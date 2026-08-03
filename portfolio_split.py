# -*- coding: utf-8 -*-
"""반반(50:50) 분산 포트폴리오 — 급등 단타 + 장투를 합치면 낙폭이 줄어드나?

자본 절반씩: 급등(공시 LLM필터, Phase3) + 장투(KOSPI 대형주 추세추종).
두 전략은 성격이 정반대(고변동 복권 vs 안정 코어)라, 상관관계가 낮으면
합산 자산곡선의 MDD가 각각보다 작아진다(=더 부드러운 라이드). 그걸 검증.

균등가중·무레버리지라 각 전략은 자본에 선형 → 자산곡선을 1로 정규화해 0.5:0.5 혼합.
"""
import os
import pickle
import numpy as np
import pandas as pd

from surge_backtest import load_data as load_surge
from surge_dart_backtest import simulate, _catalyst_ts
from dart_data import build_catalyst_dates
import trend_backtest

JUDGE_CACHE = "cache/llm_catalyst_judgments.pkl"
PREP = "cache/phase3_prep.pkl"


def surge_curve(slip=0.003, min_score=50):
    """급등 단타(가능하면 LLM호재 필터, 아니면 키워드) 자산곡선 반환 + 라벨."""
    data = load_surge()
    if os.path.exists(JUDGE_CACHE) and os.path.exists(PREP):
        judg = pickle.load(open(JUDGE_CACHE, "rb"))
        prep = pickle.load(open(PREP, "rb"))
        events, rcepts = prep["events"], prep["rcepts"]
        done = sum(1 for r in rcepts if r in judg)
        if done >= len(rcepts):                       # LLM 판정 완료 → C(LLM호재)
            def bull(rn):
                j = judg.get(rn)
                return bool(j and j["verdict"] == "호재" and j["score"] >= min_score)
            cat = {}
            for code, evs in events.items():
                ds = sorted({d for d, rn, nm in evs if bull(rn)})
                if ds:
                    cat[code] = ds
            s = simulate(data, slip, True, cat)
            return s["equity"], f"급등(LLM호재 {done}/{len(rcepts)})"
    # 폴백: 키워드 촉매(Phase2)
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))
    bgn, end = cal[0].strftime("%Y%m%d"), cal[-1].strftime("%Y%m%d")
    cat = _catalyst_ts(build_catalyst_dates(list(data.keys()), bgn, end))
    s = simulate(data, slip, True, cat)
    return s["equity"], "급등(키워드촉매·LLM대기중)"


def _norm(equity):
    idx = pd.to_datetime([t for t, _ in equity])
    val = np.array([v for _, v in equity], float)
    s = pd.Series(val / val[0], index=idx)
    return s[~s.index.duplicated(keep="last")]


def stats(series):
    peak = series.cummax()
    mdd = (series / peak - 1).min() * 100
    ret = (series.iloc[-1] - 1) * 100
    dr = series.pct_change().dropna()
    vol = dr.std() * np.sqrt(252) * 100
    return ret, mdd, vol


def run(slip=0.003):
    se, se_lbl = surge_curve(slip)
    tr = trend_backtest.run(verbose=False)
    A = _norm(se)                          # 급등
    B = _norm(tr["equity"])                # 장투
    # 공통 달력으로 정렬(전진채움)
    idx = A.index.union(B.index)
    A = A.reindex(idx).ffill().bfill()
    B = B.reindex(idx).ffill().bfill()
    C = 0.5 * A + 0.5 * B                   # 반반

    corr = A.pct_change().corr(B.pct_change())
    print("=" * 66)
    print(f"  반반 포트폴리오  ({idx[0].date()} ~ {idx[-1].date()})   슬리피지 {slip*100:.1f}%")
    print(f"  구성: 50% {se_lbl}  +  50% 장투(KOSPI 추세추종)")
    print(f"  두 전략 일간수익 상관계수: {corr:+.2f}")
    print("=" * 66)
    print("  구성            수익률%    MDD%    연변동성%")
    print("-" * 66)
    for name, s in [("급등 단타(100%)", A), ("장투(100%)", B), ("★ 반반 50:50", C)]:
        r, m, v = stats(s)
        print(f"  {name:<16} {r:>7.2f} {m:>8.2f} {v:>10.1f}")
    print("=" * 66)
    ra, ma, _ = stats(A); rb, mb, _ = stats(B); rc, mc, _ = stats(C)
    print(f"  낙폭: 반반 {mc:.1f}%  vs  단순평균 {(ma+mb)/2:.1f}%  → 분산효과 {(ma+mb)/2 - mc:+.1f}%p")
    print("=" * 66)


if __name__ == "__main__":
    run()
