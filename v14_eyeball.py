# -*- coding: utf-8 -*-
"""v14 — **바구니를 눈으로 본다.** 살아남은 전략에 같은 검사를 적용.

스테이블코인 오염(롱 바구니의 53~83% 점유, 알파 1.53%p 부풀림)은 **통계 검정으로
안 잡혔다.** t값도 좋았고 겹침 보정도 통과했다. **무엇이 바구니에 들어갔는지 눈으로
본 것**이 잡아냈다. 그런데 그 기법을 크립토 롱숏에만 썼다.

**아직 안 본 곳**: 장투(4.5년 +150%), 코인봇(3년 +437.8%), 결합 포트폴리오.
셋 다 통계는 통과했지만 스테이블 건도 통계는 통과했었다.

**볼 것**
  1. 장투 — 수익이 몇 종목에 몰렸나. 상위 3종목이 전부면 전략이 아니라 운이다.
  2. 코인봇 — 실제로 무엇을 샀나. 상폐·이상 종목이 섞였나.
  3. 결합 — 무상관(ρ≤0.03)이 **국면별로도** 유지되나. 위기에는 상관이 1로 수렴하는
     것이 보통이고, 그러면 분산 효과가 필요할 때 사라진다.

사용: python3 v14_eyeball.py
"""
import os
import pickle

import numpy as np
import pandas as pd

import htf_tune as H
import trend_regime_backtest as T
from portfolio_mix import series_trend, series_crypto_ls, series_coinbot


def sec1_trend():
    print("\n" + "=" * 70)
    print("  [1] 장투 — 수익이 몇 종목에 몰렸나")
    print("=" * 70)
    data = T.load_data()
    regime = T.load_regime()
    eq, tr = T.simulate(data, regime, use_regime=True)
    if not tr:
        print("  거래 없음"); return
    df = pd.DataFrame(tr)
    df["pnl"] = df["ret_pct"]
    tot = df["pnl"].sum()
    by = df.groupby("name")["pnl"].agg(["sum", "count"]).sort_values("sum",
                                                                    ascending=False)
    print(f"  거래 {len(df)}건 | 종목 {len(by)}개 | 수익률 합 {tot:+.1f}%p")
    print(f"\n  {'종목':<12}{'합%p':>9}{'거래':>5}{'누적비중%':>10}")
    cum = 0.0
    for i, (nm, r) in enumerate(by.head(10).iterrows()):
        cum += r["sum"]
        print(f"  {nm[:11]:<12}{r['sum']:>+9.1f}{int(r['count']):>5}"
              f"{100*cum/tot:>10.1f}")
    top3 = by["sum"].head(3).sum()
    top5 = by["sum"].head(5).sum()
    pos = df[df["pnl"] > 0]["pnl"].sum()
    print(f"\n  상위 3종목이 전체 수익의 {100*top3/tot:.1f}%")
    print(f"  상위 5종목이 전체 수익의 {100*top5/tot:.1f}%")
    print(f"  이익 거래 {len(df[df['pnl']>0])}건 합 {pos:+.1f}%p / "
          f"손실 거래 {len(df[df['pnl']<=0])}건 합 {tot-pos:+.1f}%p")
    print("  → 상위 3종목이 100%를 넘으면 나머지가 순손실이라는 뜻이다.")


def sec2_coinbot():
    print("\n" + "=" * 70)
    print("  [2] 코인봇 — 실제로 무엇을 샀나")
    print("=" * 70)
    cache, vol = pickle.load(open(H.PX, "rb"))
    ind = {m: H.indicators(d) for m, d in cache.items() if len(d) >= 200}
    regime = H.regimes("ma20")
    uni = [m for m in H.JETSON if m in ind]
    tr = H.simulate2(ind, regime, uni)
    if not tr:
        print("  거래 없음"); return
    df = pd.DataFrame(tr)
    tot = df["krw"].sum()
    by = df.groupby("m")["krw"].agg(["sum", "count"]).sort_values("sum",
                                                                 ascending=False)
    print(f"  거래 {len(df)}건 | 종목 {len(by)}개 | 손익 합 {tot:+,.0f}원")
    print(f"\n  {'코인':<14}{'합원':>12}{'거래':>5}{'누적비중%':>10}")
    cum = 0.0
    for m, r in by.head(8).iterrows():
        cum += r["sum"]
        print(f"  {m.replace('KRW-',''):<14}{r['sum']:>+12,.0f}{int(r['count']):>5}"
              f"{100*cum/tot:>10.1f}")
    print("  ── 손실 상위 ──")
    for m, r in by.tail(4).iterrows():
        print(f"  {m.replace('KRW-',''):<14}{r['sum']:>+12,.0f}{int(r['count']):>5}")
    print(f"\n  상위 3코인이 전체 손익의 {100*by['sum'].head(3).sum()/tot:.1f}%")
    # 데이터가 짧은(상장 얼마 안 된) 코인이 섞였나
    short = [m for m in by.index if len(cache[m]) < 3000]
    print(f"  이력 3,000봉(125일) 미만 코인이 거래에 등장: {len(short)}개 "
          f"{[m.replace('KRW-','') for m in short[:8]]}")


def sec3_mix():
    print("\n" + "=" * 70)
    print("  [3] 결합 — 무상관이 국면별로도 유지되나")
    print("=" * 70)
    S = {"장투": series_trend(), "롱숏": series_crypto_ls(), "코인봇": series_coinbot()}
    df = pd.DataFrame(S).dropna()
    print(f"  공통 {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)")

    def show(tag, sub):
        if len(sub) < 30:
            print(f"  {tag:<22} 표본 부족({len(sub)}일)"); return
        c = sub.corr()
        print(f"  {tag:<22} 장투-롱숏 {c.iloc[0,1]:>+5.2f} | "
              f"장투-코인봇 {c.iloc[0,2]:>+5.2f} | 롱숏-코인봇 {c.iloc[1,2]:>+5.2f}"
              f"   ({len(sub)}일)")

    show("전체", df)
    # 국면: 장투(=KOSPI 대리) 하위 20% 하락일 = 위기
    thr = df["장투"].quantile(0.2)
    show("위기(장투 하위20%)", df[df["장투"] <= thr])
    show("평시(나머지)", df[df["장투"] > thr])
    for y in sorted(set(df.index.year)):
        show(f"{y}년", df[df.index.year == y])
    print("\n  → 위기 구간에서 상관이 올라가면 **분산 효과가 필요할 때 사라진다**.")


if __name__ == "__main__":
    sec1_trend()
    sec2_coinbot()
    sec3_mix()
