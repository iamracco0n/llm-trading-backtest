# -*- coding: utf-8 -*-
"""소액(예: 10만원)으로 목표액을 노릴 때의 실제 확률 — 트레이드 부트스트랩.

`monthly_target.py`가 '매달 얼마'를 묻는다면, 이쪽은 **'한 번 굴려서 얼마'** 를 묻는다.

왜 포트폴리오 곡선을 안 쓰나: 백테스트는 100만원으로 5종목 분산(종목당 20만)을 가정한다.
10만원이면 한 번에 1종목이라 **분산이 아예 없다** → 결과 분산이 백테스트보다 훨씬 크다.
그래서 자산곡선이 아니라 **개별 트레이드 분포에서 부트스트랩**해야 이 상황을 옳게 모사한다.

출력: 목표(+X원)에 먼저 닿을 확률 vs 손실선(−X원)에 먼저 닿을 확률, 그리고 계속 굴렸을 때
잔고 분포. **평균과 중앙값을 같이 본다** — 급등추격은 평균은 본전인데 중앙값은 폭락하는
전형적 복권 구조라, 평균만 보면 게임을 오해한다.

사용: python3 small_capital.py --capital 100000 --target 30000
"""
import argparse
import numpy as np

import surge_backtest

SEED = 20260803
MAX_TRADES = 50
N_PATHS = 50_000


def analyze(trades, capital, target, label):
    r = np.array([t["ret_pct"] for t in trades]) / 100.0
    up, dn = 1 + target / capital, 1 - target / capital

    print()
    print("=" * 66)
    print(f"  {label} — 실제 트레이드 {len(r)}건의 분포")
    print("=" * 66)
    print(f"  승률 {100*(r>0).mean():.1f}%   평균 {100*r.mean():+.2f}%   "
          f"중앙값 {100*np.median(r):+.2f}%")
    print(f"  최고 {100*r.max():+.0f}%   최악 {100*r.min():+.0f}%")

    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(r), size=(N_PATHS, MAX_TRADES))
    paths = np.cumprod(1 + r[idx], axis=1)

    has_up, has_dn = (paths >= up).any(axis=1), (paths <= dn).any(axis=1)
    hit_up, hit_dn = np.argmax(paths >= up, axis=1), np.argmax(paths <= dn, axis=1)
    up_first = has_up & (~has_dn | (hit_up < hit_dn))
    dn_first = has_dn & (~has_up | (hit_dn < hit_up))

    print(f"\n  {capital:,}원 → {capital+target:,}원(+{target:,}) 먼저 닿을 확률 : "
          f"{100*up_first.mean():.1f}%")
    print(f"  {capital:,}원 → {capital-target:,}원(−{target:,}) 먼저 닿을 확률 : "
          f"{100*dn_first.mean():.1f}%")
    print(f"  {MAX_TRADES}거래 내 어느 쪽도 못 닿음 : {100*(~up_first & ~dn_first).mean():.1f}%")

    fin = paths[:, -1] * capital
    print(f"\n  {MAX_TRADES}거래 후 잔고: 중앙값 {np.median(fin):,.0f}원   "
          f"평균 {fin.mean():,.0f}원   하위25% {np.percentile(fin, 25):,.0f}원")
    print(f"  {MAX_TRADES}거래 후 원금({capital:,}) 이상일 확률: {100*(fin>=capital).mean():.1f}%")
    print("  ↑ 평균은 본전 근처인데 중앙값이 훨씬 낮다 = 소수 대박이 평균을 떠받치는 복권 구조")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=int, default=100_000, help="투입 자본(원)")
    ap.add_argument("--target", type=int, default=30_000, help="목표 수익(원). 같은 크기의 손실선도 함께 계산")
    a = ap.parse_args()

    for slip, lbl in ((0.003, "슬리피지 0.3%(낙관)"), (0.005, "슬리피지 0.5%(소형주 현실)")):
        out = surge_backtest.run(slip=slip)
        if out:
            analyze(out[1], a.capital, a.target, lbl)

    print()
    print("=" * 66)
    print("  전제와 한계")
    print("=" * 66)
    print("  - 트레이드가 독립이라 가정한 부트스트랩(실제론 장세에 따라 몰림)")
    print("  - 표본이 '현재 상장 코스닥'이라 상폐된 작전주가 빠져 있다 → 실제는 더 나쁘다")
    print("  - 소액은 주당 가격 때문에 원하는 금액만큼 못 사는 단수 손실이 추가로 붙는다")


if __name__ == "__main__":
    main()
