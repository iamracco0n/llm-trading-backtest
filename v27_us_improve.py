# -*- coding: utf-8 -*-
"""v27 — 개선 시도 **실패**. v26 원본을 그대로 쓴다. OOS 는 열지 않았다.

━━━ 결과 ━━━
격자 1536개를 IS 3조각 maximin 으로 훑은 결과, 내가 제안한 개선 둘이 **선택되지 않았다.**

    최고 조합   dc40 ma50 ch3.0 mom20 s3 **동일금액 · 섹터무제한**   최악 SR 0.77
    v26 기준선  dc40 ma120 ch3.0 mom20 s3 동일금액                  최악 SR 0.74

  · **섹터 제한**: 상위 10개 중 **0개**가 사용. 명백히 도움이 안 된다.
  · **ATR 리스크 패리티**: 상위 10 중 6개가 쓰지만 **1위는 안 쓴다.** 우위가 없다.
  · 1위와 기준선의 차이는 ma120 → ma50 하나뿐이고 **최악 Sharpe 0.03 차이**다.
    조각 세 개로 잰 0.03 은 잡음이다.

━━━ ★ 내 사전 기준이 나빴다 ━━━
`best.worst > BASE_WORST` 라는 **단순 부등호**로 통과를 정의했다. 잡음 여유가 없어
0.03 차이도 "★개선 인정"으로 찍힌다. 스크립트는 그렇게 출력했지만 **그 판정을
따르지 않는다.** 3조각 표본에서 Sharpe 0.03 은 개선의 증거가 아니다.
(기준을 지금 고쳐 쓰는 게 아니라, 기준이 나빴음을 기록하고 결론을 보수적으로 낸다.)

**그래서 OOS 를 열지 않았다.** 미장 OOS 는 v26 에서 한 번 열었을 뿐이고, 잡음 수준의
차이를 확인하겠다고 두 번째로 여는 것은 한국 OOS 를 아홉 번 열어 태운 것과 같은 길이다.

━━━ 남는 관찰 (다음에 볼 것, 지금 반영 안 함) ━━━
· 슬롯 5개 조합(dc40 ma120 ch4.0 mom20 s5 위험2%)이 최악 SR 0.64 로 2위권인데,
  슬롯이 많으면 MDD 가 낮아질 가능성이 있다. **maximin-Sharpe 기준은 MDD 를 안 본다** —
  기준 자체의 한계다. 다만 결과를 본 뒤 기준을 바꾸는 것은 하지 않는다.
· 섹터 데이터가 587종목 중 S&P500 503개만 실제 섹터이고 나머지 84개는 각자 다른
  가짜 섹터로 채워졌다. 즉 **섹터 제한이 절반만 작동한 상태**였다. 제대로 붙이면
  달라질 여지는 있으나, 상위 10 중 0개라는 결과는 그 여지를 크게 보지 않게 한다.

━━━ 결론 ━━━
**미장은 v26 설정(dc40 ma120 ch3.0 mom20 s3 regime0)으로 간다.** 바꿀 근거가 없다.

━━━ 이하 원래 설계 ━━━
미장 알고리즘 개선. **IS 안에서만 설계하고 고른다.**

━━━ 규율 먼저 ━━━
미장 OOS(2025-01~2026-08)는 v26 에서 **딱 한 번** 열었다. 한국 OOS 는 아홉 번 열어
봉인이 닳았고, 그래서 한국은 지금 백테스트로 아무것도 결론내지 못한다.
같은 실수를 반복하지 않기 위해 **여기서는 개선안을 IS(2021-09~2024-12)에서만
설계하고 IS 3조각 maximin 으로 고른다.** OOS 는 최종 1개만 마지막에 한 번 본다.

━━━ 무엇을 고치나 (셋 다 '원리'이지 '데이터 맞춤'이 아니다) ━━━

**개선 1. ATR 리스크 패리티 사이징.**
v26 은 슬롯마다 **같은 금액**을 넣는다. 그러면 변동성이 큰 종목이 위험을 훨씬 많이
차지한다 — 3종목 중 하나가 사실상 포트폴리오를 지배할 수 있다. 추세추종의 고전
(터틀 시스템)이 쓰는 방식은 **금액이 아니라 위험을 균등하게** 맞추는 것이다:
    수량 = (자본 × 위험예산) / (ATR × 트레일링 배수)
즉 변동성이 두 배면 절반만 산다. 이건 과거 수익률을 보고 맞춘 값이 아니라
**포지션 간 위험을 같게 만드는 정의**이므로 과최적화가 아니다.

**개선 2. 섹터 집중 제한.**
슬롯 3개를 전부 반도체가 채울 수 있다. 모멘텀 상위는 같은 테마에 몰리는 성질이
있어 실제로 자주 그렇게 된다. 그러면 분산이 3이 아니라 사실상 1이다.
**섹터당 최대 1종목**으로 제한한다.

**개선 3. 슬롯 수 재탐색.**
1·2 를 넣으면 최적 슬롯 수가 달라질 수 있다(위험이 균등해지면 더 많이 담아도
한 종목에 휘둘리지 않는다). 3/5/8/10 을 다시 본다.

━━━ 사전 기준 ━━━
IS 3조각 maximin Sharpe 가 **v26 기준선(최악 0.74)을 넘어야** 개선으로 인정한다.
못 넘으면 개선이 아니라 잡음이므로 **v26 원본을 그대로 쓴다.**
OOS 는 최종 선정 1개에만, 마지막에 한 번.

사용: python3 v27_us_improve.py           # IS 탐색만
      python3 v27_us_improve.py --final   # 최종 1개 OOS 1회 (신중히)
"""
import argparse
import itertools
import pickle

import numpy as np
import pandas as pd

from v26_us_holdout import IS, OOS, PX, COST, ATR_N, FOLDS, bench

GRID = {"dc": [10, 20, 40, 60], "ma": [50, 120], "chand": [2.0, 3.0, 4.0],
        "mom": [20, 60], "slots": [3, 5, 8, 10],
        "risk": [0.0, 0.005, 0.010, 0.02],   # 0 = 동일금액(v26 방식)
        "sector_cap": [0, 1]}                # 1 = 섹터당 1종목
BASE_WORST = 0.74      # v26 선정안의 IS 최악 조각 Sharpe


def sectors(codes):
    """S&P500 섹터. 못 받으면 빈 dict → 섹터 제약이 자동으로 꺼진다."""
    try:
        import FinanceDataReader as fdr
        d = fdr.StockListing("S&P500")
        return {s: str(x) for s, x in zip(d["Symbol"], d["Sector"])}
    except Exception:
        return {}


def build():
    raw = pickle.load(open(PX, "rb"))
    codes = [c for c, v in raw.items() if len(v["df"]) > 300]
    f = lambda k: pd.DataFrame({c: raw[c]["df"][k] for c in codes}).sort_index()
    op, hi, lo, cl = f("Open"), f("High"), f("Low"), f("Close")
    pc = cl.shift(1)
    tr = pd.concat([(hi - lo).stack(), (hi - pc).abs().stack(),
                    (lo - pc).abs().stack()], axis=1).max(axis=1).unstack()
    ind = {"op": op, "hi": hi, "cl": cl, "atr": tr.rolling(ATR_N).mean()}
    ind["dc"] = {d: hi.rolling(d).max().shift(1) for d in GRID["dc"]}
    ind["ma"] = {m: cl.rolling(m).mean() for m in GRID["ma"]}
    ind["mom"] = {m: cl / cl.shift(m) - 1 for m in GRID["mom"]}
    eqw = cl.pct_change().mean(axis=1).add(1).cumprod()
    ind["bench"] = eqw
    ind["codes"] = codes
    sec = sectors(codes)
    ind["sec"] = np.array([sec.get(c, f"_{c}") for c in codes])  # 미상은 각자 다른 섹터
    return ind


def simulate(ind, cfg, lo_d, hi_d, cap=100.0):
    cl = ind["cl"]
    m = (cl.index >= pd.Timestamp(lo_d)) & (cl.index <= pd.Timestamp(hi_d))
    idx = cl.index[m]
    if len(idx) < 60:
        return None, []
    O, H, C = (ind[k].loc[idx].values for k in ("op", "hi", "cl"))
    A = ind["atr"].loc[idx].values
    D = ind["dc"][cfg["dc"]].loc[idx].values
    M = ind["ma"][cfg["ma"]].loc[idx].values
    R = ind["mom"][cfg["mom"]].loc[idx].values
    SEC = ind["sec"]

    slots, chand, risk = cfg["slots"], cfg["chand"], cfg["risk"]
    eq_slot = cap / slots
    cash, pos, eq, trades = float(cap), {}, np.empty(len(idx) - 1), []

    for i in range(len(idx) - 1):
        for j in list(pos):
            p = pos[j]
            if np.isnan(H[i, j]) or np.isnan(A[i, j]):
                continue
            p["peak"] = max(p["peak"], H[i, j])
            if C[i, j] <= p["peak"] - chand * A[i, j]:
                px = O[i + 1, j]
                if not (px > 0):
                    continue
                cash += p["qty"] * px * (1 - COST / 100.0)
                trades.append((px / p["entry"] - 1) * 100 - COST)
                del pos[j]

        if len(pos) < slots:
            nx = O[i + 1]
            ok = ((C[i] > D[i]) & (C[i] > M[i]) & ~np.isnan(R[i])
                  & ~np.isnan(A[i]) & (nx > 0) & (A[i] > 0))
            held_sec = {SEC[j] for j in pos}
            for j in np.argsort(-np.where(ok, R[i], -np.inf)):
                if len(pos) >= slots or not ok[j] or j in pos:
                    if len(pos) >= slots:
                        break
                    continue
                if cfg["sector_cap"] and SEC[j] in held_sec:
                    continue                      # 개선 2: 섹터당 1종목
                if risk > 0:
                    # 개선 1: 위험 균등 — 손절폭(chand×ATR)이 자본의 risk% 가 되게
                    stop = chand * A[i, j]
                    amount = (cap * risk) / (stop / nx[j])
                    amount = min(amount, cash, cap / 2)   # 한 종목이 절반 넘지 않게
                else:
                    amount = min(eq_slot, cash)
                if amount < cash * 0.01 or amount <= 0:
                    continue
                cash -= amount
                pos[j] = {"qty": amount / nx[j], "entry": nx[j], "peak": nx[j]}
                held_sec.add(SEC[j])
        held = sum(p["qty"] * C[i, j] for j, p in pos.items() if not np.isnan(C[i, j]))
        eq[i] = cash + held
    return pd.Series(eq, index=idx[:-1]), trades


def stats(eq, trades):
    if eq is None or len(eq) < 30:
        return None
    r = eq.pct_change().dropna()
    sd = float(r.std())
    return {"tot": (float(eq.iloc[-1] / eq.iloc[0]) - 1) * 100, "n": len(trades),
            "avg": float(np.mean(trades)) if trades else 0.0,
            "mdd": float((eq / eq.cummax() - 1).min()) * 100,
            "sharpe": (float(r.mean()) / sd * np.sqrt(252)) if sd else 0.0}


def main(a):
    ind = build()
    nsec = len(set(ind["sec"]))
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"[v27] 미장 {len(ind['codes'])}종목, 섹터 {nsec}종 | 격자 {len(combos)}개")
    print(f"  IS 3조각 maximin 만으로 고른다. 기준선(v26) 최악 Sharpe {BASE_WORST}")

    rows = []
    for i, cfg in enumerate(combos):
        fold = []
        for _, l, h in FOLDS:
            eq, tr = simulate(ind, cfg, l, h)
            s = stats(eq, tr)
            if s is None or s["n"] < 3:
                fold = None
                break
            fold.append(s["sharpe"])
        if fold:
            rows.append({"cfg": cfg, "worst": min(fold), "sr": fold})
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(combos)}", flush=True)

    rows.sort(key=lambda r: -r["worst"])
    print(f"\n  ── IS 최악 조각 Sharpe 상위 10 ──")
    print(f"  {'최악':>6}  [2022 2023 2024]   설정")
    for r in rows[:10]:
        c = r["cfg"]
        rp = f"위험{c['risk']*100:.1f}%" if c["risk"] else "동일금액"
        sc = "섹터1" if c["sector_cap"] else "섹터무제한"
        print(f"  {r['worst']:>6.2f}  [{r['sr'][0]:.2f} {r['sr'][1]:.2f} "
              f"{r['sr'][2]:.2f}]   dc{c['dc']} ma{c['ma']} ch{c['chand']} "
              f"mom{c['mom']} s{c['slots']} {rp} {sc}")

    best = rows[0]
    imp = best["worst"] > BASE_WORST
    print(f"\n  최고 최악Sharpe {best['worst']:.2f}  vs  v26 기준선 {BASE_WORST}")
    print(f"  → {'★개선 인정' if imp else '개선 아님 — v26 원본을 그대로 쓴다'}")
    if not imp:
        return
    print(f"  선정: {best['cfg']}")

    if not a.final:
        print("\n  ※ OOS 를 열지 않았다. 확정하려면 --final (딱 한 번).")
        return

    eq, tr = simulate(ind, best["cfg"], *OOS)
    s = stats(eq, tr)
    b = bench(ind, *OOS)
    print(f"\n  ══ OOS 1회 ══")
    print(f"  {s['tot']:+.1f}%  SR {s['sharpe']:.2f}  MDD {s['mdd']:.1f}%  "
          f"거래 {s['n']}  거래당 {s['avg']:+.2f}%  | 대조군 {b:+.1f}%")
    print(f"  (v26 원본 OOS: +78.9% SR 1.21 MDD -22.0% 거래 33)")
    print(f"\n  ※ 이제 미장 OOS 도 두 번 열렸다. 더 이상 안 연다.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--final", action="store_true")
    main(p.parse_args())
