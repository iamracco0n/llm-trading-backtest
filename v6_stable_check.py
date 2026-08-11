# -*- coding: utf-8 -*-
"""열 번째 착시 후보 — 저변동성 롱 바구니에 **스테이블코인**이 들어 있었나.

포워드 페이퍼를 배포하다 롱 바구니가 이렇게 나왔다:

    롱  USDE, U, BFUSD, RLUSD, XUSD, TRX, SPYB, HBAR, WBTC, BNB

USDE·BFUSD·RLUSD·XUSD는 **스테이블코인**이다. 변동성이 0에 가까우니 '저변동성'
팩터가 1등으로 뽑는 게 당연하다. 그런데 **스테이블을 롱하면 수익이 0**이고,
우리 알파는 `종목수익 − 유니버스 동일가중 평균`이라 **시장이 빠지면 자동으로
플러스 알파**가 된다. 즉 마켓뉴트럴이 아니라 **사실상 시장 숏**이며, 하락장이었던
검증구간(2025-01~)에서 좋게 나온 것이 그것으로 설명될 수 있다.

`v6_crypto.STABLE`은 옛 이름(USDC/BUSD/FDUSD/TUSD/DAI/USDP/EUR/GBP/AEUR/USD1)만
막아서 **신규 스테이블이 전부 통과**했다. 백테스트 유니버스 421종목에 실제로
BFUSDUSDT·USDEUSDT·XUSDUSDT가 들어 있다.

**재는 것**: 이들을 빼면 알파가 얼마나 남나. 사전 기준은 그대로 —
검증구간 중앙값이 **양(+)** 이고 비중첩 t≥2 여야 엣지가 유지된다.

사용: python3 v6_stable_check.py
"""
import math
import pickle

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, TOP_N
from v6_crypto import load_panel, forward_alpha, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND

# 가격이 1달러에 고정되도록 설계된 자산(스테이블·랩드 달러). 변동성이 0에 가까워
# '저변동성' 팩터가 무조건 최상위로 뽑지만, 수익도 0이라 알파가 아니라 시장 숏이다.
STABLE_EXTRA = ["BFUSDUSDT", "USDEUSDT", "XUSDUSDT", "RLUSDUSDT", "PYUSDUSDT",
                "USDSUSDT", "FDUSDUSDT", "USDCUSDT", "TUSDUSDT", "DAIUSDT",
                "USDPUSDT", "USD1USDT", "AEURUSDT", "EURIUSDT"]


def _s(x):
    x = pd.Series(x).dropna()
    if len(x) < 20:
        return None
    return len(x), float(x.median()), float(x.mean())


def measure(panel, fac, C, trad, onb, exclude):
    """제외 목록을 반영해 검증구간 롱숏 성적을 낸다."""
    idx, cols = panel["close"].index, panel["close"].columns
    keep = pd.Series([c not in exclude for c in cols], index=cols)
    tr = trad & keep
    s, e = SPLIT["valid"]
    m = (idx >= s) & (idx <= e)
    out = {}
    for h in (5, 20, 60):
        a = forward_alpha(panel, h)
        fund = (C.shift(-h) - C) * 100
        hi_r = fac.where(tr).rank(axis=1, ascending=False) <= TOP_N
        lo_r = fac.where(tr & onb).rank(axis=1, ascending=True) <= TOP_N
        hi = (a - fund).where(hi_r).median(axis=1)
        lo = (a - fund).where(lo_r).median(axis=1)
        sp = (hi - lo)[m].dropna() - 2 * COST
        nonov = sp.iloc[::h]
        t = (nonov.mean() / (nonov.std() + 1e-12) * math.sqrt(len(nonov))
             if len(nonov) >= 8 else float("nan"))
        out[h] = (sp.median(), t, len(sp))
    return out


def main():
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    trad = panel["_tradable"]
    C = daily_funding(cache, idx, cols).cumsum()
    fac = eval_factor(SEEDS[0][1], panel)

    present = [s for s in STABLE_EXTRA if s in cols]
    print(f"\n  유니버스에 실재하는 스테이블: {present}")

    # 롱 바구니(상위 20)에 얼마나 자주 들어갔나
    hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
    s, e = SPLIT["valid"]
    m = (idx >= s) & (idx <= e)
    days = int(m.sum())
    for sym in present:
        if sym in hi_r.columns:
            n = int(hi_r.loc[m, sym].sum())
            print(f"    {sym:<12} 롱 바구니 편입 {n}/{days}일 ({100*n/days:.0f}%)")

    base = measure(panel, fac, C, trad, onb, set())
    excl = measure(panel, fac, C, trad, onb, set(present))

    print(f"\n  검증구간 롱숏 중앙값% (비중첩 t)")
    print(f"  {'구성':<20}{'H+5':>16}{'H+20':>16}{'H+60':>16}")
    print("  " + "-" * 68)
    for label, r in (("포함(기존 결과)", base), ("**스테이블 제외**", excl)):
        line = f"  {label:<20}"
        for h in (5, 20, 60):
            md, t, n = r[h]
            line += f"{md:>+10.2f}(t{t:>4.1f})"
        print(line)
    print("\n  사전 기준: 검증구간 중앙값 + 이고 비중첩 t≥2 — 제외 후에도 유지돼야 한다")


if __name__ == "__main__":
    main()
