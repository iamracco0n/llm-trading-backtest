# -*- coding: utf-8 -*-
"""장투 국면 필터 가속 — 크립토에서 얻은 결론을 국내주식으로 이전 검증.

**왜 이걸 하나.** 같은 날 코인봇에서 국면 필터를 MA50 → MA20으로 바꿔 **누적 +71%,
최대낙폭 −41%**를 얻었다. 결론은 "더 엄격하게가 아니라 **더 빠르게**"였다.

그런데 **장투는 아직 MA120을 쓴다.** 그리고 같은 날 실측에서 그 필터가 하락장
43일 중 **31일(72%)을 통과**시키고 6월 손실을 그대로 다 맞았다. **코인봇이 갖고
있던 병과 같고, 처방은 이미 검증됐다.**

**시장·자산군을 건너뛴 이전 검증**이라는 점이 중요하다. 크립토(24시간, 무기한선물,
1시간봉)와 한국 주식(장중 6시간, 공매도 불가, 일봉)은 구조가 전혀 다르다. 여기서도
같은 방향이 나오면 "빠른 국면 필터가 낫다"는 것이 특정 시장의 우연이 아니라는 뜻이고,
안 나오면 크립토 고유 현상이라는 것을 배운다. 어느 쪽이든 얻는 게 있다.

**후보**: 필터없음(대조군) / MA20 / MA30 / MA60 / MA120(현재).
대조군을 반드시 넣는다 — 크립토에서 필터를 빼면 −71,270원이었다(필터의 값어치가
처음으로 입증됐다). 국내주식에서도 같은지 확인한다.

**사전 기준(결과 보기 전 고정, 크립토와 동일)**
  (a) 전체 수익률이 MA120보다 높다
  (b) 최대낙폭(MDD)이 MA120보다 나쁘지 않다
  (c) **최근 구간(2025~)에서도 MA120보다 낫다**
셋 다여야 채택. (c)가 핵심이다 — 특정 상승장에서만 좋아지는 것은 과최적화다.

사용: python3 trend_regime_sweep.py [--fresh]
"""
import argparse

import pandas as pd
import FinanceDataReader as fdr

import trend_regime_backtest as T


def regime_series(ma, start="2022-01-01"):
    """코스피 지수 종가 > MA(ma) → 위험선호. ma=None이면 항상 허용(대조군)."""
    idx = fdr.DataReader("KS11", start)
    if ma is None:
        return {ts: True for ts in idx.index}
    m = idx["Close"].rolling(ma).mean()
    return (idx["Close"] > m).to_dict()


def yearly_from(equity, year_from):
    """지정 연도 이후 구간의 수익률·MDD만 다시 계산."""
    s = pd.Series({pd.Timestamp(t): v for t, v in equity})
    s = s[s.index.year >= year_from]
    if len(s) < 2:
        return None, None
    peak, mdd = s.iloc[0], 0.0
    for v in s:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return (s.iloc[-1] / s.iloc[0] - 1) * 100, mdd * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="시세 새로 받기")
    a = ap.parse_args()

    data = T.load_data(use_cache=not a.fresh)
    span = sorted(set().union(*[set(d["df"].index) for d in data.values()]))
    print(f"[data] {len(data)}종목 | {span[0].date()} ~ {span[-1].date()}")

    cands = [("필터없음(대조군)", None), ("MA20", 20), ("MA30", 30),
             ("MA60", 60), ("MA120(현재)", 120)]
    rows = []
    for name, ma in cands:
        rg = regime_series(ma)
        eq, tr = T.simulate(data, rg, use_regime=(ma is not None))
        st = T.stat(eq, tr)
        r25, m25 = yearly_from(eq, 2025)
        on = 100 * sum(1 for v in rg.values() if v) / max(len(rg), 1)
        rows.append((name, on, st, r25, m25))

    base = next(r for r in rows if r[0] == "MA120(현재)")
    print(f"\n  {'국면 필터':<18}{'허용일%':>8}{'수익률%':>10}{'MDD%':>9}"
          f"{'매매':>6}{'승률%':>7}{'2025+%':>9}")
    print("  " + "-" * 68)
    for name, on, st, r25, m25 in rows:
        mark = ""
        if name != "MA120(현재)":
            ok = (st["ret"] > base[2]["ret"] and st["mdd"] >= base[2]["mdd"]
                  and r25 is not None and base[3] is not None and r25 > base[3])
            mark = "  ★통과" if ok else ""
        print(f"  {name:<18}{on:>8.0f}{st['ret']:>10.1f}{st['mdd']:>9.1f}"
              f"{st['n']:>6}{st['win']:>7.0f}{(r25 or 0):>9.1f}{mark}")

    print("\n  ── 연도별 수익률% ──")
    yrs = sorted(set().union(*[set(r[2]["yearly"]) for r in rows]))
    print(f"  {'국면 필터':<18}" + "".join(f"{y:>9}" for y in yrs))
    for name, _, st, _, _ in rows:
        print(f"  {name:<18}" + "".join(f"{st['yearly'].get(y, 0):>+9.1f}" for y in yrs))

    print("\n  사전 기준: (a)수익률↑ (b)MDD 악화 없음 (c)2025년 이후에도 개선 — 셋 다")


if __name__ == "__main__":
    main()
