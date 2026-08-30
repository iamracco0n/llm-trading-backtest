# -*- coding: utf-8 -*-
"""v13 — 규칙 기반 단타. **왕복 0.4%를 넘는 일간 엣지가 있는가.**

**왜 규칙인가 — 깨끗한 구간이 소진됐다.**
v10/v11을 2026-06~08에 돌리면서 판정자가 그 구간의 KOSPI 경로를 전부 봤다
(1주차 −14.8%, 7월 −25.9%, 8월 −20.7% 마감). 컷오프 이후에 남은 깨끗한 구간이
그것뿐이었으므로 **LLM 단타 시뮬은 이제 오염된다.** 규칙은 판정자의 기억이 개입할
여지가 없으므로 오염과 무관하게 답을 낸다. 그리고 진짜 질문은 이것이다:

    **매일 회전하며 왕복 0.4%를 내고도 남는 엣지가 있는가.**

52거래일이면 비용만 20.8%다. v6에서 LLM이 만든 팩터가 **단타 0/69**로 전멸한 것도
같은 문턱 때문이었다(한국은 거래세 0.18%가 매도마다 붙는다).

**설계**
  · 신호는 t일 종가까지로 계산, 진입은 **t+1 시가**, 청산은 **t+1 종가**(1일 보유).
    2일 보유도 같이 잰다.
  · 매일 신호 상위 N=10 동일가중. 비용 0 / 0.2% / 0.4%로 나눠 본다.
  · **손익분기 비용**(이 비용을 넘으면 적자가 되는 지점)을 같이 보고한다 —
    이것이 "얼마나 싸야 성립하나"의 답이다.

사용: python3 v13_daytrade_rules.py
"""
import os
import pickle

import numpy as np
import pandas as pd

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PX = os.path.join(CACHE, "v10_prices_long.pkl")
TOP_N = 10
MIN_AMT = 3e8          # 20일 평균 거래대금 3억원 이상(거래 가능성)


def panels():
    data = pd.read_pickle(PX)
    op, cl, hi, lo, vo = {}, {}, {}, {}, {}
    for c, d in data.items():
        if c == "_KS11":
            continue
        df = d["df"]
        op[c], cl[c] = df["Open"], df["Close"]
        hi[c], lo[c] = df["High"], df["Low"]
        vo[c] = df["Volume"]
    f = lambda x: pd.DataFrame(x).sort_index()
    return f(op), f(cl), f(hi), f(lo), f(vo), data["_KS11"]["df"]["Close"]


def main():
    op, cl, hi, lo, vo, ks = panels()
    amt20 = (cl * vo).rolling(20).mean()
    tradable = (cl > 0) & (vo > 0) & (amt20 >= MIN_AMT)

    r1 = cl.pct_change()
    r5 = cl / cl.shift(5) - 1
    vr = vo / vo.rolling(20).mean()
    ma20 = cl.rolling(20).mean()
    gap = op.shift(-1) / cl - 1                      # t+1 시가 갭(t 종가 대비)

    sig = {
        "① 5일 급등 상위":      r5.where(tradable),
        "② 5일 급락 상위":      (-r5).where(tradable),
        "③ 당일 급등(전일比)":   r1.where(tradable),
        "④ 당일 급락(전일比)":   (-r1).where(tradable),
        "⑤ 거래량 급증+상승":    (vr * (r1 > 0)).where(tradable),
        "⑥ MA20 이격 하위":     (-(cl / ma20 - 1)).where(tradable),
    }

    # 보유 1일: t+1 시가 매수 → t+1 종가 매도 / 2일: t+2 종가 매도
    # ⚠️ 시가 0/결측과 액면분할 아티팩트를 막는다. 한국은 일일 가격제한폭이 ±30%라
    # 시가→종가가 ±35%를 넘으면 정상 거래가 아니라 데이터 문제다(분할·병합 등).
    # 이걸 안 걸렀더니 총수익이 inf로 나왔다.
    ent = op.shift(-1).where(op.shift(-1) > 0)
    ret1 = (cl.shift(-1) / ent - 1) * 100
    ret2 = (cl.shift(-2) / ent - 1) * 100
    ret1 = ret1.where(ret1.abs() <= 35)
    ret2 = ret2.where(ret2.abs() <= 60)

    idx = cl.index
    m = (idx >= "2024-07-01")
    print(f"\n  구간 {idx[m][0].date()} ~ {idx[m][-1].date()} "
          f"({int(m.sum())}거래일) | 상위 {TOP_N}종목 동일가중")
    print(f"  거래가능 종목/일 평균 {tradable[m].sum(axis=1).mean():.0f}\n")

    print(f"  {'규칙':<20}{'보유':>4}{'거래':>7}{'총수익%':>9}{'승률%':>7}"
          f"{'비용0.2%후':>11}{'비용0.4%후':>11}{'손익분기비용%':>13}")
    print("  " + "-" * 84)
    for name, s in sig.items():
        rank = s.rank(axis=1, ascending=False)
        pick = (rank <= TOP_N)
        for hold, ret in (("1일", ret1), ("2일", ret2)):
            v = ret.where(pick)[m]
            daily = v.mean(axis=1).dropna()
            if len(daily) < 50:
                continue
            n = int(pick[m].sum().sum())
            gross = float(daily.mean())              # 거래당 평균 %
            tot = float(daily.sum())
            win = 100 * float((daily > 0).mean())
            print(f"  {name:<20}{hold:>4}{n:>7,}{tot:>9.1f}{win:>7.1f}"
                  f"{(gross-0.2)*len(daily):>11.1f}{(gross-0.4)*len(daily):>11.1f}"
                  f"{gross:>13.3f}")
    print("\n  ※ '손익분기비용%' = 거래당 평균 총수익. 왕복 비용이 이 값을 넘으면 적자다.")
    print("     한국 실거래 왕복 비용 하한 0.23% (2026년 실제 요율, 슬리피지 별도).")
    print("     내역: 매수수수료 0.015 + 매도수수료 0.015 + 매도 거래세 0.20 = 0.23%")
    print("     ⚠️ 2026-01부터 거래세가 0.15% → 0.20%로 **인상**됐다(금투세 폐지 세수보전).")
    print("        문턱이 올라갔으므로 아래 엣지와의 비교는 더 불리해진다.")


if __name__ == "__main__":
    main()
