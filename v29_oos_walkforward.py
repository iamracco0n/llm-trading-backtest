# -*- coding: utf-8 -*-
"""v29 — 봉인 구간(2025-01~2026-08)에 **워크포워드**를 적용. 마지막 검증.

━━━ 왜 여는가 ━━━
v28 에서 드러난 것: IS 성적 +177% 는 **그 구간에서 고른 이득**이었고, 공정하게
재니 +45.9%(Sharpe 0.64) 였다. 그리고 순위가 뒤집혔다 —
슬롯 3(지금 돌고 있는 설정)이 최악, 슬롯 5·10 이 나았다.

그런데 v28 도 결국 같은 4년 구간이다. 거기서 "슬롯 5 가 낫다"를 고르면 그것도
고르는 행위다. 그래서 **아무도 손대지 않은 구간에서 한 번만** 확인한다.

━━━ 방법 ━━━
v28 과 **똑같은 절차**. 학습 252일에서 격자를 훑어 그 창의 설정을 고르고,
바로 다음 63일에 적용한다. 다른 점은 **성적을 내는 창이 2025-01 이후**라는 것뿐.
학습 구간은 항상 검증 구간보다 앞선다(미래를 보지 않는다).

⚠️ 이 구간은 v26 에서 한 번, 여기서 한 번 — 두 번째다. 이후로는 닫는다.
   다음 증거는 포워드(실계좌)에서만 나온다.

사용: python3 v29_oos_walkforward.py
"""
import itertools

import numpy as np
import pandas as pd

from v26_us_holdout import build
from v28_walkforward import GRID, TEST, TRAIN, sharpe, sim

OOS_FROM = "2025-01-01"
OOS_TO = "2026-08-31"


def walkforward_oos(ind, slots, combos, idx):
    rets, trades, picks = [], [], []
    stop = idx.searchsorted(pd.Timestamp(OOS_TO))
    a = idx.searchsorted(pd.Timestamp(OOS_FROM)) - TRAIN   # 첫 검증창이 OOS 시작
    while a + TRAIN + TEST <= stop:
        best, best_sr = None, -9e9
        for cfg in combos:
            r, _ = sim(ind, cfg, slots, a, a + TRAIN)      # 학습: 과거만
            sr = sharpe(r)
            if sr > best_sr:
                best, best_sr = cfg, sr
        r, tr = sim(ind, best, slots, a + TRAIN, a + TRAIN + TEST)
        rets.append(r)
        trades += tr
        picks.append((str(idx[a + TRAIN].date()), best))
        a += TEST
    if not rets:
        return None
    all_r = np.concatenate(rets)
    eq = (1 + pd.Series(all_r)).cumprod()
    return {"tot": (eq.iloc[-1] - 1) * 100, "sr": sharpe(all_r),
            "mdd": float((eq / eq.cummax() - 1).min()) * 100,
            "n": len(trades), "picks": picks,
            "avg": float(np.mean(trades)) if trades else 0.0}


def main():
    ind = build()
    idx = ind["cl"].index
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"[v29] 봉인 구간 워크포워드 {OOS_FROM} ~ {OOS_TO}")
    print(f"  학습 {TRAIN}일 → 검증 {TEST}일, 창마다 재선택 | 격자 {len(combos)}개\n")

    # 대조군: 유니버스 동일가중(시장)
    b = ind["bench"]
    b = b[(b.index >= pd.Timestamp(OOS_FROM)) & (b.index <= pd.Timestamp(OOS_TO))]
    bench = (b.iloc[-1] / b.iloc[0] - 1) * 100
    br = b.pct_change().dropna()
    print(f"  {'슬롯':<8}{'누적%':>9}{'Sharpe':>8}{'MDD%':>8}{'거래':>6}{'창':>5}")
    print("  " + "-" * 46)
    res = {}
    for slots in (3, 5, 10):
        r = walkforward_oos(ind, slots, combos, idx)
        res[slots] = r
        print(f"  {slots:<8}{r['tot']:>9.1f}{r['sr']:>8.2f}{r['mdd']:>8.1f}"
              f"{r['n']:>6}{len(r['picks']):>5}")
    print(f"  {'시장(동일가중)':<8}{bench:>7.1f}"
          f"{sharpe(br.values):>8.2f}"
          f"{float((b/b.cummax()-1).min())*100:>8.1f}")

    print(f"\n  ── v28(IS 워크포워드)와 비교 ──")
    print(f"     슬롯3  IS-WF +45.9 / SR 0.64   →  봉인 {res[3]['tot']:+.1f} / SR {res[3]['sr']:.2f}")
    print(f"     슬롯5  IS-WF +148.5 / SR 1.47  →  봉인 {res[5]['tot']:+.1f} / SR {res[5]['sr']:.2f}")
    print(f"     슬롯10 IS-WF +99.7 / SR 1.43   →  봉인 {res[10]['tot']:+.1f} / SR {res[10]['sr']:.2f}")
    print(f"\n  ※ 이 구간은 이제 닫는다. 다음 증거는 실계좌 포워드뿐이다.")


if __name__ == "__main__":
    main()
