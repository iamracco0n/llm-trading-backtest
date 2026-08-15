# -*- coding: utf-8 -*-
"""크립토 롱숏 적대적 감사 — 살아남은 유일한 결과를 의심한다.

**왜.** 이 저장소에서 "엣지가 있다"로 살아있는 주장은 크립토 롱숏 하나뿐이다
(H+20 +8.29%, 비중첩 t 3.2, 관문 5개 통과). 그런데 **스테이블코인 오염을 배포
직전에야 잡았다** — 통계 검정이 아니라 바구니를 눈으로 봐서. 통계가 못 잡는 결함이
더 있을 수 있다고 봐야 한다.

**확인 항목**
  1. 룩어헤드 — `_tradable`이 미래 정보를 쓰나 (코드 검토로 확인: 깨끗)
  2. 롱숏 스프레드가 '시장' 정의에 의존하나 — 의존하면 벤치마크 편향이 결과를 오염시킨다
  3. 숏 바구니 유동성 — 하위 20종목이 실행 불가능한 곳에 몰렸나
  4. 생존편향(롱 다리) — 유니버스가 '오늘 상장 종목'이라 죽은 저변동 코인을 못 담는다
  5. 죽은 코인의 폭락을 숏으로 실제 수확하나 — 데이터가 끊기면 못 먹는다
  6. 무기한선물 상장 직후 구간이 숏 후보에 섞이나

사용: python3 v6_audit.py
"""
import pickle

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, TOP_N
from v6_crypto import load_panel, forward_alpha, SPLIT, COST, SEEDS, DEAD
from v6_funding import daily_funding, fetch_perp_info, FUND
from v6_stable_check import STABLE_EXTRA


def main():
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
    s, e = SPLIT["valid"]
    m = (idx >= s) & (idx <= e)
    hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
    lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N

    print("\n" + "=" * 74)
    print("  크립토 롱숏 적대적 감사")
    print("=" * 74)

    # ── 1. 룩어헤드 (코드 검토 결과 재확인) ──
    print("\n  [1] 룩어헤드")
    print("      _tradable = close>0 & volume>0 & amt20>=$1M & std20>0, 전부 t 시점까지.")
    print("      팩터도 t까지, 진입은 t+1 시가. → 미래 정보 없음. **통과**")

    # ── 2. 스프레드가 '시장' 정의에 의존하나 ──
    h = 20
    a = forward_alpha(panel, h)                       # 종목 − 시장
    op, cl = panel["open"], panel["close"]
    raw = (cl.shift(-h) / op.shift(-1).where(op.shift(-1) > 0) - 1) * 100  # 시장 안 뺌
    sp_a = (a.where(hi_r).median(axis=1) - a.where(lo_r).median(axis=1))[m].dropna()
    sp_r = (raw.where(hi_r).median(axis=1) - raw.where(lo_r).median(axis=1))[m].dropna()
    both = sp_a.index.intersection(sp_r.index)
    diff = (sp_a[both] - sp_r[both]).abs().max()
    print(f"\n  [2] 시장 정의 의존성 (H+{h})")
    print(f"      알파기준 스프레드 중앙 {sp_a.median():+.2f}%  vs  "
          f"원수익률 스프레드 중앙 {sp_r.median():+.2f}%")
    print(f"      두 계열 최대 절대차 {diff:.6f}%p")
    print("      → 롱숏은 시장항이 상쇄되어 **벤치마크 편향과 무관**. 통과"
          if diff < 1e-6 else "      → ⚠️ 차이 있음. 벤치마크 정의가 결과에 영향")

    # ── 3. 숏 바구니 유동성 ──
    amt20 = (panel["close"] * panel["volume"]).rolling(20).mean()
    lo_amt = amt20.where(lo_r)[m].stack().dropna()
    hi_amt = amt20.where(hi_r)[m].stack().dropna()
    uni_amt = amt20.where(trad)[m].stack().dropna()
    print(f"\n  [3] 유동성 (20일 평균 거래대금, 중앙값 USD)")
    print(f"      롱 바구니   {hi_amt.median():>14,.0f}")
    print(f"      숏 바구니   {lo_amt.median():>14,.0f}")
    print(f"      전체 유니버스 {uni_amt.median():>12,.0f}")
    print(f"      숏 하위 5% 분위 {lo_amt.quantile(0.05):>10,.0f}  "
          f"(문턱 $1,000,000)")

    # ── 4. 생존편향: 표본 종료 전에 데이터가 끊긴 종목 ──
    last = panel["close"].apply(lambda c: c.last_valid_index())
    end = idx[-1]
    died = last[last < end - pd.Timedelta(days=30)]
    print(f"\n  [4] 생존편향")
    print(f"      유니버스 {len(cols)}개 중 표본 종료 30일 전에 데이터가 끊긴 종목 "
          f"{len(died)}개")
    print(f"      (수기 DEAD 목록 {len(DEAD)}개 — 실제로 끊긴 것과 비교)")
    in_long = [c for c in died.index if bool(hi_r[c].any())]
    in_short = [c for c in died.index if bool(lo_r[c].any())]
    print(f"      그중 롱 바구니에 들어간 적 있음 {len(in_long)}개 / "
          f"숏 바구니 {len(in_short)}개")
    print("      → 롱 다리는 '오늘까지 살아남은 종목'에서만 뽑힌다. "
          "죽은 저변동 코인은 애초에 후보가 아니다.")

    # ── 5. 죽은 코인의 폭락을 숏으로 수확하나 ──
    exit_ok = cl.shift(-h).notna()
    lo_entries = lo_r[m].sum().sum()
    lo_realized = (lo_r[m] & exit_ok[m]).sum().sum()
    print(f"\n  [5] 숏 포지션 청산 실현율 (H+{h})")
    print(f"      숏 진입 {lo_entries:,}건 중 h일 후 종가가 존재하는 것 "
          f"{lo_realized:,}건 ({100*lo_realized/max(lo_entries,1):.1f}%)")
    print("      → 데이터가 끊긴 코인은 중앙값 계산에서 빠진다. "
          "폭락 수익을 못 먹으므로 **보수적**.")

    # ── 6. 무기한선물 상장 직후 구간 ──
    days_since = pd.DataFrame(np.nan, index=idx, columns=cols)
    for c in cols:
        if c in perp:
            d0 = pd.to_datetime(perp[c], unit="ms")
            days_since[c] = (idx - d0).days
    ds = days_since.where(lo_r)[m].stack().dropna()
    print(f"\n  [6] 숏 후보의 무기한선물 상장 경과일")
    print(f"      중앙 {ds.median():.0f}일 | 30일 미만 비율 {100*(ds<30).mean():.1f}% "
          f"| 7일 미만 {100*(ds<7).mean():.1f}%")
    print("=" * 74)


if __name__ == "__main__":
    main()
