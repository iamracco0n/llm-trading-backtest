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


def fetch_1h(market, bars=1400, before=None):
    """1시간봉. 200개씩 끊어서 과거로 거슬러 올라간다.

    ⚠️ 58일(1400봉)로는 아무것도 판별 못 한다 — 거래가 11~17건이라 한두 건이
    전체를 뒤집는다(M=3.0에서 유니버스만 바꿔도 +51.7 → −6.1 → +0.3 → +50.6).
    **표본을 늘리는 것이 규칙을 바꾸는 것보다 먼저다.** 3년치면 26,000봉,
    거래 표본이 수백 건이 되어 그때부터 비교가 의미를 갖는다."""
    rows = []
    to = (before.strftime("%Y-%m-%dT%H:%M:%S") if before is not None else None)
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
    """--bars 만큼 채운다. 이미 받은 구간은 건드리지 않고 **더 과거만 이어받는다.**"""
    mkts, vol = top_markets(args.n)
    print(f"[universe] 거래대금 상위 {len(mkts)}개 | 목표 {args.bars}봉 "
          f"(~{args.bars/24:.0f}일)")
    old = pickle.load(open(PX, "rb")) if os.path.exists(PX) else ({}, {})
    cache, oldvol = old if isinstance(old, tuple) else (old, {})
    vol = {**oldvol, **vol}
    for i, m in enumerate(mkts + ["KRW-BTC"]):
        have = len(cache.get(m, []))
        if have >= args.bars:
            continue
        d = fetch_1h(m, bars=args.bars,
                     before=cache[m].index[0] if have else None)
        if d is not None:
            cache[m] = (pd.concat([d, cache[m]]).sort_index()
                        .pipe(lambda x: x[~x.index.duplicated()])) if have else d
        print(f"[fetch] {i+1}/{len(mkts)+1}  {m:<14} {have} → {len(cache.get(m, []))}봉",
              flush=True)
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
    rows, to = [], None
    while len(rows) < 1500:                      # 3년+ 확보. 200개만 받으면
        u = f"{UP}/candles/days?market=KRW-BTC&count=200"   # 그 이전이 전부
        if to:                                   # '위험회피'로 깔려 매수가 0이 된다
            u += f"&to={to}"
        r = _get(u)
        if not r:
            break
        rows += r
        to = r[-1]["candle_date_time_utc"]
        if len(r) < 200:
            break
        time.sleep(0.12)
    r = rows
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

# 젯슨에 실제로 배포된 유니버스(2026-08-10 기준 30종목)
JETSON = ["KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE", "KRW-SUI",
          "KRW-SEI", "KRW-ONDO", "KRW-HBAR", "KRW-LINK", "KRW-AVAX", "KRW-APT",
          "KRW-TAO", "KRW-RENDER", "KRW-WIF", "KRW-BONK", "KRW-PEPE", "KRW-NEAR",
          "KRW-WLD", "KRW-XLM", "KRW-ADA", "KRW-ID", "KRW-ENA", "KRW-JTO",
          "KRW-KAITO", "KRW-SAHARA", "KRW-XPL", "KRW-SHIB", "KRW-PENGU", "KRW-ME"]


def cmd_baseline(args):
    """**2단계 — 지금 배포된 규칙 그대로 장기 구간에 돌린다.**

    파라미터를 고르지 않는다. 젯슨에 실제로 도는 설정(M=3.0, Donchian-20,
    ma50 필터, BTC 일봉 MA50 국면, 동시보유 3, 5만원 고정)을 그대로 쓴다.
    여기서 장기 성적이 마이너스면 **파라미터를 어떻게 만져도 안 된다**는 뜻이고,
    ①진입방식 ②초기손절 ③금액고정 을 손볼 필요조차 없다.

    연도별·국면별로 쪼개서 본다 — 전체 합계 하나로는 '어느 장에서 벌었나'를 못 본다.
    """
    cache, vol = pickle.load(open(PX, "rb"))
    ind = {m: indicators(d) for m, d in cache.items() if len(d) >= 200}
    regime = btc_regime()
    uni = [m for m in (JETSON if args.jetson else
                       [m for m, _ in sorted(vol.items(), key=lambda x: -x[1])][:20])
           if m in ind]
    spans = {m: (cache[m].index[0], cache[m].index[-1]) for m in uni}
    lo = min(v[0] for v in spans.values())
    hi = max(v[1] for v in spans.values())
    print(f"[baseline] 유니버스 {len(uni)}종목 | 구간 {lo.date()} ~ {hi.date()} "
          f"| M={args.mult}")
    short = [m for m in uni if len(cache[m]) < 5000]
    if short:
        print(f"  ⚠️ 이력 짧은 종목({len(short)}개): "
              f"{', '.join(m.replace('KRW-','') for m in short[:12])}"
              f"{' ...' if len(short) > 12 else ''}")

    tr = simulate(ind, regime, args.mult, uni)
    st = stats(tr)
    if not st:
        print("  거래 0건"); return

    # 자산곡선(체결 순서대로 복리 아님 — 회당 고정금액이라 단순합)
    tr_sorted = sorted(tr, key=lambda t: t["out"])
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in tr_sorted:
        eq += t["ret"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)

    print("\n  " + "=" * 68)
    print(f"  전체   {st['n']}거래 | 누적 {st['sum']:+.1f}% ({st['krw']:+,.0f}원) "
          f"| 승률 {st['win']:.0f}% | 손익비 {st['pf']:.2f}")
    print(f"         평균 승 {st['avg_w']:+.2f}% / 평균 패 {st['avg_l']:+.2f}% "
          f"| 평균 보유 {st['hold']:.0f}시간 | 최대낙폭 {mdd:.1f}%p")
    print("  " + "=" * 68)

    print("\n  ── 연도별 ──")
    print(f"  {'연도':<8}{'거래':>6}{'누적%':>10}{'승률%':>8}{'손익비':>8}")
    for y in sorted({t["out"].year for t in tr}):
        sub = [t for t in tr if t["out"].year == y]
        s2 = stats(sub)
        print(f"  {y:<8}{s2['n']:>6}{s2['sum']:>+10.1f}{s2['win']:>8.0f}"
              f"{s2['pf']:>8.2f}")

    print("\n  ── 반기별 ──")
    for y in sorted({t["out"].year for t in tr}):
        for h, lab in ((1, "상"), (2, "하")):
            sub = [t for t in tr if t["out"].year == y
                   and ((t["out"].month <= 6) == (h == 1))]
            if not sub:
                continue
            s2 = stats(sub)
            print(f"  {y}{lab}반기  {s2['n']:>4}거래  {s2['sum']:>+8.1f}%  "
                  f"승률 {s2['win']:>3.0f}%  손익비 {s2['pf']:.2f}")

    print(f"\n  BTC 위험선호 일수 {int(regime.sum())}/{len(regime)} "
          f"({100*regime.sum()/len(regime):.0f}%)")
    print("\n  판정: 장기 누적이 마이너스면 파라미터 문제가 아니라 전략 문제다.")

def simulate2(ind, regime, universe, *, trail=3.0, init_stop=None,
              rank="mom", risk_krw=None, fixed_krw=BUY_AMOUNT):
    """개선안 실험용 시뮬레이터. 기본값을 그대로 두면 `simulate()`와 동일하다.

    ① rank   — 후보 정렬. "mom"(현재: 24h 모멘텀 = 제일 펌핑된 것을 산다)
                "quality"(ma50 위 거리 ÷ ATR = 추세 품질) / "liq"(거래대금)
    ② init_stop — 초기 손절 배수(ATR). None이면 현재처럼 트레일만 쓴다.
                진입 직후에도 −trail×ATR을 잃을 수 있는 구조를 좁히는 것.
                스탑 = max(진입−init×ATR, 최고가−trail×ATR)
    ③ risk_krw — 위험 균등 사이징. 지정하면 '스탑까지 거리 = risk_krw'가 되도록
                금액을 정한다(변동성 큰 코인은 적게 산다). None이면 고정 5만원.
    """
    cal = sorted(set().union(*[set(ind[m].index) for m in universe]))
    pos, trades = {}, []
    for ts in cal:
        day = ts.normalize()
        for m in list(pos):
            if ts not in ind[m].index:
                continue
            r = ind[m].loc[ts]
            if np.isnan(r["atr"]):
                continue
            p = pos[m]
            c = float(r["close"])
            p["peak"] = max(p["peak"], c)
            stop = p["peak"] - trail * float(r["atr"])
            if p.get("init") is not None:
                stop = max(stop, p["init"])
            if c <= stop:
                ret = (c / p["buy"] - 1) * 100 - FEE * 100
                trades.append({"m": m, "ret": ret, "krw": p["size"] * ret / 100,
                               "size": p["size"],
                               "hours": (ts - p["ts"]).total_seconds() / 3600,
                               "in": p["ts"], "out": ts})
                del pos[m]
        if len(pos) >= MAX_POS or not bool(regime.get(day, False)):
            continue
        cands = []
        for m in universe:
            if m in pos or ts not in ind[m].index:
                continue
            r = ind[m].loc[ts]
            if any(np.isnan(r[k]) for k in ("ma", "dc", "atr", "mom")):
                continue
            c, atr = float(r["close"]), float(r["atr"])
            if c > float(r["dc"]) and c > float(r["ma"]) and atr > 0:
                key = {"mom": float(r["mom"]),
                       "quality": (c - float(r["ma"])) / atr,
                       "liq": float(r.get("val", 0))}[rank]
                cands.append((key, m, c, atr))
        cands.sort(reverse=True)
        for _, m, c, atr in cands:
            if len(pos) >= MAX_POS:
                break
            stop_dist = (init_stop if init_stop is not None else trail) * atr
            if risk_krw is not None and stop_dist > 0:
                size = min(risk_krw * c / stop_dist, fixed_krw * 3)   # 3배 상한
            else:
                size = fixed_krw
            pos[m] = {"buy": c, "peak": c, "ts": ts, "size": size,
                      "init": (c - init_stop * atr) if init_stop else None}
    return trades


def kstats(tr):
    """원화 기준 통계. 사이징이 변하면 % 합계는 의미가 없다."""
    if not tr:
        return None
    k = np.array([t["krw"] for t in tr])
    w, l = k[k > 0], k[k <= 0]
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in sorted(tr, key=lambda x: x["out"]):
        eq += t["krw"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n": len(k), "krw": k.sum(), "win": 100 * len(w) / len(k),
            "pf": (w.sum() / abs(l.sum())) if len(l) and l.sum() else float("inf"),
            "mdd": mdd, "avg_size": np.mean([t["size"] for t in tr])}


def cmd_improve(args):
    """**3단계 — ①②③을 하나씩 켜서 기준선과 비교.**

    사전 기준(결과 보기 전 고정): 개선으로 인정하려면 **셋 다** 만족해야 한다.
      (a) 3년 누적 원화가 기준선보다 크다
      (b) 최대낙폭(원화)이 기준선보다 나쁘지 않다
      (c) **최근 약세 구간(2025-01~)에서도 기준선보다 낫다**
    (c)가 핵심이다 — 수익의 대부분이 2023하·2024하 두 상승 반기에 몰려 있어서,
    그 구간만 좋아지는 개선은 상승장 과최적화다.
    """
    cache, vol = pickle.load(open(PX, "rb"))
    ind = {m: indicators(d) for m, d in cache.items() if len(d) >= 200}
    regime = btc_regime()
    uni = [m for m in JETSON if m in ind]
    print(f"[improve] 유니버스 {len(uni)}종목 | M=3.0 기준선 대비\n")

    variants = [
        ("기준선(현재 배포)", {}),
        ("① 정렬: 추세품질", {"rank": "quality"}),
        ("② 초기손절 1.5ATR", {"init_stop": 1.5}),
        ("② 초기손절 2.0ATR", {"init_stop": 2.0}),
        ("③ 위험균등 사이징", {"risk_krw": 5000}),
        ("①+② 조합", {"rank": "quality", "init_stop": 1.5}),
        ("①+②+③ 전부", {"rank": "quality", "init_stop": 1.5, "risk_krw": 5000}),
    ]
    base = None
    print(f"  {'구성':<22}{'거래':>6}{'누적원':>11}{'승률%':>7}{'손익비':>7}"
          f"{'최대낙폭':>10}{'2025+':>10}")
    print("  " + "-" * 74)
    for name, kw in variants:
        tr = simulate2(ind, regime, uni, **kw)
        st = kstats(tr)
        recent = kstats([t for t in tr if t["out"] >= pd.Timestamp("2025-01-01")])
        if st is None:
            continue
        if base is None:
            base = (st, recent)
        mark = ""
        if name != "기준선(현재 배포)":
            ok = (st["krw"] > base[0]["krw"] and st["mdd"] >= base[0]["mdd"]
                  and recent and recent["krw"] > base[1]["krw"])
            mark = "  ★통과" if ok else ""
        print(f"  {name:<22}{st['n']:>6}{st['krw']:>+11,.0f}{st['win']:>7.0f}"
              f"{st['pf']:>7.2f}{st['mdd']:>+10,.0f}"
              f"{(recent['krw'] if recent else 0):>+10,.0f}{mark}")
    print("\n  사전 기준: (a)누적↑ (b)낙폭 악화 없음 (c)2025년 이후에도 개선 — 셋 다여야 통과")

def regimes(kind):
    """국면 필터 후보들. 전부 BTC **일봉**으로 만들고 {날짜: bool} 로 돌려준다.

    현재 배포판은 'BTC > MA50' 하나뿐인데 **MA50은 후행**이라 하락이 상당히
    진행된 뒤에야 꺼진다. 같은 문제를 장투에서도 실측했다 — 하락장 43일 중
    31일(72%)을 통과시켰다.

    **none(대조군)을 반드시 넣는다.** '필터가 있어서 좋았다'를 이 저장소는
    한 번도 검증한 적이 없다. 없는 게 나을 수도 있다.
    """
    rows, to = [], None
    while len(rows) < 1500:
        u = f"{UP}/candles/days?market=KRW-BTC&count=200"
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
    d = pd.DataFrame(rows)[["candle_date_time_kst", "trade_price",
                            "high_price", "low_price"]]
    d.columns = ["dt", "close", "high", "low"]
    d["dt"] = pd.to_datetime(d["dt"]).dt.normalize()
    d = d.drop_duplicates("dt").sort_values("dt").set_index("dt")
    c, h, l = d["close"], d["high"], d["low"]
    pc = c.shift()
    tr = (h - l).combine((h - pc).abs(), max).combine((l - pc).abs(), max)
    atr = tr.rolling(14).mean()

    if kind == "none":                                   # E 대조군
        return pd.Series(True, index=c.index)
    if kind == "ma50":                                   # 현재 배포판
        return c > c.rolling(50).mean()
    if kind == "ma30":                                   # A
        return c > c.rolling(30).mean()
    if kind == "ma20":                                   # A
        return c > c.rolling(20).mean()
    if kind == "ma50_up":                                # B  위 + 우상향
        ma = c.rolling(50).mean()
        return (c > ma) & (ma > ma.shift(10))
    if kind == "vol_gate":                               # C  변동성 급등 회피
        ma = c.rolling(50).mean()
        v = atr / c
        return (c > ma) & (v < v.rolling(60).quantile(0.8))
    if kind == "strength":                               # D  추세 강도
        ma = c.rolling(50).mean()
        return (c - ma) / atr > 0.5
    raise ValueError(kind)


def cmd_regime(args):
    """**4단계 — 국면 필터 후보 비교.**

    사전 기준(결과 보기 전 고정, 3단계와 동일):
      (a) 3년 누적 원화가 현재(ma50)보다 크다
      (b) 최대낙폭이 현재보다 나쁘지 않다
      (c) **2025년 이후 약세 구간에서도 현재보다 낫다**
    셋 다여야 통과. 매매 규칙은 배포판 그대로 두고 **국면 필터만** 바꾼다.
    """
    cache, vol = pickle.load(open(PX, "rb"))
    ind = {m: indicators(d) for m, d in cache.items() if len(d) >= 200}
    uni = [m for m in JETSON if m in ind]
    print(f"[regime] 유니버스 {len(uni)}종목 | 매매규칙 고정(M=3.0), 국면만 교체\n")
    order = [("현재 ma50", "ma50"), ("E 필터없음(대조군)", "none"),
             ("A ma30", "ma30"), ("A ma20", "ma20"),
             ("B ma50+우상향", "ma50_up"), ("C 변동성게이트", "vol_gate"),
             ("D 추세강도", "strength")]
    print(f"  {'국면 필터':<20}{'허용일%':>8}{'거래':>6}{'누적원':>11}"
          f"{'승률%':>7}{'손익비':>7}{'최대낙폭':>10}{'2025+':>10}")
    print("  " + "-" * 79)
    base = None
    for name, kind in order:
        rg = regimes(kind)
        tr = simulate2(ind, rg, uni)
        st = kstats(tr)
        rec = kstats([t for t in tr if t["out"] >= pd.Timestamp("2025-01-01")])
        if st is None:
            print(f"  {name:<20}{'거래 0건':>60}")
            continue
        if base is None:
            base = (st, rec)
        mark = ""
        if kind != "ma50":
            ok = (st["krw"] > base[0]["krw"] and st["mdd"] >= base[0]["mdd"]
                  and rec and rec["krw"] > base[1]["krw"])
            mark = "  ★통과" if ok else ""
        print(f"  {name:<20}{100*rg.mean():>8.0f}{st['n']:>6}{st['krw']:>+11,.0f}"
              f"{st['win']:>7.0f}{st['pf']:>7.2f}{st['mdd']:>+10,.0f}"
              f"{(rec['krw'] if rec else 0):>+10,.0f}{mark}")
    print("\n  사전 기준: (a)누적↑ (b)낙폭 악화 없음 (c)2025년 이후에도 개선 — 셋 다여야 통과")

def cmd_detail(args):
    """**적용 전 마지막 확인 — 후보 국면 필터를 연도·반기별로 쪼갠다.**

    전체 합계가 좋아도 특정 해에만 좋은 것이면 못 쓴다. 기준선(ma50)과 나란히
    놓고, **모든 해에서 지지 않는지**를 본다. 3년 재측정에서 수익의 96%가 두
    상승 반기에 몰려 있었으므로 이 확인이 필수다.
    """
    cache, vol = pickle.load(open(PX, "rb"))
    ind = {m: indicators(d) for m, d in cache.items() if len(d) >= 200}
    uni = [m for m in JETSON if m in ind]
    kinds = args.kinds or ["ma50", "ma20"]
    res = {}
    for k in kinds:
        res[k] = simulate2(ind, regimes(k), uni)
    years = sorted({t["out"].year for tr in res.values() for t in tr})

    print(f"[detail] 유니버스 {len(uni)}종목 | 누적 원화\n")
    print(f"  {'구간':<12}" + "".join(f"{k:>14}" for k in kinds))
    print("  " + "-" * (12 + 14 * len(kinds)))
    for y in years:
        row = f"  {y}년{'':<7}"
        for k in kinds:
            st = kstats([t for t in res[k] if t["out"].year == y])
            row += f"{(st['krw'] if st else 0):>+14,.0f}"
        print(row)
    print()
    for y in years:
        for hh, lab in ((1, "상"), (2, "하")):
            row = f"  {y}{lab}반기{'':<4}"
            any_ = False
            for k in kinds:
                sub = [t for t in res[k] if t["out"].year == y
                       and ((t["out"].month <= 6) == (hh == 1))]
                st = kstats(sub)
                if st:
                    any_ = True
                row += f"{(st['krw'] if st else 0):>+14,.0f}"
            if any_:
                print(row)
    print("\n  판정: 어느 해에도 기준선(첫 열)보다 나쁘지 않아야 채택할 수 있다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "sweep", "baseline", "improve", "regime", "detail"])
    ap.add_argument("-n", type=int, default=60)
    ap.add_argument("--bars", type=int, default=1400, help="종목당 목표 봉수")
    ap.add_argument("--mult", type=float, default=3.0, help="트레일 배수")
    ap.add_argument("--jetson", action="store_true", help="젯슨 배포 30종목 사용")
    ap.add_argument("--kinds", nargs="+", help="detail: 비교할 국면 필터들")
    ap.add_argument("--sizes", type=int, nargs="+", default=[20, 40, 60],
                    help="비교할 유니버스 크기들")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "sweep": cmd_sweep, "baseline": cmd_baseline, "improve": cmd_improve, "regime": cmd_regime, "detail": cmd_detail}[a.cmd](a)
