# -*- coding: utf-8 -*-
"""젯슨 코인봇(HTF 1시간봉 추세추종) 파라미터 재검증.

**왜 다시 재나.** `htf_indicators.py` 주석에는 "백테스트로 검증: 하락장에서도 +25%,
손익비 2.0"이라 적혀 있는데, 25일 실거래(페이퍼) 결과는 정반대다:

    청산 13건 | 승률 15.4% | 평균 승 +1.15% / 평균 패 −3.65% | 누적 −37.82%

**손익비가 2.0이 아니라 0.3이다.** 이기는 폭이 지는 폭의 1/3. 추세추종은 "승률 낮아도
이길 때 크게"가 성립해야 하는데 지금은 승률도 낮고 이겨도 조금 번다. 주석의 백테스트가
어떤 조건이었는지 기록이 없어 재현이 안 되므로, **같은 로직을 그대로 옮겨 다시 잰다.**

**전략(젯슨 코드 그대로)**
  · 진입: 직전 20봉(1h) 고점 상향 돌파 + 종가 > ma50(1h)
  · 국면: BTC 일봉 종가 > 일봉 ma50 일 때만 신규 매수
  · 청산: 샹들리에 트레일 = 진입후 최고가 − M×ATR(14)
  · 동시보유 3, 회당 5만원, 왕복 수수료 0.1%, 24h 모멘텀 강한 순 선택

**재는 것**: (1) 트레일 배수 M (2) 유니버스 크기.
데이터는 업비트 공개 REST(1시간봉)로 직접 받는다.

사용: python3 htf_tune.py fetch     # 시세 수집(캐시)
      python3 htf_tune.py sweep     # M × 유니버스 격자 탐색
"""
import os
import json
import time
import pickle
import argparse
import urllib.request

import numpy as np
import pandas as pd

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PX = os.path.join(CACHE, "htf_upbit_1h.pkl")
UP = "https://api.upbit.com/v1"

# 젯슨 현재 설정
DC_ENTRY, ATR_N, MA_TREND, MOM_LB = 20, 14, 50, 24
BUY_AMOUNT, MAX_POS, FEE = 50_000, 3, 0.001

STABLE = ("KRW-USDT", "KRW-USDC", "KRW-DAI", "KRW-BUSD", "KRW-TUSD")


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def top_markets(n=60):
    """거래대금 상위 KRW 마켓. 스테이블은 뺀다(추세가 없다)."""
    mk = _get(f"{UP}/market/all?isDetails=false") or []
    krw = [m["market"] for m in mk if m["market"].startswith("KRW-")
           and m["market"] not in STABLE]
    out = []
    for i in range(0, len(krw), 100):
        chunk = ",".join(krw[i:i + 100])
        t = _get(f"{UP}/ticker?markets={chunk}") or []
        out += [(x["market"], x.get("acc_trade_price_24h", 0)) for x in t]
        time.sleep(0.2)
    out.sort(key=lambda x: -x[1])
    return [m for m, _ in out[:n]], dict(out)


def fetch_1h(market, bars=1400):
    """1시간봉. 200개씩 끊어서 과거로 거슬러 올라간다."""
    rows, to = [], None
    while len(rows) < bars:
        u = f"{UP}/candles/minutes/60?market={market}&count=200"
        if to:
            u += f"&to={to}"
        r = _get(u)
        if not r:
            break
        rows += r
        to = r[-1]["candle_date_time_utc"]
        if len(r) < 200:
            break
        time.sleep(0.12)
    if not rows:
        return None
    df = pd.DataFrame(rows)[["candle_date_time_kst", "opening_price", "high_price",
                             "low_price", "trade_price", "candle_acc_trade_price"]]
    df.columns = ["dt", "open", "high", "low", "close", "value"]
    df["dt"] = pd.to_datetime(df["dt"])
    return df.drop_duplicates("dt").sort_values("dt").set_index("dt")


def cmd_fetch(args):
    mkts, vol = top_markets(args.n)
    print(f"[universe] 거래대금 상위 {len(mkts)}개")
    cache = pickle.load(open(PX, "rb")) if os.path.exists(PX) else {}
    for i, m in enumerate(mkts + ["KRW-BTC"]):
        if m in cache and len(cache[m]) >= 1300:
            continue
        d = fetch_1h(m)
        if d is not None and len(d) >= 200:
            cache[m] = d
        if (i + 1) % 10 == 0:
            print(f"[fetch] {i+1}/{len(mkts)}  {m} {len(cache.get(m, []))}봉", flush=True)
            pickle.dump((cache, vol), open(PX, "wb"))
    pickle.dump((cache, vol), open(PX, "wb"))
    span = max(len(v) for v in cache.values())
    print(f"[fetch] 완료 {len(cache)}종목, 최장 {span}봉 (~{span/24:.0f}일)")


def indicators(df):
    c, h, l = df["close"], df["high"], df["low"]
    ma = c.rolling(MA_TREND).mean()
    dc = h.rolling(DC_ENTRY).max().shift(1)
    pc = c.shift()
    tr = (h - l).combine((h - pc).abs(), max).combine((l - pc).abs(), max)
    atr = tr.rolling(ATR_N).mean()
    mom = c / c.shift(MOM_LB) - 1
    return pd.DataFrame({"close": c, "high": h, "ma": ma, "dc": dc,
                         "atr": atr, "mom": mom})


def btc_regime(_unused=None):
    """BTC 일봉 종가 > 일봉 ma50 → 위험선호.

    ⚠️ 1시간봉을 일봉으로 리샘플하면 안 된다 — 수집 구간이 58일이라 ma50이
    대부분 NaN이 되고 국면이 통째로 False로 깔린다(그러면 거래가 0건이 되어
    '전략이 안 통한다'는 착시가 생긴다). **일봉을 따로 받는다.**"""
    r = _get(f"{UP}/candles/days?market=KRW-BTC&count=200") or []
    d = pd.DataFrame(r)[["candle_date_time_kst", "trade_price"]]
    d.columns = ["dt", "close"]
    d["dt"] = pd.to_datetime(d["dt"]).dt.normalize()
    d = d.drop_duplicates("dt").sort_values("dt").set_index("dt")["close"]
    ma = d.rolling(50).mean()
    return (d > ma)


def simulate(ind, regime, mult, universe):
    """젯슨 로직 그대로. 반환: 거래 리스트."""
    cal = sorted(set().union(*[set(ind[m].index) for m in universe]))
    pos, trades = {}, []
    for ts in cal:
        day = ts.normalize()
        # 청산
        for m in list(pos):
            if ts not in ind[m].index:
                continue
            r = ind[m].loc[ts]
            if np.isnan(r["atr"]):
                continue
            p = pos[m]
            p["peak"] = max(p["peak"], float(r["close"]))
            if float(r["close"]) <= p["peak"] - mult * float(r["atr"]):
                ret = (float(r["close"]) / p["buy"] - 1) * 100 - FEE * 100
                trades.append({"m": m, "ret": ret,
                               "hours": (ts - p["ts"]).total_seconds() / 3600,
                               "in": p["ts"], "out": ts})
                del pos[m]
        if len(pos) >= MAX_POS:
            continue
        if not bool(regime.get(day, False)):
            continue
        # 진입 후보
        cands = []
        for m in universe:
            if m in pos or ts not in ind[m].index:
                continue
            r = ind[m].loc[ts]
            if any(np.isnan(r[k]) for k in ("ma", "dc", "atr", "mom")):
                continue
            if float(r["close"]) > float(r["dc"]) and float(r["close"]) > float(r["ma"]):
                cands.append((float(r["mom"]), m, float(r["close"])))
        cands.sort(reverse=True)
        for _, m, px in cands:
            if len(pos) >= MAX_POS:
                break
            pos[m] = {"buy": px, "peak": px, "ts": ts}
    return trades


def stats(tr):
    if not tr:
        return None
    r = np.array([t["ret"] for t in tr])
    w, l = r[r > 0], r[r <= 0]
    pf = (w.sum() / abs(l.sum())) if len(l) and l.sum() != 0 else float("inf")
    return {"n": len(r), "win": 100 * len(w) / len(r), "sum": r.sum(),
            "avg_w": w.mean() if len(w) else 0, "avg_l": l.mean() if len(l) else 0,
            "pf": pf, "krw": r.sum() / 100 * BUY_AMOUNT,
            "hold": np.mean([t["hours"] for t in tr])}


def cmd_sweep(args):
    cache, vol = pickle.load(open(PX, "rb"))
    ind = {m: indicators(d) for m, d in cache.items() if len(d) >= 200}
    regime = btc_regime()
    ranked = [m for m, _ in sorted(vol.items(), key=lambda x: -x[1]) if m in ind]
    span = max(len(d) for d in cache.values())
    print(f"[data] {len(ind)}종목 | 최장 {span}봉 (~{span/24:.0f}일) | "
          f"위험선호 일수 {int(regime.sum())}/{len(regime)}")

    print("\n  트레일 배수(M) × 유니버스 크기 — 누적손익%(거래수/승률%/손익비)")
    print("  " + "-" * 76)
    sizes = args.sizes
    print(f"  {'M':>5} " + "".join(f"{'상위'+str(s):>24}" for s in sizes))
    best = None
    for mult in (1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0):
        row = f"  {mult:>5.1f} "
        for s in sizes:
            uni = ranked[:s]
            st = stats(simulate(ind, regime, mult, uni))
            if not st:
                row += f"{'-':>24}"
                continue
            row += f"{st['sum']:>+9.1f}({st['n']:>3}/{st['win']:>2.0f}/{st['pf']:>4.2f})"
            if best is None or st["sum"] > best[0]["sum"]:
                best = (st, mult, s)
        print(row)
    st, mult, s = best
    print("\n  " + "=" * 76)
    print(f"  최고: M={mult}, 상위{s}종목 | 누적 {st['sum']:+.1f}% "
          f"({st['krw']:+,.0f}원) | {st['n']}거래 승률 {st['win']:.0f}% "
          f"손익비 {st['pf']:.2f}")
    print(f"        평균 승 {st['avg_w']:+.2f}% / 평균 패 {st['avg_l']:+.2f}% | "
          f"평균 보유 {st['hold']:.0f}시간")
    print(f"  현재 젯슨 설정은 M=3.0, 상위 20종목 상당")
    print("  " + "=" * 76)
    print("  ⚠️ 이 구간은 표본이 한정적이고 격자 탐색이라 다중검정 편향이 있다.")
    print("     '현재 설정이 최적인가'를 보는 용도지, 이 숫자를 그대로 기대하면 안 된다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "sweep"])
    ap.add_argument("-n", type=int, default=60)
    ap.add_argument("--sizes", type=int, nargs="+", default=[20, 40, 60],
                    help="비교할 유니버스 크기들")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "sweep": cmd_sweep}[a.cmd](a)
