# -*- coding: utf-8 -*-
"""살아남은 세 전략을 합치면 — **예측이 아니라 배분 문제**.

지금 살아있는 전략이 셋인데 **따로 논다**. 그런데 국면 의존성이 서로 다르다:

  장투(KR 추세추종)   상승장에서 벌고 **하락장 −21%**
  크립토 롱숏         마켓뉴트럴 — 하락장과 무관 (같은 2달 +6%)
  코인봇(HTF 추세추종) 상승장 전용, 하락장엔 현금

**장투가 죽는 구간에 크립토 롱숏은 벌었다.** 합치면 낙폭이 줄 수 있는데 한 번도
같이 놓고 본 적이 없다. 이것은 미래를 맞히는 문제가 아니라 **배분 문제**라,
이 저장소가 여덟 번 확인한 "LLM은 예측을 못 한다"는 한계에 걸리지 않는다.

**사전 기준(결과 보기 전 고정)**: 결합이 값어치 있으려면
  (a) 결합 MDD < 개별 전략 중 **가장 나쁜** MDD
  (b) 결합 Sharpe > 개별 전략 중 **가장 좋은** Sharpe
둘 다여야 한다. (a)만 만족하면 그냥 위험을 줄인 것이고(현금 섞어도 됨),
(b)만 만족하면 위험 대비 개선이 아니다.

**일별 수익률 만드는 법**
  · 장투: `trend_regime_backtest.simulate` 자산곡선 → 일별 변화율
  · 크립토 롱숏: 20일 겹침 코호트 북. t의 신호로 t+1~t+20 보유, 매일 1/20씩 새로
    열리므로 정상상태에서 20개가 겹친다. 일별 수익 = 롱 보유비중×일수익 −
    숏 보유비중×일수익 − 펀딩. **포워드 페이퍼(`crypto_ls_paper.py`)와 같은 구조.**
  · 코인봇: 1시간봉 시뮬을 돌리며 **매일 평가액을 기록**(거래 손익을 청산일에
    몰아 찍으면 낙폭이 과소평가된다).

사용: python3 portfolio_mix.py
"""
import pickle

import numpy as np
import pandas as pd

import htf_tune as H
from v6_factor_lab import eval_factor, TOP_N
from v6_crypto import load_panel, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND
from v6_stable_check import STABLE_EXTRA
import trend_regime_backtest as T
from trend_backtest import START_KRW

HOLD = 20


def series_trend():
    """장투(국면필터 MA120 = 젯슨 배포 설정) 일별 수익률."""
    data = T.load_data()
    regime = T.load_regime()
    eq, _ = T.simulate(data, regime, use_regime=True)
    s = pd.Series({pd.Timestamp(t): v for t, v in eq}).sort_index()
    return s.pct_change().dropna()


def series_crypto_ls():
    """크립토 저변동 롱숏, 20일 겹침 코호트 북의 일별 수익률."""
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    keep = pd.Series([c not in set(STABLE_EXTRA) for c in cols], index=cols)
    trad = panel["_tradable"] & keep
    fac = eval_factor(SEEDS[0][1], panel)

    hi = (fac.where(trad).rank(axis=1, ascending=False) <= TOP_N).astype(float)
    lo = (fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N).astype(float)
    # t의 신호 → t+1부터 20일 보유. 매일 1/20씩 새 코호트.
    w_hi = hi.shift(1).rolling(HOLD).sum() / (HOLD * TOP_N)
    w_lo = lo.shift(1).rolling(HOLD).sum() / (HOLD * TOP_N)
    ret = panel["close"].pct_change()
    D = daily_funding(cache, idx, cols)          # 비율(하루치)
    # 롱은 펀딩을 내고(−), 숏은 받는다(+)
    r = ((w_hi * ret).sum(axis=1) - (w_lo * ret).sum(axis=1)
         - (w_hi * D).sum(axis=1) + (w_lo * D).sum(axis=1))
    turn = (w_hi.diff().abs().sum(axis=1) + w_lo.diff().abs().sum(axis=1))
    return (r - turn * COST / 100 / 2).dropna()   # 회전량만큼 비용


def series_coinbot():
    """코인봇(HTF 1시간봉 추세추종) 일별 수익률 — 매일 평가액 기록."""
    cache, vol = pickle.load(open(H.PX, "rb"))
    ind = {m: H.indicators(d) for m, d in cache.items() if len(d) >= 200}
    regime = H.regimes("ma20")                    # 배포된 설정
    uni = [m for m in H.JETSON if m in ind]
    cal = sorted(set().union(*[set(ind[m].index) for m in uni]))
    cash, pos, marks = float(H.BUY_AMOUNT * H.MAX_POS), {}, {}
    for ts in cal:
        for m in list(pos):
            if ts not in ind[m].index:
                continue
            r = ind[m].loc[ts]
            if np.isnan(r["atr"]):
                continue
            p = pos[m]
            c = float(r["close"])
            p["peak"] = max(p["peak"], c)
            if c <= p["peak"] - 3.0 * float(r["atr"]):
                cash += p["qty"] * c * (1 - H.FEE)
                del pos[m]
        if len(pos) < H.MAX_POS and bool(regime.get(ts.normalize(), False)):
            cands = []
            for m in uni:
                if m in pos or ts not in ind[m].index:
                    continue
                r = ind[m].loc[ts]
                if any(np.isnan(r[k]) for k in ("ma", "dc", "atr", "mom")):
                    continue
                c = float(r["close"])
                if c > float(r["dc"]) and c > float(r["ma"]):
                    cands.append((float(r["mom"]), m, c))
            cands.sort(reverse=True)
            for _, m, c in cands:
                if len(pos) >= H.MAX_POS or cash < H.BUY_AMOUNT:
                    break
                q = H.BUY_AMOUNT / c
                cash -= H.BUY_AMOUNT * (1 + H.FEE)
                pos[m] = {"qty": q, "peak": c}
        mv = cash + sum(p["qty"] * float(ind[m].loc[ts, "close"])
                        for m, p in pos.items() if ts in ind[m].index)
        marks[ts.normalize()] = mv
    s = pd.Series(marks).groupby(level=0).last().sort_index()
    return s.pct_change().dropna()


def stats(r, ann=252):
    if len(r) < 30:
        return None
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min()) * 100
    mu = float(r.mean()) * ann
    sd = float(r.std()) * np.sqrt(ann)
    return {"ret": (float(eq.iloc[-1]) - 1) * 100, "ann": mu * 100,
            "vol": sd * 100, "sharpe": mu / sd if sd else 0, "mdd": mdd,
            "n": len(r)}


def main():
    print("[mix] 일별 수익률 생성...")
    S = {}
    S["장투(KR)"] = series_trend()
    print("  장투 완료")
    S["크립토 롱숏"] = series_crypto_ls()
    print("  크립토 롱숏 완료")
    S["코인봇"] = series_coinbot()
    print("  코인봇 완료")

    df = pd.DataFrame(S).dropna()
    print(f"\n  공통 구간 {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)\n")

    print(f"  {'전략':<14}{'수익률%':>10}{'연율%':>9}{'변동성%':>9}"
          f"{'Sharpe':>9}{'MDD%':>9}")
    print("  " + "-" * 60)
    indiv = {}
    for k in df.columns:
        st = stats(df[k])
        indiv[k] = st
        print(f"  {k:<14}{st['ret']:>10.1f}{st['ann']:>9.1f}{st['vol']:>9.1f}"
              f"{st['sharpe']:>9.2f}{st['mdd']:>9.1f}")

    print("\n  ── 상관계수 ──")
    c = df.corr()
    print("  " + "".join(f"{x:>14}" for x in c.columns))
    for i in c.index:
        print(f"  {i:<14}" + "".join(f"{c.loc[i,j]:>14.2f}" for j in c.columns))

    print("\n  ── 결합 ──")
    combos = {"동일비중": np.array([1 / 3] * 3)}
    iv = 1 / df.std()
    combos["역변동성 비중"] = (iv / iv.sum()).values
    print(f"  {'구성':<14}{'수익률%':>10}{'연율%':>9}{'변동성%':>9}"
          f"{'Sharpe':>9}{'MDD%':>9}   비중")
    print("  " + "-" * 76)
    best_sh = max(v["sharpe"] for v in indiv.values())
    worst_mdd = min(v["mdd"] for v in indiv.values())
    for name, w in combos.items():
        r = (df * w).sum(axis=1)
        st = stats(r)
        ok = (st["mdd"] > worst_mdd) and (st["sharpe"] > best_sh)
        print(f"  {name:<14}{st['ret']:>10.1f}{st['ann']:>9.1f}{st['vol']:>9.1f}"
              f"{st['sharpe']:>9.2f}{st['mdd']:>9.1f}   "
              f"{'/'.join(f'{x:.0%}' for x in w)}{'  ★통과' if ok else ''}")
    print(f"\n  사전 기준: 결합 MDD < 개별 최악({worst_mdd:.1f}%) "
          f"**그리고** Sharpe > 개별 최고({best_sh:.2f}) — 둘 다여야 통과")


if __name__ == "__main__":
    main()
