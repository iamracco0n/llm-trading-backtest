# -*- coding: utf-8 -*-
"""장투 트랙 — KOSPI 대형주 추세추종 장기보유 (급등 단타의 '안정 코어' 짝).

강한 상승추세(MA120 위 + MA120 우상향 + 60일 신고가 돌파) 종목을 사서
넓은 트레일링(청산=MA60 이탈 or 최고가−4×ATR)으로 수주~수개월 보유.
데이터=FinanceDataReader 일봉. 대형주라 슬리피지 작게(0.1%).
"""
import os
import pickle
import pandas as pd
import FinanceDataReader as fdr

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
START_KRW = 1_000_000
MAX_POS = 8                     # 장투는 더 분산
POS_KRW = START_KRW // MAX_POS
CH_MULT = 4.0                   # 넓은 트레일(장기보유)
FEE_BUY = 0.00015
FEE_SELL = 0.00015 + 0.0018
SLIP = 0.001                    # 대형주 슬리피지


def get_universe():
    ks = fdr.StockListing("KOSPI").dropna(subset=["Marcap", "Amount"])
    f = ks[(ks["Marcap"] >= 5000e8) & (ks["Amount"] >= 30e8)]   # 시총 5천억+, 거래대금 30억+
    return list(zip(f["Code"], f["Name"]))


def load_data(days=430, use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = os.path.join(CACHE_DIR, "trend_kospi.pkl")
    if use_cache and os.path.exists(cp):
        with open(cp, "rb") as f:
            print("[data] 장투 캐시 사용")
            return pickle.load(f)
    uni = get_universe()
    print(f"[data] KOSPI 대형주 {len(uni)}종목 수집...")
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
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


def run(slip=SLIP, verbose=True):
    data = load_data()
    if not data:
        print("데이터 없음"); return None
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
        for code in pending:                        # 어제신호 → 오늘 시가 진입
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

        for code in list(positions.keys()):         # 청산: MA60 이탈 or 넓은 트레일
            pos = positions[code]
            hi = px(code, ts, "High"); cl = px(code, ts, "Close")
            atr = px(code, ts, "atr14"); ma60 = px(code, ts, "ma60")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            if (ma60 and cl < ma60) or (atr and cl <= pos["peak"] - CH_MULT * atr):
                fill = cl * (1 - slip)
                proceeds = pos["shares"] * fill * (1 - FEE_SELL)
                cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
                cash += proceeds
                trades.append({"name": data[code]["name"],
                               "ret_pct": (proceeds / cost - 1) * 100})
                del positions[code]

        mv = cash
        for code, pos in positions.items():
            cl = px(code, ts, "Close")
            if cl:
                mv += pos["shares"] * cl
        equity.append((ts, mv))

        if len(positions) < MAX_POS:                # 신호: 확인된 상승추세 돌파
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
                if r["Close"] > r["ma120"] and r["ma120"] > r["ma120_prev"] \
                        and r["Close"] > r["hh60"]:
                    cands.append((r["Close"] / r["ma120"] - 1, code))   # 추세강도순
            cands.sort(reverse=True)
            slots = MAX_POS - len(positions) - len(pending)
            for _, code in cands[:max(0, slots)]:
                pending.append(code)

    end_v = equity[-1][1] if equity else START_KRW
    peak, mdd = START_KRW, 0
    for _, v in equity:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    wins = [t for t in trades if t["ret_pct"] > 0]
    res = {"ret": (end_v / START_KRW - 1) * 100, "mdd": mdd * 100,
           "n": len(trades), "win": 100 * len(wins) / len(trades) if trades else 0,
           "avg": sum(t["ret_pct"] for t in trades) / len(trades) if trades else 0,
           "cal": (cal[0], cal[-1]), "equity": equity}
    if verbose:
        print("=" * 60)
        print(f"  장투(KOSPI 대형주 추세추종)  {res['cal'][0].date()}~{res['cal'][1].date()}")
        print("=" * 60)
        print(f"  수익률 {res['ret']:+.2f}%   MDD {res['mdd']:.2f}%   매매 {res['n']}   승률 {res['win']:.1f}%   평균 {res['avg']:+.2f}%")
        print("=" * 60)
    return res


if __name__ == "__main__":
    run()
