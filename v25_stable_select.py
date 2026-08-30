# -*- coding: utf-8 -*-
"""v25 — 선정을 안정화한다. **그리고 OOS 로는 더 이상 인증할 수 없음을 인정한다.**

━━━ 두 가지 문제 ━━━
**문제 1. IS 선정이 불안정하다.** v24 에서 자본만 바꿨더니 다른 조합이 뽑혔고,
하나(A)는 OOS 에서 좋고 하나(B)는 무너졌다. IS 수익으로는 둘이 구분되지 않았다
(A +182~197%, B +108~176%). "IS Sharpe 최고"는 절반만 맞는 규칙이다.

**문제 2. OOS 봉인이 닳았다.** 이 저장소는 2025-01~2026-07 구간을 이미
    v23 1회 + v24 두 자본 2회 + 교차검증 6회 = **최소 9번** 열었다.
봉인 구간의 값어치는 **한 번만 본다**는 데서 나온다. 아홉 번 본 구간에서 통과하는
조합을 고르면 그것은 홀드아웃이 아니라 그냥 두 번째 IS 다.
**그러므로 여기서는 OOS 를 판정에 쓰지 않는다.** 참고로만 찍고, 진짜 검증은 포워드다.

━━━ 안정화 방법: 최악 조각 최대화(maximin) ━━━
IS 를 연도로 3등분한다 — 2022 / 2023 / 2024. 세 해의 성격이 다르다
(2022 하락, 2023 반등, 2024 횡보). 조합마다 **세 조각 각각의 Sharpe** 를 구하고
**그중 최솟값이 가장 큰 조합**을 고른다.

  · "평균이 높은 것"이 아니라 "**최악일 때도 버티는 것**"을 고른다.
  · 한 해에만 반짝한 조합(B 유형)은 최솟값이 낮아 자동 탈락한다.
  · 이 규칙은 **IS 안에서만** 정의된다. OOS 를 안 본다.

⚠️ 이 규칙을 A 가 OOS 에서 좋다는 걸 **본 뒤에** 설계했다는 점을 숨기지 않는다.
   다만 규칙 자체는 'A 를 뽑아라'가 아니라 '국면이 바뀌어도 버티는 것을 뽑아라'는
   일반 원리이고, 판정에 OOS 를 쓰지 않으므로 순환논증은 피한다.
   그래도 이 규칙이 옳다는 증거는 **포워드에서만** 나온다.

사용: python3 v25_stable_select.py --cap 500000
"""
import argparse
import itertools
import pickle

import numpy as np
import pandas as pd

from v24_small_cap import GRID, IS, OOS, bh, build, simulate, stats

FOLDS = [("2022", "2022-01-01", "2022-12-31"),
         ("2023", "2023-01-01", "2023-12-31"),
         ("2024", "2024-01-01", "2024-12-31")]


def main(a):
    ind = build()
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"[v25] 유니버스 {len(ind['codes'])}종목 | 자본 {a.cap:,}원 | "
          f"격자 {len(combos)}개")
    print(f"  IS 조각: " + ", ".join(f"{n}" for n, _, _ in FOLDS))

    rows = []
    for i, cfg in enumerate(combos):
        fold = []
        for _, lo, hi in FOLDS:
            eq, tr = simulate(ind, cfg, lo, hi, a.cap)
            s = stats(eq, tr)
            if s is None or s["n"] < 3:
                fold = None
                break
            fold.append(s)
        if fold:
            sr = [f["sharpe"] for f in fold]
            rows.append({"cfg": cfg, "sr": sr, "worst": min(sr),
                         "mean": float(np.mean(sr)),
                         "n": sum(f["n"] for f in fold)})
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(combos)}", flush=True)

    rows = [r for r in rows if r["n"] >= 20]
    print(f"\n  유효 조합 {len(rows)}개 (세 조각 모두 거래 3건+, 합계 20건+)")
    if not rows:
        return

    rows.sort(key=lambda r: -r["worst"])
    print(f"\n  ── 최악 조각 Sharpe 상위 8 ──")
    print(f"  {'최악SR':>7}{'평균SR':>8}{'거래':>6}  {'2022':>6}{'2023':>7}{'2024':>7}"
          f"  조합")
    for r in rows[:8]:
        print(f"  {r['worst']:>7.2f}{r['mean']:>8.2f}{r['n']:>6}"
              f"{r['sr'][0]:>7.2f}{r['sr'][1]:>7.2f}{r['sr'][2]:>7.2f}  "
              f"dc{r['cfg']['dc']} ma{r['cfg']['ma']} ch{r['cfg']['chand']} "
              f"mom{r['cfg']['mom']} s{r['cfg']['slots']} rg{r['cfg']['regime']}")

    best = rows[0]["cfg"]
    print(f"\n  선정(maximin): {best}")

    # 비교용 — v24 가 IS 수익 최고로 골랐다면 무엇이었나
    print(f"\n  ── 참고: 같은 격자를 'IS 전체 Sharpe 최고'로 고르면 ──")
    alt = []
    for cfg in combos:
        eq, tr = simulate(ind, cfg, *IS, a.cap)
        s = stats(eq, tr)
        if s and s["n"] >= 20:
            alt.append((s["sharpe"], cfg))
    alt.sort(key=lambda x: -x[0])
    print(f"   {alt[0][1]}  (IS SR {alt[0][0]:.2f})")
    print(f"   maximin 과 {'같다' if alt[0][1] == best else '다르다'}")

    # OOS 는 참고만 — 판정에 쓰지 않는다
    eq, tr = simulate(ind, best, *OOS, a.cap)
    s = stats(eq, tr)
    print(f"\n  ── OOS (참고용. 이 구간은 이미 9회 이상 열려 판정 자격이 없다) ──")
    print(f"  {s['tot']:+.1f}%  SR {s['sharpe']:.2f}  MDD {s['mdd']:.1f}%  "
          f"거래 {s['n']}  거래당 {s['avg']:+.2f}%  (KOSPI {bh(ind, *OOS):+.1f}%)")
    print(f"\n  ※ 이 숫자로 '통과/기각'을 선언하지 않는다. 다음은 포워드다.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cap", type=int, default=500_000)
    main(p.parse_args())
