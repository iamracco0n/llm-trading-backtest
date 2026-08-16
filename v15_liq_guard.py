# -*- coding: utf-8 -*-
"""v15 — **청산 위험을 줄여 알파를 되찾는다.**

`v6_liquidation.py`에서 확인한 것: 무레버리지(L=1)에서도 숏 포지션의 **2.65%가
강제청산**되고, 그것이 **알파의 39%(H+20 −1.12%p)**를 가져간다. 펀딩비 다음으로 큰
비용이다.

**착상.** 저변동성 팩터는 "가장 변동성이 큰 것"을 숏한다. 그런데 청산은 코인이 2배가
될 때 일어나므로, **청산당하는 것들이 정확히 그 최상위 변동성 종목**일 가능성이 높다.
그렇다면 숏 바구니에서 **변동성 극단만 제외**하면 알파는 크게 안 잃고 청산만 줄일 수
있다. 이것은 방향 예측이 아니라 **위험 관리**다.

**시험할 가드**
  A. 무가드(현재)
  B. **변동성 상한** — 20일 변동성 상위 x%는 숏 후보에서 제외
  C. **급등 배제** — 직전 5일 수익률이 +x% 이상이면 숏 안 함(이미 튀는 중)
  D. B+C

**사전 기준(결과 보기 전 고정)**: 가드가 값어치 있으려면
  (a) 청산율이 내려가고 **그리고** (b) 검증구간 H+20 순수익(청산 반영)이 무가드보다
  높아야 한다. (a)만 만족하면 그냥 알파를 같이 버린 것이다.

사용: python3 v15_liq_guard.py
"""
import pickle

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, TOP_N
from v6_crypto import load_panel, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND
from v6_stable_check import STABLE_EXTRA
from v6_liquidation import _liq_trigger, MMR


def run(panel, fac, C, trad, onb, h, lev, vol_cap=None, run_cap=None):
    """가드를 적용한 롱숏. 반환 (검증구간 중앙 수익%, 청산율%, 숏 후보수/일)."""
    op, cl, hi, lo = panel["open"], panel["close"], panel["high"], panel["low"]
    idx = cl.index
    entry = op.shift(-1)
    exit_ = cl.shift(-h)
    roll_hi = hi[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1)
    roll_lo = lo[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1)
    fund = (C.shift(-h) - C) * 100

    vol20 = cl.pct_change().rolling(20).std()
    r5 = cl / cl.shift(5) - 1

    short_ok = trad & onb
    if vol_cap is not None:                      # 변동성 상위 vol_cap% 제외
        thr = vol20.quantile(1 - vol_cap, axis=1)
        short_ok = short_ok & vol20.lt(thr, axis=0)
    if run_cap is not None:                      # 직전 5일 급등분 제외
        short_ok = short_ok & (r5 < run_cap)

    hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
    lo_r = fac.where(short_ok).rank(axis=1, ascending=True) <= TOP_N

    trig = _liq_trigger(lev)
    out, nliq, ntot = {}, 0, 0
    for mask, is_short in ((hi_r, False), (lo_r, True)):
        e = entry.where(mask)
        x = exit_.where(mask)
        w = (roll_hi if is_short else roll_lo).where(mask)
        ok = e.notna() & x.notna() & w.notna() & (e > 0)
        ev, xv, wv = e.where(ok).values, x.where(ok).values, w.where(ok).values
        if is_short:
            liq = wv >= ev * (1 + trig)
            raw = (ev - xv) / ev
        else:
            liq = wv <= ev * (1 - trig)
            raw = (xv - ev) / ev
        pnl = np.where(liq, -1.0, np.clip(raw * lev, -1.0, None)) * 100
        if is_short:
            nliq += int(np.nansum(np.where(ok.values, liq, 0)))
            ntot += int(ok.values.sum())
        f = fund.where(ok).values
        adj = pnl + (f * lev if is_short else -f * lev)
        out["s" if is_short else "l"] = pd.DataFrame(adj, index=idx,
                                                     columns=cl.columns).where(ok)
    port = pd.concat([out["l"], out["s"]], axis=1).mean(axis=1) - COST * 2 * lev
    s, e2 = SPLIT["valid"]
    m = (idx >= s) & (idx <= e2)
    return (float(port[m].dropna().median()),
            100 * nliq / max(ntot, 1),
            float(short_ok[m].sum(axis=1).mean()))


def main():
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    keep = pd.Series([c not in set(STABLE_EXTRA) for c in cols], index=cols)
    trad = panel["_tradable"] & keep
    C = daily_funding(cache, idx, cols).cumsum()
    fac = eval_factor(SEEDS[0][1], panel)

    print(f"\n  청산 가드 — 검증구간(2025-01~) H+20, 무레버리지(L=1)")
    print(f"  {'가드':<26}{'순수익%':>9}{'청산율%':>9}{'숏후보/일':>10}")
    print("  " + "-" * 56)
    cfgs = [("A 무가드(현재)", None, None),
            ("B 변동성 상위 5% 제외", 0.05, None),
            ("B 변동성 상위 10% 제외", 0.10, None),
            ("B 변동성 상위 20% 제외", 0.20, None),
            ("C 5일 +30% 급등 제외", None, 0.30),
            ("C 5일 +50% 급등 제외", None, 0.50),
            ("D 상위10% + 급등30% 제외", 0.10, 0.30)]
    base = None
    for name, vc, rc in cfgs:
        md, lq, n = run(panel, fac, C, trad, onb, 20, 1.0, vc, rc)
        if base is None:
            base = (md, lq)
        mark = ""
        if name != "A 무가드(현재)":
            mark = "  ★통과" if (lq < base[1] and md > base[0]) else ""
        print(f"  {name:<26}{md:>+9.2f}{lq:>9.2f}{n:>10.0f}{mark}")
    print("\n  사전 기준: 청산율이 내려가고 **그리고** 순수익이 무가드보다 높아야 통과")
    print("  (청산율만 내려가면 알파를 같이 버린 것이다)")


if __name__ == "__main__":
    main()
