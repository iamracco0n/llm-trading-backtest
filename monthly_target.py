# -*- coding: utf-8 -*-
"""'단타로 매달 커피값' 목표를 백테스트 데이터로 검산한다.

"월 6만원(하루 2천원)만 벌면 된다"처럼 **목표가 작으면 쉬워 보인다.** 하지만 기대수익이
0 이하인 게임에서는 목표 크기와 무관하게 달성되지 않는다. 오히려 작은 목표를 매달
채우려고 매매를 늘리면 비용(수수료+슬리피지)만 선형으로 쌓인다.

이 스크립트는 Phase 1 급등 백테스트의 자산곡선을 월 단위로 쪼개서
  1) 목표액을 벌려면 자본이 얼마나 필요한지
  2) 그 자본으로 실제 몇 %의 달이 목표를 넘겼는지
  3) 그 대가로 최악의 달엔 얼마를 잃는지
를 원(￦) 단위로 보여준다. 퍼센트는 감이 안 오지만 원은 온다.

사용: python3 monthly_target.py [--target 60000]
"""
import argparse
import pandas as pd

import surge_backtest
from surge_backtest import START_KRW


def monthly(equity):
    s = pd.Series({pd.Timestamp(t): v for t, v in equity}).sort_index()
    m = s.resample("M").last()
    first = s.iloc[0]
    prev = pd.concat([pd.Series([first], index=[m.index[0]]), m]).iloc[:-1]
    prev.index = m.index
    return (m / prev - 1) * 100, m


def report(label, equity, target):
    ret_m, _ = monthly(equity)
    ret_m = ret_m.dropna()
    total = (equity[-1][1] / START_KRW - 1) * 100
    months = len(ret_m)
    ann = total * 12 / months if months else 0

    print()
    print("=" * 70)
    print(f"  {label}")
    print("=" * 70)
    print(f"  기간 {months}개월  총수익 {total:+.2f}%  (연환산 {ann:+.2f}%)")
    print(f"  월수익률: 평균 {ret_m.mean():+.2f}%  중앙값 {ret_m.median():+.2f}%  "
          f"최악 {ret_m.min():+.2f}%  최고 {ret_m.max():+.2f}%")
    print(f"  플러스인 달: {(ret_m > 0).sum()}/{months} ({(ret_m > 0).mean()*100:.0f}%)")

    if ann <= 0:
        print(f"\n  ▶ 목표 {target:,}원/월 달성에 필요한 자본: **불가능**")
        print("     연환산 수익이 0 이하 — 자본을 아무리 키워도 기대값이 음수다.")
        print("     자본을 2배로 하면 기대손실도 2배가 된다.")
        return

    need = target * 12 / (ann / 100)
    print(f"\n  ▶ 목표 {target:,}원/월(= 연 {target*12:,}원) 달성에 필요한 자본: 약 {need:,.0f}원")
    hit = (ret_m / 100 * need >= target).mean() * 100
    worst = ret_m.min() / 100 * need
    print(f"     그 자본으로 실제 목표를 넘긴 달: {hit:.0f}%  (나머지 달은 미달·손실)")
    print(f"     최악의 달 손실: {worst:,.0f}원   ← 커피 {abs(worst)/2000:,.0f}잔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=60000, help="월 목표 수익(원)")
    a = ap.parse_args()

    print(f"[목표] 월 {a.target:,}원 (하루 {a.target/30:,.0f}원)")
    for slip, label in ((0.003, "단타(급등추격) — 슬리피지 0.3% 보통"),
                        (0.005, "단타(급등추격) — 슬리피지 0.5% 소형주 현실")):
        out = surge_backtest.run(slip=slip)
        if out:
            report(label, out[0], a.target)

    print()
    print("=" * 70)
    print("  주의: 위 수치조차 낙관적이다")
    print("=" * 70)
    print("  - 유니버스가 '현재 상장 코스닥'이라 그사이 상장폐지된 작전주가 빠져 있다")
    print("    (RESULTS_KR.md 생존편향 경고). 급등추격의 최악 손실이 표본에 없다.")
    print("  - 평균손익이 트레이드당 ~0%라, 총수익 부호는 엣지가 아니라 운의 잔여물이다.")


if __name__ == "__main__":
    main()
