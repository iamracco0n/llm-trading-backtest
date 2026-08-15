# -*- coding: utf-8 -*-
"""베이시스 관문 — **현물 봉으로 계산한 롱숏이 무기한선물에서도 성립하나.**

우리 백테스트는 전부 **현물 일봉**으로 계산했다. 그런데 숏은 현물로 못 친다 —
실제로는 **무기한선물**이고, 선물 가격은 현물과 다르다(베이시스). 펀딩이 둘을
붙들어 매지만 완전히 같지는 않고, 특히 변동성이 큰 잡알트에서 벌어진다.
숏 다리가 바로 그 잡알트다.

`v6_funding.py`에서 펀딩 *비용*은 반영했지만 **가격 자체는 여전히 현물**이었다.
비용을 뺀 것과 다른 가격 계열로 매매하는 것은 다른 문제다.

**재는 법**: 바이낸스 무기한선물 일봉을 직접 받아 같은 로직을 다시 돌린다.
  (a) 현물만 — 현재 결과
  (b) 숏만 선물 — 현실에 가장 가깝다(롱은 현물로도 가능)
  (c) 롱·숏 둘 다 선물 — 완전 선물 구현

**사전 기준(결과 보기 전 고정)**: (b)와 (c)에서 검증구간(2025-01~) H+20 롱숏이
**양(+)** 이어야 "실행 가능한 엣지"가 유지된다. 못 넘으면 현물 백테스트가
선물 실행을 대표하지 못한다는 뜻이고, 이 결과는 기각이다.

사용: python3 v6_basis.py fetch    # 선물 일봉 수집(캐시)
      python3 v6_basis.py check    # 판정
"""
import os
import json
import time
import pickle
import argparse
import urllib.request

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, CACHE, TOP_N
from v6_crypto import load_panel, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND
from v6_stable_check import STABLE_EXTRA

FAPI = "https://fapi.binance.com"
FPX = os.path.join(CACHE, "v6_perp_klines.pkl")


def _get(url, tries=4):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=30).read())
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5 * (i + 1))


def fetch_perp_klines(sym, start_ms):
    rows, cur = [], start_ms
    while True:
        r = _get(f"{FAPI}/fapi/v1/klines?symbol={sym}&interval=1d"
                 f"&startTime={cur}&limit=1500")
        if not r:
            break
        rows += r
        if len(r) < 1500:
            break
        cur = r[-1][0] + 1
        time.sleep(0.1)
    if not rows:
        return None
    df = pd.DataFrame(rows).iloc[:, :5]
    df.columns = ["t", "open", "high", "low", "close"]
    df.index = pd.to_datetime(df["t"], unit="ms")
    return df[["open", "high", "low", "close"]].astype(float)


def cmd_fetch(args):
    panel = load_panel(full=True)
    perp = fetch_perp_info()
    syms = [s for s in panel["close"].columns if s in perp]
    cache = pickle.load(open(FPX, "rb")) if os.path.exists(FPX) else {}
    todo = [s for s in syms if s not in cache]
    print(f"[basis] 무기한선물 일봉 수집 {len(todo)}개 (캐시 {len(cache)})")
    t0 = int(pd.Timestamp("2021-11-01").timestamp() * 1000)
    for i, s in enumerate(todo):
        d = fetch_perp_klines(s, t0)
        if d is not None and len(d) >= 100:
            cache[s] = d
        if (i + 1) % 25 == 0:
            print(f"[basis] {i+1}/{len(todo)}  {s} {len(cache.get(s, []))}봉", flush=True)
            pickle.dump(cache, open(FPX, "wb"))
        time.sleep(0.05)
    pickle.dump(cache, open(FPX, "wb"))
    print(f"[basis] 완료 {len(cache)}개")


def build(cache, idx, cols, field):
    df = pd.DataFrame({s: d[field] for s, d in cache.items() if s in cols})
    return df.reindex(index=idx, columns=cols)


def cmd_check(args):
    panel = load_panel(full=True)
    fcache = pickle.load(open(FPX, "rb"))
    fund_cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns

    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    keep = pd.Series([c not in set(STABLE_EXTRA) for c in cols], index=cols)
    trad = panel["_tradable"] & keep
    C = daily_funding(fund_cache, idx, cols).cumsum()
    fac = eval_factor(SEEDS[0][1], panel)

    s_op, s_cl = panel["open"], panel["close"]
    f_op = build(fcache, idx, cols, "open")
    f_cl = build(fcache, idx, cols, "close")

    # 베이시스 크기 자체
    b = (f_cl / s_cl - 1) * 100
    bv = b.where(trad).stack().dropna()
    print(f"\n  선물 일봉 확보 {len(fcache)}개 / 유니버스 {len(cols)}개")
    print(f"  베이시스(선물/현물 − 1, 거래가능 종목·일):")
    print(f"    중앙 {bv.median():+.3f}%  |  절대값 중앙 {bv.abs().median():.3f}%  "
          f"|  95분위 {bv.abs().quantile(0.95):.3f}%")

    st, e = SPLIT["valid"]
    m = (idx >= st) & (idx <= e)

    def ls(long_perp, short_perp, h):
        lo_op = f_op if short_perp else s_op
        lo_cl = f_cl if short_perp else s_cl
        hi_op = f_op if long_perp else s_op
        hi_cl = f_cl if long_perp else s_cl
        fund = (C.shift(-h) - C) * 100
        hi_ret = (hi_cl.shift(-h) / hi_op.shift(-1).where(hi_op.shift(-1) > 0) - 1) * 100
        lo_ret = (lo_cl.shift(-h) / lo_op.shift(-1).where(lo_op.shift(-1) > 0) - 1) * 100
        hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
        lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N
        hi = (hi_ret - fund).where(hi_r).median(axis=1)
        lo = (lo_ret - fund).where(lo_r).median(axis=1)
        sp = (hi - lo)[m].dropna() - 2 * COST
        return float(sp.median()), len(sp)

    print(f"\n  {'구성':<28}{'H+5':>10}{'H+20':>10}{'H+60':>10}")
    print("  " + "-" * 58)
    for label, lp, sp_ in (("(a) 현물만 (현재 결과)", False, False),
                           ("(b) 숏만 선물 (현실적)", False, True),
                           ("(c) 롱·숏 둘 다 선물", True, True)):
        row = f"  {label:<28}"
        for h in (5, 20, 60):
            md, n = ls(lp, sp_, h)
            row += f"{md:>+10.2f}"
        print(row)
    print("\n  사전 기준: (b)·(c)의 H+20이 + 여야 '현물 백테스트가 선물 실행을 대표한다'")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "check"])
    a = ap.parse_args()
    (cmd_fetch if a.cmd == "fetch" else cmd_check)(a)
