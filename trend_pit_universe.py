# -*- coding: utf-8 -*-
"""장투 백테스트의 룩어헤드 검증 — 시점별(point-in-time) 유니버스로 재실행.

**왜 필요한가**
`trend_backtest.get_universe()`는 `fdr.StockListing("KOSPI")`, 즉 **오늘 시점**의
시총 5천억+·거래대금 30억+ 명단이다. `trend_regime_backtest`는 그 명단을 2022년에
그대로 적용해 4.5년을 돌린다. 2022년엔 작았다가 이후 커진 종목(효성중공업 +4390%,
HD현대일렉트릭 +3316% 등)이 **"미래에 커진다는 걸 아는 상태로"** 2022년 매수 후보에
들어간다. 추세추종 수익은 소수 대박(오른쪽 꼬리)이 지배하므로 이 편향에 특히 취약하다.

이 프로젝트는 이미 공시 필터 +73%가 생존편향 착시임을 밝힌 전례가 있다(RESULTS_KR.md
Phase 3). 같은 잣대를 장투에도 들이대는 것이 이 스크립트다.

**어떻게 검증하나**
매수 후보 판정 시점마다 그 시점의 자격을 다시 따진다:
  - 추정시총(t) = 오늘시총 × 종가(t)/오늘종가   ← 상장주식수 불변 가정
  - 20일 평균 거래대금(t) = mean(Close × Volume)
둘 다 원본 기준(5천억 / 30억)을 통과할 때만 후보에 넣는다. 나머지 로직은 원본과 동일.

**한계 (반드시 같이 읽을 것)**
1. 캐시 데이터가 '오늘 살아남은 150종목'이라 상장폐지·시총붕괴로 탈락한 종목은 애초에
   없다. 즉 이 테스트는 **룩어헤드만 걷어내고 생존편향은 그대로 남긴다** → 결과는 낙관적.
2. 상장주식수 불변 가정이라 증자·소각이 있던 종목은 추정시총에 오차가 있다.

사용: python3 trend_pit_universe.py
"""
import os
import pickle
import pandas as pd
import FinanceDataReader as fdr

from trend_regime_backtest import (simulate, stat, load_regime, START_KRW, MAX_POS,
                                   POS_KRW, CH_MULT, FEE_BUY, FEE_SELL, SLIP)

CACHE = os.path.join(os.path.dirname(__file__), "cache", "trend_kospi_long.pkl")
MIN_MARCAP = 5000e8      # get_universe()와 동일 기준
MIN_AMOUNT = 30e8


def build_eligibility(data):
    """종목×날짜 → 그 시점에 유니버스 자격이 있었는지."""
    ks = fdr.StockListing("KOSPI").dropna(subset=["Marcap"])
    marcap_today = dict(zip(ks["Code"], ks["Marcap"]))

    elig, short = {}, []
    for code, rec in data.items():
        df = rec["df"]
        mc = marcap_today.get(code)
        if mc is None:
            elig[code] = {}
            continue
        shares = mc / float(df["Close"].iloc[-1])          # 상장주식수 추정
        est_marcap = df["Close"] * shares
        amount20 = (df["Close"] * df["Volume"]).rolling(20).mean()
        ok = (est_marcap >= MIN_MARCAP) & (amount20 >= MIN_AMOUNT)
        elig[code] = ok.to_dict()
        if float(ok.mean()) < 0.5:
            short.append((rec["name"], float(ok.mean()) * 100))
    return elig, short


def simulate_pit(data, elig):
    """원본 simulate(use_regime=False)와 동일하되, 신규매수 후보에 시점자격 게이트 추가."""
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))[125:]

    def px(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    cash = START_KRW
    positions, pending, trades, equity = {}, [], [], []
    for ts in cal:
        for code in pending:
            if code in positions or len(positions) >= MAX_POS:
                continue
            op = px(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + SLIP)
            shares = int(POS_KRW / fill) if fill > 0 else 0
            if shares <= 0 or shares * fill * (1 + FEE_BUY) > cash:
                continue
            cash -= shares * fill * (1 + FEE_BUY)
            positions[code] = {"shares": shares, "entry": fill, "peak": fill}
        pending = []

        for code in list(positions.keys()):
            pos = positions[code]
            hi, cl = px(code, ts, "High"), px(code, ts, "Close")
            atr, ma60 = px(code, ts, "atr14"), px(code, ts, "ma60")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            if (ma60 and cl < ma60) or (atr and cl <= pos["peak"] - CH_MULT * atr):
                fill = cl * (1 - SLIP)
                proceeds = pos["shares"] * fill * (1 - FEE_SELL)
                cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
                cash += proceeds
                trades.append({"name": data[code]["name"], "ret_pct": (proceeds / cost - 1) * 100})
                del positions[code]

        mv = cash
        for code, pos in positions.items():
            cl = px(code, ts, "Close")
            if cl:
                mv += pos["shares"] * cl
        equity.append((ts, mv))

        if len(positions) < MAX_POS:
            cands = []
            for code, d in data.items():
                if code in positions:
                    continue
                df = d["df"]
                if ts not in df.index:
                    continue
                if not elig[code].get(ts, False):          # ← 시점자격 게이트
                    continue
                r = df.loc[ts]
                if any(pd.isna(r[c]) for c in ("ma120", "ma120_prev", "hh60")):
                    continue
                if r["Close"] > r["ma120"] and r["ma120"] > r["ma120_prev"] and r["Close"] > r["hh60"]:
                    cands.append((r["Close"] / r["ma120"] - 1, code))
            cands.sort(reverse=True)
            slots = MAX_POS - len(positions) - len(pending)
            for _, code in cands[:max(0, slots)]:
                pending.append(code)

    return equity, trades


def run():
    if not os.path.exists(CACHE):
        print(f"캐시 없음: {CACHE} — 먼저 trend_regime_backtest.py를 실행하세요")
        return
    data = pickle.load(open(CACHE, "rb"))
    print(f"[data] 캐시 {len(data)}종목")

    elig, short = build_eligibility(data)
    short.sort(key=lambda x: x[1])
    print(f"[자격] 기간의 절반도 자격을 못 갖췄던 종목 {len(short)}/{len(data)}")
    print("  자격기간 짧은 top8:", [(n, f"{p:.0f}%") for n, p in short[:8]])

    e_o, t_o = simulate(data, load_regime(), use_regime=False)
    e_p, t_p = simulate_pit(data, elig)
    s_o, s_p = stat(e_o, t_o), stat(e_p, t_p)

    print()
    print("=" * 68)
    print("  장투 무필터: 원본(오늘 유니버스) vs 시점별 유니버스")
    print("=" * 68)
    print(f"{'':24} {'총수익':>9} {'MDD':>9} {'매매':>6} {'승률':>7}")
    for lbl, s in (("원본(룩어헤드 포함)", s_o), ("시점별(룩어헤드 제거)", s_p)):
        print(f"  {lbl:22} {s['ret']:+8.1f}% {s['mdd']:8.1f}% {s['n']:6d} {s['win']:6.1f}%")

    print()
    print("연도별 수익률(%)   ★=지수 하락장")
    years = sorted(s_o["yearly"])
    print("        " + "".join(f"{y:>10}" for y in years))
    print("  원본  " + "".join(f"{s_o['yearly'][y]:>+10.1f}" for y in years))
    print("  시점  " + "".join(f"{s_p['yearly'].get(y, 0):>+10.1f}" for y in years))

    idx = fdr.DataReader("KS11", "2022-01-01")
    bh = (float(idx["Close"].iloc[-1]) / float(idx["Close"].iloc[0]) - 1) * 100
    print()
    print(f"벤치마크 KOSPI 매수후보유: {bh:+.1f}%")
    print(f"  원본 초과수익 {s_o['ret'] - bh:+.1f}%p / 시점 초과수익 {s_p['ret'] - bh:+.1f}%p")


if __name__ == "__main__":
    run()
