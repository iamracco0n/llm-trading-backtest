# -*- coding: utf-8 -*-
"""크립토 롱숏 마지막 관문 — **강제청산**을 넣어도 엣지가 남나.

`v6_funding.py`에서 펀딩비·숏가능성을 넣고도 살아남았다(H+20 +9.82%, 비중첩 t=3.7).
이 저장소에서 관문을 통과한 유일한 결과다. 그런데 거기 **청산이 없다.**

숏 다리 개별 포지션 5,595건을 뜯어보면 최악이 **−353.9%**, −100%를 넘는 손실이
**1.06%**였다. 실전에서 그런 일은 일어나지 않는다 — 그 전에 **강제청산**된다.
청산은 손실을 증거금으로 끊어주지만, 동시에 **되돌아올 기회도 끊는다.** 어느 쪽이
큰지는 재봐야 안다.

**이걸 안 넣은 채 "엣지가 있다"고 말하면 그게 아홉 번째 착시가 된다.**

**모델**
  · 포지션마다 격리증거금(isolated). 증거금 = 명목 ÷ 레버리지 L.
  · 숏 청산: 보유구간 **장중 고가**가 진입가 × (1 + 1/L − MMR) 에 닿으면 청산.
    롱 청산: **장중 저가**가 진입가 × (1 − 1/L + MMR) 에 닿으면 청산.
    → 종가만 보면 장중에 터진 청산을 놓친다. 그래서 high/low를 쓴다.
  · 청산 시 손익 = **−100%(증거금 전액)**. 그 뒤 가격이 되돌아와도 복구 없음.
  · 증거금 기준 손익 = L × (가격 변화율), 하한 −100%.
  · 펀딩비는 `v6_funding.py`와 동일 부호 규약으로 반영(롱 −, 숏 +).

**사전 기준(결과 보기 전 고정)**: 청산까지 넣은 뒤에도 검증구간(2025-01~) 중앙값이
**양(+)** 이어야 "실행 가능한 엣지"가 유지된다. 못 넘으면 이 전략도 기각이다.

사용: python3 v6_liquidation.py run
"""
import os
import math
import pickle
import argparse

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, CACHE, TOP_N
from v6_crypto import load_panel, HORIZONS, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND

MMR = 0.005          # 유지증거금률 0.5% (바이낸스 소액 구간 통상값)


def _liq_trigger(lev):
    """청산까지 허용되는 가격 변화폭(비율). L=1이면 0.995, L=2면 0.495."""
    return 1.0 / lev - MMR


def run_leg(entry, exit_px, worst, lev, is_short):
    """증거금 대비 손익%(하한 −100). worst = 숏이면 구간 최고가, 롱이면 최저가."""
    trig = _liq_trigger(lev)
    if is_short:
        liq = worst >= entry * (1 + trig)
        raw = (entry - exit_px) / entry
    else:
        liq = worst <= entry * (1 - trig)
        raw = (exit_px - entry) / entry
    pnl = np.where(liq, -1.0, np.clip(raw * lev, -1.0, None))
    return pnl * 100, liq


def simulate(panel, fac, C, trad, onb, h, lev, use_liq=True):
    """h일 보유 롱숏. 반환: (일자별 포트폴리오 수익 시리즈, 청산건수, 총포지션)."""
    op, cl, hi, lo = panel["open"], panel["close"], panel["high"], panel["low"]
    idx = cl.index
    entry = op.shift(-1)
    exit_ = cl.shift(-h)
    # 보유구간(t+1 ~ t+h) 장중 최고/최저
    hi_w = hi.shift(-h).rolling(1).max()          # 자리표시 — 아래에서 다시 계산
    roll_hi = hi[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1)
    roll_lo = lo[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1)
    fund = (C.shift(-h) - C) * 100

    hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
    lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N

    out, nliq, ntot = {}, 0, 0
    for mask, is_short in ((hi_r, False), (lo_r, True)):
        e = entry.where(mask)
        x = exit_.where(mask)
        w = (roll_lo if not is_short else roll_hi).where(mask)
        ok = e.notna() & x.notna() & w.notna() & (e > 0)
        ev, xv, wv = e.where(ok), x.where(ok), w.where(ok)
        if use_liq:
            pnl, liq = run_leg(ev.values, xv.values, wv.values, lev, is_short)
            nliq += int(np.nansum(np.where(ok.values, liq, 0)))
        else:                                      # 청산 없음(기존 방식)
            raw = ((ev - xv) / ev) if is_short else ((xv - ev) / ev)
            pnl = (raw * lev * 100).values
        ntot += int(ok.values.sum())
        f = fund.where(ok)
        # 롱은 펀딩을 내고(−), 숏은 받는다(+). 증거금 기준이라 레버리지를 곱한다.
        adj = pnl + (f.values * lev if is_short else -f.values * lev)
        out["short" if is_short else "long"] = pd.DataFrame(
            adj, index=idx, columns=cl.columns).where(ok)
    port = pd.concat([out["long"], out["short"]], axis=1).mean(axis=1)
    return port - COST * 2 * lev, nliq, ntot


def cmd_run(args):
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
    s, e = SPLIT["valid"]
    m = (idx >= s) & (idx <= e)

    print(f"\n  저변동성 롱숏 — 강제청산 반영 (검증구간 {s}~)")
    print(f"  증거금 기준 수익률. 청산 트리거: 숏 +{100*_liq_trigger(1):.0f}%(L=1) / "
          f"+{100*_liq_trigger(2):.0f}%(L=2) / +{100*_liq_trigger(3):.0f}%(L=3)\n")
    print(f"  {'구성':<22}{'H+5':>10}{'H+20':>10}{'H+60':>10}{'청산율':>9}")
    print("  " + "-" * 61)

    rows = [("청산 없음(기존, L=1)", 1, False)]
    for lev in (1, 2, 3):
        rows.append((f"청산 반영 L={lev}", lev, True))

    for label, lev, use_liq in rows:
        line = f"  {label:<22}"
        liq_rate = None
        for h in (5, 20, 60):
            port, nliq, ntot = simulate(panel, fac, C, trad, onb, h, lev, use_liq)
            v = port[m].dropna()
            line += f"{v.median():>+10.2f}"
            if h == 20:
                liq_rate = 100 * nliq / max(ntot, 1)
        line += f"{liq_rate:>8.2f}%" if liq_rate is not None else ""
        print(line)

    print("\n  사전 기준: 청산 반영 후에도 검증구간 중앙값이 + 여야 '실행 가능한 엣지' 유지")
    print("  ※ 증거금 기준이라 L이 커지면 수익도 손실도 함께 커진다. "
          "부호와 청산율을 봐야 한다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    a = ap.parse_args()
    cmd_run(a)
