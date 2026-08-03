# -*- coding: utf-8 -*-
"""생존편향 제거 재검증 — 상장폐지 종목을 유니버스에 되살려 다시 돌린다.

**남아 있던 마지막 편향.**
이 레포의 모든 백테스트는 유니버스를 `fdr.StockListing()`, 즉 **오늘 살아있는 종목**에서
뽑았다. 그사이 상장폐지된 종목은 표본에 아예 없다. 최악의 손실은 "사고 나서 무너진 종목"에서
나오는데 그 사례가 통째로 빠져 있었다. `trend_pit_universe.py`가 룩어헤드를 걷어냈지만
이 편향은 그대로 남겨뒀다 — 이 스크립트가 그걸 마저 걷어낸다.

**편향을 분리해서 본다.** 섞으면 무엇이 원인인지 읽을 수 없으므로 한 번에 하나씩만 바꾼다.

**상폐 처리(중요).** 기존 `simulate()`를 그대로 쓰면 안 된다. 데이터가 끊긴 종목은
`cl is None`으로 청산 로직을 빠져나가 **포지션에 영원히 남고**, 자산평가에서 조용히
사라지는 데다 **MAX_POS 슬롯을 영구 점유**해 이후 매수를 막는다. 그래서 여기서는
종목별 마지막 거래일을 추적해 **그날 종가로 강제 청산**한다(대개 정리매매 폭락가).
청산 규칙이 먼저 걸리면 그쪽이 우선이므로, 이 처리는 '규칙이 못 빠져나온 경우'만 잡는다.

**상폐 사유를 구분한다.** 2022년 이후 상폐 다수가 스팩소멸합병·지주회사 완전자회사화·
피흡수합병이라 '망한 것'이 아니다(현대홈쇼핑·더존비즈온도 여기 속한다). 부실 상폐는
"기업의 계속성 및 경영의 투명성..." 계열이다. 그래서 '전체 상폐'와 '부실 상폐만'을 나눠 본다.

사용: python3 delisted_recheck.py --track trend
      python3 delisted_recheck.py --track surge
"""
import os
import pickle
import argparse

import pandas as pd
import FinanceDataReader as fdr

CACHE = os.path.join(os.path.dirname(__file__), "cache")
DELISTED = os.path.join(CACHE, "delisted_prices.pkl")
FAIL_KW = ["계속성", "투명성", "감사의견", "자본잠식", "부도", "회생", "횡령", "배임"]


def is_failure(reason):
    return any(k in str(reason) for k in FAIL_KW)


def load_delisted(market, only_failure=False):
    if not os.path.exists(DELISTED):
        raise SystemExit(f"상폐 캐시 없음: {DELISTED}")
    d = pickle.load(open(DELISTED, "rb"))
    return {c: r for c, r in d.items() if r["market"] == market
            and (not only_failure or is_failure(r["reason"]))}


def _atr_hh(df, hh_win):
    pc = df["Close"].shift()
    tr = (df["High"] - df["Low"]).combine((df["High"] - pc).abs(), max) \
                                 .combine((df["Low"] - pc).abs(), max)
    df["atr14"] = tr.rolling(14).mean()
    df["hh%d" % hh_win] = df["High"].rolling(hh_win).max().shift(1)
    return df


def ind_trend(df):
    df = df.copy()
    df["ma60"] = df["Close"].rolling(60).mean()
    df["ma120"] = df["Close"].rolling(120).mean()
    df["ma120_prev"] = df["ma120"].shift(20)
    return _atr_hh(df, 60)


def ind_surge(df):
    df = df.copy()
    df["vma20"] = df["Volume"].rolling(20).mean()
    df["ret1"] = df["Close"].pct_change()
    return _atr_hh(df, 20)


def stat_of(equity, trades, start):
    end = equity[-1][1] if equity else start
    peak, mdd = start, 0
    for _, v in equity:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    wins = [t for t in trades if t["ret_pct"] > 0]
    s = pd.Series({pd.Timestamp(t): v for t, v in equity})
    yearly = {}
    for y in sorted(set(s.index.year)):
        sy = s[s.index.year == y]
        if len(sy) > 1:
            yearly[y] = (sy.iloc[-1] / sy.iloc[0] - 1) * 100
    return {"ret": (end / start - 1) * 100, "mdd": mdd * 100, "n": len(trades),
            "win": 100 * len(wins) / len(trades) if trades else 0, "yearly": yearly,
            "delist_exits": sum(1 for t in trades if t["reason"] == "상장폐지"),
            "delist_pnl": sum(t["ret_pct"] for t in trades if t["reason"] == "상장폐지")}


def simulate(data, cfg, elig=None):
    """장투/단타 공통 시뮬레이터 + 상폐 강제청산.

    cfg: dict(entry=..., exit=..., start, max_pos, pos_krw, slip, fee_buy, fee_sell, warmup)
    """
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))[cfg["warmup"]:]
    last_day = {c: d["df"].index[-1] for c, d in data.items()}
    overall_last = max(last_day.values())

    def px(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    cash = cfg["start"]
    positions, pending, trades, equity = {}, [], [], []

    def sell(code, price, ts, reason):
        nonlocal cash
        p = positions[code]
        proceeds = p["shares"] * price * (1 - cfg["fee_sell"])
        cost = p["shares"] * p["entry"] * (1 + cfg["fee_buy"])
        cash += proceeds
        trades.append({"date": ts, "name": data[code]["name"], "reason": reason,
                       "ret_pct": (proceeds / cost - 1) * 100})
        del positions[code]

    for i, ts in enumerate(cal):
        for code in pending:
            if code in positions or len(positions) >= cfg["max_pos"]:
                continue
            op = px(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + cfg["slip"])
            shares = int(cfg["pos_krw"] / fill) if fill > 0 else 0
            cost = shares * fill * (1 + cfg["fee_buy"])
            if shares <= 0 or cost > cash:
                continue
            cash -= cost
            positions[code] = {"shares": shares, "entry": fill, "peak": fill, "i0": i}
        pending = []

        # 상폐 강제청산 — 그 종목의 마지막 거래일이 지났는데 아직 들고 있으면
        for code in list(positions.keys()):
            ld = last_day[code]
            if ts > ld and ld < overall_last:
                sell(code, float(data[code]["df"].at[ld, "Close"]) * (1 - cfg["slip"]),
                     ts, "상장폐지")

        for code in list(positions.keys()):
            p = positions[code]
            hi, cl = px(code, ts, "High"), px(code, ts, "Close")
            if cl is None:
                continue
            if hi is not None:
                p["peak"] = max(p["peak"], hi)
            reason = cfg["exit"](data[code]["df"], ts, p, i, cl)
            if reason:
                sell(code, cl * (1 - cfg["slip"]), ts, reason)

        mv = cash
        for code, p in positions.items():
            cl = px(code, ts, "Close")
            if cl:
                mv += p["shares"] * cl
        equity.append((ts, mv))

        if len(positions) < cfg["max_pos"]:
            cands = []
            for code, d in data.items():
                if code in positions or ts not in d["df"].index:
                    continue
                if elig is not None and not elig.get(code, {}).get(ts, False):
                    continue
                sc = cfg["entry"](d["df"], ts)
                if sc is not None:
                    cands.append((sc, code))
            cands.sort(reverse=True)
            for _, code in cands[:max(0, cfg["max_pos"] - len(positions) - len(pending))]:
                pending.append(code)

    return equity, trades


# ─────────────────────── 트랙별 규칙 ───────────────────────

def trend_cfg():
    from trend_backtest import START_KRW, MAX_POS, POS_KRW, CH_MULT, FEE_BUY, FEE_SELL, SLIP

    def entry(df, ts):
        r = df.loc[ts]
        if any(pd.isna(r[c]) for c in ("ma120", "ma120_prev", "hh60")):
            return None
        if r["Close"] > r["ma120"] and r["ma120"] > r["ma120_prev"] and r["Close"] > r["hh60"]:
            return r["Close"] / r["ma120"] - 1
        return None

    def exit_(df, ts, p, i, cl):
        r = df.loc[ts]
        ma60, atr = r.get("ma60"), r.get("atr14")
        if pd.notna(ma60) and cl < ma60:
            return "추세이탈"
        if pd.notna(atr) and cl <= p["peak"] - CH_MULT * atr:
            return "트레일"
        return None

    return dict(entry=entry, exit=exit_, start=START_KRW, max_pos=MAX_POS,
                pos_krw=POS_KRW, slip=SLIP, fee_buy=FEE_BUY, fee_sell=FEE_SELL, warmup=125)


def surge_cfg():
    from surge_backtest import (START_KRW, MAX_POS, POS_KRW, VOL_SURGE, UP_MIN,
                                CH_MULT, HARD_STOP, MAX_HOLD, FEE_BUY, FEE_SELL)

    def entry(df, ts):
        r = df.loc[ts]
        if pd.isna(r["vma20"]) or pd.isna(r["hh20"]) or r["vma20"] == 0:
            return None
        vr = r["Volume"] / r["vma20"]
        if vr >= VOL_SURGE and r["ret1"] >= UP_MIN and r["Close"] > r["hh20"]:
            return vr
        return None

    def exit_(df, ts, p, i, cl):
        atr = df.at[ts, "atr14"]
        if cl / p["entry"] - 1 <= HARD_STOP:
            return "손절"
        if pd.notna(atr) and cl <= p["peak"] - CH_MULT * atr:
            return "트레일"
        if i - p["i0"] >= MAX_HOLD:
            return "시간만료"
        return None

    return dict(entry=entry, exit=exit_, start=START_KRW, max_pos=MAX_POS,
                pos_krw=POS_KRW, slip=0.003, fee_buy=FEE_BUY, fee_sell=FEE_SELL, warmup=40)


def merge(base, market, ind, only_failure, since=None):
    dl = load_delisted(market, only_failure)
    merged, added = dict(base), 0
    for code, rec in dl.items():
        if code in merged:
            continue
        df = ind(rec["df"])
        if since is not None:
            df = df[df.index >= since]
        if len(df) < 60:
            continue
        merged[code] = {"name": rec["name"], "df": df, "shares": rec.get("shares")}
        added += 1
    return merged, added


def show(title, rows, bench=None):
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print(f"  {'구성':<28}{'총수익':>10}{'MDD':>9}{'매매':>7}{'승률':>8}{'상폐청산':>9}")
    for label, s in rows:
        print(f"  {label:<28}{s['ret']:+9.1f}%{s['mdd']:8.1f}%{s['n']:7d}{s['win']:7.1f}%"
              f"{s['delist_exits']:8d}건")
    if bench is not None:
        print(f"\n  벤치마크 매수후보유 {bench:+.1f}%")


def run_trend(_):
    base = pickle.load(open(os.path.join(CACHE, "trend_kospi_long.pkl"), "rb"))
    print(f"[base] 현재 상장 {len(base)}종목")
    cfg = trend_cfg()
    since = pd.Timestamp("2021-06-01")

    rows = []
    e, t = simulate(base, cfg)
    rows.append(("원본(오늘 상장만)", stat_of(e, t, cfg["start"])))
    for label, of in (("전체 상폐", False), ("부실 상폐만", True)):
        m, added = merge(base, "KOSPI", ind_trend, of, since)
        e, t = simulate(m, cfg)
        rows.append((f"+{label} ({added}종목)", stat_of(e, t, cfg["start"])))

    # 결정적 조합: 상폐 포함 + 시점별 자격(룩어헤드 제거)
    m_all, added_all = merge(base, "KOSPI", ind_trend, False, since)
    ks = fdr.StockListing("KOSPI").dropna(subset=["Marcap"])
    mc = dict(zip(ks["Code"], ks["Marcap"]))
    elig = {}
    for code, rec in m_all.items():
        df = rec["df"]
        sh = (mc[code] / float(df["Close"].iloc[-1])) if code in mc else rec.get("shares")
        if not sh:
            elig[code] = {}
            continue
        ok = ((df["Close"] * sh >= 5000e8) &
              ((df["Close"] * df["Volume"]).rolling(20).mean() >= 30e8))
        elig[code] = ok.to_dict()
    e, t = simulate(m_all, cfg, elig)
    rows.append(("+상폐 +시점별자격(둘 다)", stat_of(e, t, cfg["start"])))

    idx = fdr.DataReader("KS11", "2022-01-01")
    bh = (float(idx["Close"].iloc[-1]) / float(idx["Close"].iloc[0]) - 1) * 100
    show("장투(추세추종) — 생존편향 제거 재검증 (2022~2026)", rows, bh)
    print("\n  연도별 수익률(%)")
    years = sorted(rows[0][1]["yearly"])
    print("    " + "".join(f"{y:>10}" for y in years))
    for label, s in rows:
        print(f"    {label[:14]:<14}" + "".join(f"{s['yearly'].get(y, 0):>+10.1f}" for y in years))


def run_surge(_):
    import surge_backtest as sb
    base = sb.load_data()
    print(f"[base] 현재 상장 {len(base)}종목")
    cfg = surge_cfg()
    since = min(min(d["df"].index) for d in base.values())

    rows = []
    e, t = simulate(base, cfg)
    rows.append(("원본(오늘 상장만)", stat_of(e, t, cfg["start"])))
    for label, of in (("전체 상폐", False), ("부실 상폐만", True)):
        m, added = merge(base, "KOSDAQ", ind_surge, of, since)
        e, t = simulate(m, cfg)
        rows.append((f"+{label} ({added}종목)", stat_of(e, t, cfg["start"])))
    show("단타(급등추격) — 생존편향 제거 재검증", rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=["trend", "surge"], default="trend")
    a = ap.parse_args()
    (run_trend if a.track == "trend" else run_surge)(a)
