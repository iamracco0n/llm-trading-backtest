# -*- coding: utf-8 -*-
"""Phase 1 — 급등주 올라타기 백테스트 (거래량 급증 + 급등 돌파 모멘텀).

"작전주/테마주 급등을 뉴스 없이 순수 가격·거래량 신호로 잡아 트레일링 손절로 타면
기댓값이 +인가?"를 정직하게 검증. 뉴스/공시/종토방은 다음 단계(phase 2~).

정직성 장치:
  - 신호는 당일 '종가'로 잡지만 진입은 '다음날 시가'(그 종가엔 못 사니까 = look-ahead 방지)
  - 소형주 슬리피지 반영(--slip). 이거 빼면 급등추격은 실제보다 훨씬 좋아 보임
  - 한국 주식 매도세 0.18% + 수수료 반영

데이터=FinanceDataReader(KRX 일봉, 무료). 유니버스=KOSDAQ 시총≤2조 & 거래대금≥30억.
"""
import os
import sys
import pickle
import argparse

import pandas as pd
import FinanceDataReader as fdr

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
START_KRW = 1_000_000
MAX_POS = 5
POS_KRW = START_KRW // MAX_POS         # 종목당 균등 20만

# 신호 파라미터
VOL_SURGE = 3.0      # 거래량 ≥ 20일평균 × 3
UP_MIN = 0.06        # 당일 +6% 이상
# 청산
CH_MULT = 3.0        # 샹들리에 트레일: 최고가 − 3×ATR
HARD_STOP = -0.08    # 진입 대비 −8% 손절
MAX_HOLD = 15        # 최대 보유 15거래일

# 비용
FEE_BUY = 0.00015            # 매수 수수료
FEE_SELL = 0.00015 + 0.0018  # 매도 수수료 + 증권거래세 0.18%


def get_universe():
    kq = fdr.StockListing("KOSDAQ").dropna(subset=["Marcap", "Amount"])
    f = kq[(kq["Marcap"] <= 2e12) & (kq["Amount"] >= 30e8)]
    return list(zip(f["Code"], f["Name"]))


def load_data(days=430, use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = os.path.join(CACHE_DIR, "surge_kosdaq.pkl")
    if use_cache and os.path.exists(cp):
        with open(cp, "rb") as f:
            print("[data] 캐시 사용")
            return pickle.load(f)
    uni = get_universe()
    print(f"[data] 유니버스 {len(uni)}종목 수집 (FDR)...")
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    data = {}
    for i, (code, name) in enumerate(uni):
        try:
            df = fdr.DataReader(code, start)
        except Exception:
            continue
        if df is None or len(df) < 60:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        # 지표 프리컴퓨트
        df["vma20"] = df["Volume"].rolling(20).mean()
        df["ret1"] = df["Close"].pct_change()
        pc = df["Close"].shift()
        tr = (df["High"] - df["Low"]).combine((df["High"] - pc).abs(), max) \
                                     .combine((df["Low"] - pc).abs(), max)
        df["atr14"] = tr.rolling(14).mean()
        df["hh20"] = df["High"].rolling(20).max().shift(1)  # 직전 20일 고점(당일 제외)
        data[code] = {"name": name, "df": df}
        if (i + 1) % 40 == 0:
            print(f"[data]   {i+1}/{len(uni)}")
    with open(cp, "wb") as f:
        pickle.dump(data, f)
    print(f"[data] 저장 완료 ({len(data)}종목)")
    return data


def run(slip=0.003):
    data = load_data()
    if not data:
        print("데이터 없음"); return
    # 마스터 거래일 달력 = 전 종목 날짜 합집합
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))
    cal = cal[40:]  # 워밍업(20일 지표 + 여유)

    cash = START_KRW
    positions = {}          # code -> dict(shares, entry, peak, day0_i)
    pending = []            # 다음날 시가 진입 대기 code 목록
    trades = []
    equity = []

    def price_at(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    for i, ts in enumerate(cal):
        # 1) 어제 신호 → 오늘 시가 진입
        newpend = []
        for code in pending:
            if code in positions or len(positions) >= MAX_POS:
                continue
            op = price_at(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + slip)                 # 슬리피지: 시가보다 불리하게 체결
            shares = int(POS_KRW / fill) if fill > 0 else 0
            if shares <= 0:
                continue
            cost = shares * fill * (1 + FEE_BUY)
            if cost > cash:
                continue
            cash -= cost
            positions[code] = {"shares": shares, "entry": fill, "peak": fill, "i0": i}
        pending = newpend

        # 2) 청산 판정(오늘 데이터), 체결은 종가 기준(슬리피지 불리)
        for code in list(positions.keys()):
            pos = positions[code]
            hi = price_at(code, ts, "High"); cl = price_at(code, ts, "Close")
            atr = price_at(code, ts, "atr14")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            ret = cl / pos["entry"] - 1
            reason = None
            if ret <= HARD_STOP:
                reason = "손절"
            elif atr and cl <= pos["peak"] - CH_MULT * atr:
                reason = "트레일청산"
            elif i - pos["i0"] >= MAX_HOLD:
                reason = "시간만료"
            if reason:
                fill = cl * (1 - slip)
                proceeds = pos["shares"] * fill * (1 - FEE_SELL)
                cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
                cash += proceeds
                trades.append({"code": code, "name": data[code]["name"],
                               "ret_pct": round((proceeds / cost - 1) * 100, 2),
                               "reason": reason})
                del positions[code]

        # 3) 종가 마크 + 자산평가
        mv = cash
        for code, pos in positions.items():
            cl = price_at(code, ts, "Close")
            if cl:
                mv += pos["shares"] * cl
        equity.append((ts, mv))

        # 4) 오늘 종가로 급등 신호 스캔 → 내일 시가 진입 대기
        if len(positions) < MAX_POS:
            cands = []
            for code, d in data.items():
                if code in positions:
                    continue
                df = d["df"]
                if ts not in df.index:
                    continue
                r = df.loc[ts]
                if pd.isna(r["vma20"]) or pd.isna(r["hh20"]) or r["vma20"] == 0:
                    continue
                vr = r["Volume"] / r["vma20"]
                if vr >= VOL_SURGE and r["ret1"] >= UP_MIN and r["Close"] > r["hh20"]:
                    cands.append((vr, code))
            cands.sort(reverse=True)
            slots = MAX_POS - len(positions) - len(pending)
            for _, code in cands[:max(0, slots)]:
                pending.append(code)

    # 청산 못 한 잔여 포지션 마지막 종가로 정리
    end_v = equity[-1][1] if equity else START_KRW
    peak = START_KRW; mdd = 0
    for _, v in equity:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    wins = [t for t in trades if t["ret_pct"] > 0]
    ret = (end_v / START_KRW - 1) * 100
    avg = sum(t["ret_pct"] for t in trades) / len(trades) if trades else 0

    print("=" * 60)
    print(f"  급등 모멘텀 백테스트  (슬리피지 {slip*100:.1f}%/편도)")
    print(f"  기간: {cal[0].date()} ~ {cal[-1].date()}  ({len(cal)}거래일)")
    print("=" * 60)
    print(f"  최종자산 : {round(end_v):,}원   수익률 {ret:+.2f}%")
    print(f"  MDD      : {mdd*100:.2f}%")
    print(f"  매매     : {len(trades)}회   승률 {100*len(wins)/len(trades) if trades else 0:.1f}%   평균손익 {avg:+.2f}%/트레이드")
    if trades:
        best = sorted(trades, key=lambda t: t["ret_pct"], reverse=True)[:3]
        worst = sorted(trades, key=lambda t: t["ret_pct"])[:3]
        print("  베스트:", ", ".join(f"{t['name']} {t['ret_pct']:+.0f}%" for t in best))
        print("  워스트:", ", ".join(f"{t['name']} {t['ret_pct']:+.0f}%" for t in worst))
    print("=" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=0.003, help="편도 슬리피지(기본 0.3%)")
    a = ap.parse_args()
    run(slip=a.slip)
