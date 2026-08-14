# -*- coding: utf-8 -*-
"""② 펀딩률 팩터 — 크립토 캐리. **새 데이터 수집 0.**

**논리.** 무기한선물 펀딩률은 롱·숏 중 어느 쪽이 몰렸는지를 가격이 아니라 **포지션
쏠림**으로 보여준다. 펀딩이 극단적으로 높다 = 롱이 과밀 = 이후 부진, 이라는 것이
문헌의 통상 해석이다. 우리 실측과도 맞물린다 — `v6_funding.py`에서 2025년 대형주
펀딩이 지속 양수라 **롱이 계속 지불**했고, 잡알트는 음수라 **숏도 지불**했다.

**왜 값어치가 있나.** 저변동성은 *가격 변동*에서 나온 팩터다. 펀딩률은 **가격에 없는
정보**(파생 포지션 쏠림)라 성격이 다르다. 겹치지 않으면 합쳐 쓸 수 있고, 겹치면
"저변동성이 사실 캐리였다"는 것을 알게 된다. 어느 쪽이든 얻는다.

**비용 0.** `v6_funding.py`가 이미 362개 심볼의 전체 펀딩 이력을 캐시에 받아뒀다.

**후보 팩터** (전부 부호를 명시한다 — 부호를 헷갈리면 결과가 통째로 뒤집힌다)
  · `carry_neg`   = −(최근 7일 펀딩 합). 펀딩 높은 것을 **숏**, 낮은 것을 **롱**.
                    "롱 과밀 → 이후 부진" 가설 그대로.
  · `carry_pos`   = +(최근 7일 펀딩 합). 반대 방향. **대조군으로 반드시 같이 잰다** —
                    한쪽만 재고 좋으면 채택하는 것은 부호를 사후에 고르는 짓이다.
  · `carry_chg`   = 최근 7일 합 − 직전 7일 합. 쏠림의 *변화*.
  · `lowvol`      = 기존 저변동성(비교 기준선).
  · `lowvol+carry`= 두 팩터의 순위 평균(결합).

**평가**: `v6_funding.py`와 동일한 잣대 — 마켓뉴트럴 롱숏, 펀딩비·숏가능 필터 반영,
겹침 보정 t(h일마다 한 번), 스테이블 제외. 마이닝(2022~2024)/검증(2025~) 분리.

**사전 기준(결과 보기 전 고정)**: 검증구간 중앙값이 **양(+)이고 비중첩 t≥2**.
그리고 **마이닝 구간에서도 같은 부호**여야 한다(구간 과최적화 차단).

사용: python3 v6_carry.py
"""
import math
import pickle

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, TOP_N
from v6_crypto import load_panel, forward_alpha, SPLIT, COST, SEEDS
from v6_funding import daily_funding, fetch_perp_info, FUND
from v6_stable_check import STABLE_EXTRA


def carry_factors(D):
    """일별 펀딩 패널 D로부터 캐리 팩터들을 만든다."""
    w1 = D.rolling(7).sum()
    w2 = D.shift(7).rolling(7).sum()
    return {"carry_neg": -w1, "carry_pos": w1, "carry_chg": w1 - w2}


def rank_avg(a, b):
    """두 팩터의 횡단면 순위 평균(결측은 그 팩터를 무시)."""
    ra = a.rank(axis=1, pct=True)
    rb = b.rank(axis=1, pct=True)
    return pd.concat([ra, rb]).groupby(level=0).mean()


def evaluate(fac, panel, C, trad, onb, period):
    s, e = SPLIT[period]
    idx = panel["close"].index
    m = (idx >= s) & (idx <= e)
    out = {}
    for h in (5, 20, 60):
        a = forward_alpha(panel, h)
        fund = (C.shift(-h) - C) * 100
        hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
        lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N
        hi = (a - fund).where(hi_r).median(axis=1)
        lo = (a - fund).where(lo_r).median(axis=1)
        sp = (hi - lo)[m].dropna() - 2 * COST
        if len(sp) < 30:
            out[h] = (float("nan"), float("nan"))
            continue
        nonov = sp.iloc[::h]
        t = (nonov.mean() / (nonov.std() + 1e-12) * math.sqrt(len(nonov))
             if len(nonov) >= 8 else float("nan"))
        out[h] = (float(sp.median()), float(t))
    return out


def main():
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns

    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    # 스테이블 제외 — 2026-08-11에 잡은 오염. 안 빼면 저변동성 쪽이 부풀려진다.
    keep = pd.Series([c not in set(STABLE_EXTRA) for c in cols], index=cols)
    trad = panel["_tradable"] & keep

    D = daily_funding(cache, idx, cols)
    C = D.cumsum()
    facs = carry_factors(D)
    facs["lowvol"] = eval_factor(SEEDS[0][1], panel)
    facs["lowvol+carry"] = rank_avg(facs["lowvol"], facs["carry_neg"])

    n_fund = int((D != 0).any(axis=0).sum())
    print(f"\n  펀딩 이력이 있는 심볼 {n_fund}개 / 유니버스 {len(cols)}개")
    print(f"  스테이블 제외 후 거래가능 평균 {trad.sum(axis=1).mean():.0f}종목\n")

    order = ["lowvol", "carry_neg", "carry_pos", "carry_chg", "lowvol+carry"]
    label = {"lowvol": "저변동성(기준선)", "carry_neg": "캐리 −(롱과밀→숏)",
             "carry_pos": "캐리 +(대조군)", "carry_chg": "캐리 변화",
             "lowvol+carry": "저변동성+캐리 결합"}
    print(f"  {'팩터':<20}{'구간':<8}" + "".join(f"{'H+'+str(h):>16}" for h in (5, 20, 60)))
    print("  " + "-" * 76)
    res = {}
    for k in order:
        res[k] = {}
        for period in ("mine", "valid"):
            r = evaluate(facs[k], panel, C, trad, onb, period)
            res[k][period] = r
            line = f"  {label[k]:<20}{period:<8}" if period == "mine" else f"  {'':<20}{period:<8}"
            for h in (5, 20, 60):
                md, t = r[h]
                line += f"{md:>+10.2f}(t{t:>4.1f})" if md == md else f"{'n/a':>16}"
            print(line)
        print()

    print("  사전 기준: 검증구간 중앙값 + 이고 비중첩 t≥2, **그리고 마이닝 구간도 같은 부호**")
    print("  ※ 캐리 +/− 를 둘 다 재는 이유: 한쪽만 재고 좋으면 채택하는 것은")
    print("     부호를 사후에 고르는 짓이다. 대조군이 나쁘게 나와야 −쪽 결과를 믿을 수 있다.")


if __name__ == "__main__":
    main()
