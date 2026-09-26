# -*- coding: utf-8 -*-
"""v28 — **워크포워드.** +177% 는 고른 구간에서 잰 값이라 못 믿는다.

━━━ 왜 ━━━
v26 의 설정(dc40/ma120/chand3.0/mom20/slots3)은 IS(2021-09~2024-12)에서 골랐다.
그 구간 성적 +177% 는 **고른 데서 잰 값**이라 실전 기대치가 아니다.
더 나쁜 것은, 그 뒤 익절·손절선·슬롯 비교를 **같은 IS**에서 했다는 점이다.
기준선만 그 구간에 맞춰져 있었으므로 "안 바꾸는 게 낫다"가 나오게 되어 있었다.

━━━ 방법 ━━━
고르는 데이터와 성적 내는 데이터를 **항상 분리**한다:
    [학습 252일] → [검증 63일] → 창을 63일 밀고 반복
각 창마다 학습 구간에서 격자를 훑어 **그 창의 최적 설정**을 새로 고르고,
바로 다음 검증 구간에 적용한다. 검증 구간 수익만 이어 붙인 것이 워크포워드 성적이다.

**변형도 같은 대접을 한다.** 슬롯을 3 으로 고정한 세계, 10 으로 고정한 세계 각각에서
나머지 파라미터를 매 창 새로 고른다. 그래야 공정한 비교다.

봉인 구간(2025-01~)은 쓰지 않는다.

사용: python3 v28_walkforward.py
"""
import itertools
import sys

import numpy as np
import pandas as pd

from v26_us_holdout import COST, build

TRAIN, TEST = 252, 63
WF_START = "2021-09-01"
WF_END = "2024-12-31"

GRID = {"dc": [20, 40, 60], "ma": [50, 120], "chand": [2.0, 3.0, 4.0], "mom": [20, 60]}


def sim(ind, cfg, slots, i0, i1, cap=100.0):
    """idx 위치 [i0, i1) 구간. 반환 (일별수익률 배열, 거래수익 리스트)."""
    cl = ind["cl"]
    O, H, C = (ind[k].values for k in ("op", "hi", "cl"))
    A = ind["atr"].values
    D = ind["dc"][cfg["dc"]].values
    M = ind["ma"][cfg["ma"]].values
    R = ind["mom"][cfg["mom"]].values
    slot = cap / slots
    cash, pos, eq, tr = cap, {}, [], []
    for i in range(i0, min(i1, len(cl) - 1)):
        for j in list(pos):
            p = pos[j]
            if np.isnan(H[i, j]) or np.isnan(A[i, j]):
                continue
            p["pk"] = max(p["pk"], H[i, j])
            if C[i, j] <= p["pk"] - cfg["chand"] * A[i, j]:
                px = O[i + 1, j]
                if not (px > 0):
                    continue
                cash += p["q"] * px * (1 - COST / 100)
                tr.append((px / p["e"] - 1) * 100 - COST)
                del pos[j]
        if len(pos) < slots:
            nx = O[i + 1]
            ok = (C[i] > D[i]) & (C[i] > M[i]) & ~np.isnan(R[i]) & ~np.isnan(A[i]) & (nx > 0)
            for j in np.argsort(-np.where(ok, R[i], -np.inf)):
                if len(pos) >= slots or cash < slot * 0.99 or not ok[j]:
                    break
                if j in pos:
                    continue
                cash -= slot
                pos[j] = {"q": slot / nx[j], "e": nx[j], "pk": nx[j]}
        eq.append(cash + sum(p["q"] * C[i, j] for j, p in pos.items()
                             if not np.isnan(C[i, j])))
    e = pd.Series(eq)
    return e.pct_change().dropna().values, tr


def sharpe(r):
    r = np.asarray(r)
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 5 and r.std() else 0.0


def walkforward(ind, slots, combos, idx):
    """창을 굴리며 학습에서 고르고 검증에서 성적을 낸다."""
    rets, trades, picks = [], [], []
    s0 = idx.searchsorted(pd.Timestamp(WF_START))
    s1 = idx.searchsorted(pd.Timestamp(WF_END))
    a = s0
    while a + TRAIN + TEST <= s1:
        best, best_sr = None, -9e9
        for cfg in combos:
            r, _ = sim(ind, cfg, slots, a, a + TRAIN)
            sr = sharpe(r)
            if sr > best_sr:
                best, best_sr = cfg, sr
        r, tr = sim(ind, best, slots, a + TRAIN, a + TRAIN + TEST)
        rets.append(r)
        trades += tr
        picks.append(best)
        a += TEST
    if not rets:
        return None
    all_r = np.concatenate(rets)
    eq = (1 + pd.Series(all_r)).cumprod()
    return {"tot": (eq.iloc[-1] - 1) * 100, "sr": sharpe(all_r),
            "mdd": float((eq / eq.cummax() - 1).min()) * 100,
            "n": len(trades), "wins": len(picks),
            "avg": float(np.mean(trades)) if trades else 0.0,
            "picks": picks}


def main():
    ind = build()
    idx = ind["cl"].index
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"[v28] 워크포워드 — 학습 {TRAIN}일 → 검증 {TEST}일, {TEST}일씩 전진")
    print(f"  격자 {len(combos)}개 × 창마다 재선택 | 구간 {WF_START} ~ {WF_END}")
    print(f"  ⚠️ 봉인 구간(2025-01~)은 쓰지 않는다\n")
    print(f"  {'슬롯':<7}{'누적%':>9}{'Sharpe':>8}{'MDD%':>8}{'거래':>6}"
          f"{'거래당%':>9}{'창':>5}")
    print("  " + "-" * 54)
    out = {}
    for slots in (3, 5, 10):
        r = walkforward(ind, slots, combos, idx)
        out[slots] = r
        print(f"  {slots:<7}{r['tot']:>9.1f}{r['sr']:>8.2f}{r['mdd']:>8.1f}"
              f"{r['n']:>6}{r['avg']:>9.2f}{r['wins']:>5}")

    print(f"\n  ── 창마다 고른 설정이 얼마나 흔들리나 (슬롯 3) ──")
    for i, c in enumerate(out[3]["picks"], 1):
        print(f"   창{i}: dc{c['dc']} ma{c['ma']} ch{c['chand']} mom{c['mom']}")
    print(f"\n  ※ 같은 데이터에서 고르고 잰 IS 수치(+177%)와 비교할 것.")
    print(f"     워크포워드 값이 실전에 더 가까운 기대치다.")


if __name__ == "__main__":
    main()
