# -*- coding: utf-8 -*-
"""장투 + 국면필터 — 하락장까지 포함해 검증 (2022~2026, 상승·하락 전 구간).

가설: 추세추종 장투는 상승장 전용이라 하락장에서 썰린다. **코스피 지수가 MA120 위(=위험선호)
      일 때만 신규매수**하는 국면필터를 붙이면 2022/2024 하락장을 피해 낙폭이 줄어드나?

무필터 vs 국면필터를 같은 데이터로 나란히. 연도별·MDD 비교.
데이터=FinanceDataReader, 지수=KS11(코스피). 대형주라 슬리피지 0.1%.
"""
import os
import pickle
import pandas as pd
import FinanceDataReader as fdr

from trend_backtest import (get_universe, START_KRW, MAX_POS, POS_KRW,
                            CH_MULT, FEE_BUY, FEE_SELL, SLIP)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
INDEX_MA = 120


def load_data(start="2022-01-01", use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = os.path.join(CACHE_DIR, "trend_kospi_long.pkl")
    if use_cache and os.path.exists(cp):
        with open(cp, "rb") as f:
            print("[data] 장투(장기) 캐시 사용")
            return pickle.load(f)
    uni = get_universe()
    print(f"[data] KOSPI 대형주 {len(uni)}종목 장기수집({start}~)...")
    data = {}
    for i, (code, name) in enumerate(uni):
        try:
            df = fdr.DataReader(code, start)
        except Exception:
            continue
        if df is None or len(df) < 130:
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
        data[code] = {"name": name, "df": df}
        if (i + 1) % 40 == 0:
            print(f"[data]   {i+1}/{len(uni)}")
    with open(cp, "wb") as f:
        pickle.dump(data, f)
    print(f"[data] 저장 ({len(data)}종목)")
    return data


def load_regime(start="2022-01-01"):
    """코스피 지수 MA120 위 → risk_on(그날 신규매수 허용). {date: bool}."""
    idx = fdr.DataReader("KS11", start)
    ma = idx["Close"].rolling(INDEX_MA).mean()
    ron = idx["Close"] > ma
    return ron.to_dict()


def simulate(data, regime, use_regime, slip=SLIP):
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))[125:]

    def px(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    cash = START_KRW
    positions, pending, trades, equity = {}, [], [], []
    for i, ts in enumerate(cal):
        risk_on = bool(regime.get(ts, False))
        for code in pending:
            if code in positions or len(positions) >= MAX_POS:
                continue
            op = px(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + slip)
            shares = int(POS_KRW / fill) if fill > 0 else 0
            if shares <= 0 or shares * fill * (1 + FEE_BUY) > cash:
                continue
            cash -= shares * fill * (1 + FEE_BUY)
            positions[code] = {"shares": shares, "entry": fill, "peak": fill}
        pending = []

        for code in list(positions.keys()):
            pos = positions[code]
            hi = px(code, ts, "High"); cl = px(code, ts, "Close")
            atr = px(code, ts, "atr14"); ma60 = px(code, ts, "ma60")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            # 청산: 추세이탈 or 트레일 (국면필터면 risk-off 전환 시에도 방어청산)
            regime_exit = use_regime and not risk_on
            if (ma60 and cl < ma60) or (atr and cl <= pos["peak"] - CH_MULT * atr) or regime_exit:
                fill = cl * (1 - slip)
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

        # 신규매수: 국면필터면 risk_on일 때만
        if len(positions) < MAX_POS and (risk_on or not use_regime):
            cands = []
            for code, d in data.items():
                if code in positions:
                    continue
                df = d["df"]
                if ts not in df.index:
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


def stat(equity, trades):
    end = equity[-1][1] if equity else START_KRW
    peak, mdd = START_KRW, 0
    for _, v in equity:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    wins = [t for t in trades if t["ret_pct"] > 0]
    s = pd.Series({pd.Timestamp(t): v for t, v in equity})
    yearly = {}
    for y in sorted(set(s.index.year)):
        sy = s[s.index.year == y]
        if len(sy) > 1:
            yearly[y] = (sy.iloc[-1] / sy.iloc[0] - 1) * 100
    return {"ret": (end / START_KRW - 1) * 100, "mdd": mdd * 100, "n": len(trades),
            "win": 100 * len(wins) / len(trades) if trades else 0, "yearly": yearly}


def run():
    data = load_data()
    regime = load_regime()
    ea, ta = simulate(data, regime, use_regime=False)
    eb, tb = simulate(data, regime, use_regime=True)
    A, B = stat(ea, ta), stat(eb, tb)
    cal0 = min(data[list(data)[0]]["df"].index)
    print("=" * 72)
    print(f"  장투 국면필터 검증 (2022~2026, 상승·하락 전구간)")
    print("=" * 72)
    print("  전략              수익률%     MDD%   매매  승률%")
    print("-" * 72)
    for name, s in [("무필터", A), ("★ 국면필터", B)]:
        print(f"  {name:<12} {s['ret']:>9.1f} {s['mdd']:>8.1f} {s['n']:>5} {s['win']:>6.1f}")
    print("-" * 72)
    print("  연도별 수익률%:")
    yrs = sorted(set(A["yearly"]) | set(B["yearly"]))
    print("     " + "".join(f"{y:>9}" for y in yrs))
    print("  무필터 " + "".join(f"{A['yearly'].get(y,0):>+9.1f}" for y in yrs))
    print("  필터  " + "".join(f"{B['yearly'].get(y,0):>+9.1f}" for y in yrs))
    print("=" * 72)


if __name__ == "__main__":
    run()
