# -*- coding: utf-8 -*-
"""Stage 0 — 포워드 페이퍼(실시간 모의매매). 검증된 장투(추세추종 무필터)를 실전 배포 전
과거편향 없는 '지금부터의 데이터'로 검증한다. 실주문 없음 — 결정만 기록.

매일 장 마감 후 1회 실행:
  1) 지난 실행의 예약매수 → 오늘 시가 체결(모의)
  2) 청산조건(MA60 이탈 / 최고가−4×ATR) → 오늘 종가 청산
  3) 자산 평가·기록
  4) 오늘 종가 기준 신규 매수신호 → 내일 예약
상태는 cache/paper_state.json에 영속. 여러 번 돌려도 같은 날은 스킵(멱등).

데이터=FinanceDataReader(무료). 검증 후 실행 레이어만 토스 API로 교체하면 실전(Stage 1).
사용: python3 forward_paper.py         (오늘분 진행)
      python3 forward_paper.py --status (상태만 조회)
"""
import os
import json
import argparse
import datetime as dt
import pandas as pd
import FinanceDataReader as fdr

from trend_backtest import (get_universe, START_KRW, MAX_POS, POS_KRW,
                            CH_MULT, FEE_BUY, FEE_SELL, SLIP)

STATE = os.path.join(os.path.dirname(__file__), "cache", "paper_state.json")


def _blank_state():
    return {"start_date": None, "last_date": None, "cash": START_KRW,
            "positions": {}, "pending": [], "equity": [], "trades": [],
            "universe": []}


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return _blank_state()


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def fetch(codes, days=280):
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    for code in codes:
        try:
            df = fdr.DataReader(code, start)
        except Exception:
            continue
        if df is None or len(df) < 125:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df["ma60"] = df["Close"].rolling(60).mean()
        df["ma120"] = df["Close"].rolling(120).mean()
        df["ma120_prev"] = df["ma120"].shift(20)
        pc = df["Close"].shift()
        tr = (df["High"] - df["Low"]).combine((df["High"] - pc).abs(), max) \
                                     .combine((df["Low"] - pc).abs(), max)
        df["atr14"] = tr.rolling(14).mean()
        df["hh60"] = df["High"].rolling(60).max().shift(1)
        out[code] = df
    return out


def run(status_only=False):
    s = load_state()
    if not s["universe"]:
        s["universe"] = [[c, n] for c, n in get_universe()]
        print(f"[init] 유니버스 {len(s['universe'])}종목 스냅샷")
    name = {c: n for c, n in s["universe"]}
    codes = [c for c, _ in s["universe"]]

    if status_only:
        _report(s, name, {}, [], [], None); return

    print(f"[data] {len(codes)}종목 최신 일봉 수집...")
    data = fetch(codes)
    if not data:
        print("데이터 없음"); return
    today = max(df.index[-1] for df in data.values())
    tstr = today.strftime("%Y-%m-%d")
    if s["last_date"] == tstr:
        print(f"[skip] {tstr} 이미 처리됨 (장 열린 새 날에 다시 실행)")
        _report(s, name, {}, [], [], today); return
    if s["start_date"] is None:
        s["start_date"] = tstr

    def val(code, col):
        df = data.get(code)
        if df is not None and today in df.index:
            v = df.at[today, col]
            return None if pd.isna(v) else float(v)
        return None

    bought, sold = [], []
    # 1) 예약매수 → 오늘 시가 체결
    for code in s["pending"]:
        if code in s["positions"] or len(s["positions"]) >= MAX_POS:
            continue
        op = val(code, "Open")
        if op is None:
            continue
        fill = op * (1 + SLIP)
        shares = int(POS_KRW / fill) if fill > 0 else 0
        if shares <= 0 or shares * fill * (1 + FEE_BUY) > s["cash"]:
            continue
        s["cash"] -= shares * fill * (1 + FEE_BUY)
        s["positions"][code] = {"shares": shares, "entry": fill, "peak": fill,
                                "entry_date": tstr, "name": name.get(code, code)}
        bought.append((code, name.get(code, code), fill))
    s["pending"] = []

    # 2) 청산: MA60 이탈 / 트레일
    for code in list(s["positions"].keys()):
        pos = s["positions"][code]
        hi, cl = val(code, "High"), val(code, "Close")
        atr, ma60 = val(code, "atr14"), val(code, "ma60")
        if cl is None:
            continue
        if hi is not None:
            pos["peak"] = max(pos["peak"], hi)
        reason = ("추세이탈(MA60)" if (ma60 and cl < ma60)
                  else "트레일청산" if (atr and cl <= pos["peak"] - CH_MULT * atr) else None)
        if reason:
            fill = cl * (1 - SLIP)
            proceeds = pos["shares"] * fill * (1 - FEE_SELL)
            cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
            s["cash"] += proceeds
            s["trades"].append({"date": tstr, "name": pos["name"], "side": "SELL",
                                "ret_pct": round((proceeds / cost - 1) * 100, 2), "reason": reason})
            sold.append((code, pos["name"], round((proceeds / cost - 1) * 100, 1)))
            del s["positions"][code]

    # 3) 자산 평가
    mv = s["cash"]
    for code, pos in s["positions"].items():
        cl = val(code, "Close")
        if cl:
            mv += pos["shares"] * cl
    s["equity"].append([tstr, round(mv)])

    # 4) 신규 매수신호 → 내일 예약
    new_sig = []
    if len(s["positions"]) < MAX_POS:
        cands = []
        for code in codes:
            if code in s["positions"]:
                continue
            df = data.get(code)
            if df is None or today not in df.index:
                continue
            r = df.loc[today]
            if any(pd.isna(r[c]) for c in ("ma120", "ma120_prev", "hh60")):
                continue
            if r["Close"] > r["ma120"] and r["ma120"] > r["ma120_prev"] and r["Close"] > r["hh60"]:
                cands.append((r["Close"] / r["ma120"] - 1, code))
        cands.sort(reverse=True)
        slots = MAX_POS - len(s["positions"])
        for _, code in cands[:max(0, slots)]:
            s["pending"].append(code)
            new_sig.append((code, name.get(code, code)))

    s["last_date"] = tstr
    save_state(s)
    _report(s, name, dict(bought=bought, sold=sold), new_sig, s["pending"], today)


def _report(s, name, acts, new_sig, pending, today):
    print("=" * 60)
    print(f"  포워드 페이퍼 (장투)   기준일 {s['last_date']}  (시작 {s['start_date']})")
    print("=" * 60)
    eq = s["equity"][-1][1] if s["equity"] else START_KRW
    ret = (eq / START_KRW - 1) * 100
    peak = START_KRW; mdd = 0
    for _, v in s["equity"]:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    print(f"  평가자산 {eq:,}원  ({ret:+.2f}%)   MDD {mdd*100:.1f}%   거래 {len(s['trades'])}회")
    if acts:
        for c, n, p in acts.get("bought", []):
            print(f"  ▶ 매수  {n}({c}) @ {p:,.0f}")
        for c, n, r in acts.get("sold", []):
            print(f"  ◀ 매도  {n}({c})  {r:+.1f}%")
    print(f"  보유 {len(s['positions'])}/{MAX_POS}:", ", ".join(
        f"{p['name']}" for p in s["positions"].values()) or "없음")
    if pending:
        print("  내일 예약매수:", ", ".join(name.get(c, c) for c in pending))
    print("=" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="상태만 조회")
    a = ap.parse_args()
    run(status_only=a.status)
