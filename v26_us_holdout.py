# -*- coding: utf-8 -*-
"""v26 — 같은 추세추종을 **미국 시장**에서 검증한다. 파라미터는 다시 찾는다.

━━━ 왜 다시 찾나 ━━━
v22 에서 코인봇(크립토 1시간봉) 파라미터를 한국 일봉에 직역했다가 지수에 10배 졌다.
한국용으로 다시 찾으니(v23~v25) 완전히 다른 값이 나왔다. **미장도 마찬가지다** —
v25 의 값(dc60/ma120/ch4.0/mom20/s3)을 그대로 가져다 쓰면 같은 실수의 세 번째 반복이다.
시장마다 변동성·추세 지속성·갭 빈도가 다르므로 **미장 데이터로 미장 파라미터를 찾는다.**

━━━ 미장이 소자본에 유리한 이유 (구조적) ━━━
토스 Open API 명세: **금액 기반 주문(`orderAmount`)은 US MARKET 전용**이고
소수점 수량도 미국만 된다. 국내는 무조건 1주 단위다.
→ 한국은 10만원/3슬롯이면 슬롯당 33,333원이라 유니버스의 49%만 살 수 있고
  평균 4.9주라 반올림 오차가 크다. **미장은 $70 로도 정확한 비중이 나온다.**

━━━ 비용 (API 실측) ━━━
    한국  수수료 0.015%×2 + 매도 거래세 0.20%  = 왕복 **0.230%**
    미국  수수료 0.1%×2   + SEC/FINRA 극소     = 왕복 **0.200%** + 환전 스프레드
수수료는 미국이 6배 비싸지만 거래세가 없어 왕복은 비슷하다. 환전이 변수다.

━━━ 설계 (v25 와 동일 잣대) ━━━
    유니버스  S&P500 + 나스닥 상위, 587종목
    IS  2021-09 ~ 2024-12   격자 탐색 + **maximin**(연도 3조각 최악 Sharpe 최대화)
    OOS 2025-01 ~ 2026-08   **한 번만** 연다
비용 0.20%. 소수점 매수가 되므로 **1주 단위 제약을 넣지 않는다**(한국과 다른 점).

━━━ 사전 기준 (결과 보기 전 고정) ━━━
  (a) OOS 거래당 평균 순수익 > 0.20%
  (b) OOS 누적 > 같은 구간 **S&P500 매수보유**
  (c) OOS 거래 30건 이상
  (d) IS·OOS Sharpe 동부호
⚠️ 한국(v23)에서 (b)가 강세장에 불리한 기준임을 확인했지만 그대로 둔다.
   결과를 보고 잣대를 고치지 않기 위해서다. 위험조정 수치를 같이 보고한다.

━━━ 한계 ━━━
· 유니버스가 **오늘의 S&P500/나스닥**이라 생존편향이 있다(퇴출 종목 없음).
  미국 대형주는 한국 코스닥보다 퇴출이 드물어 편향은 v24 보다 작을 것이다.
· 환전 스프레드 미반영. 실제로는 여기에 더 든다.
· OOS 를 여기서 처음 연다 — 한국 쪽(2025-01~2026-07)과 달리 아직 깨끗하다.

사용: python3 v26_us_holdout.py --cap 70
"""
import argparse
import itertools
import pickle

import numpy as np
import pandas as pd

PX = "/home/user/llm-trading-backtest/cache/v26_us_px.pkl"
IS = ("2021-09-01", "2024-12-31")
OOS = ("2025-01-01", "2026-08-31")
COST = 0.20
ATR_N = 14

GRID = {"dc": [10, 20, 40, 60], "ma": [20, 50, 120], "chand": [2.0, 3.0, 4.0],
        "mom": [20, 60], "slots": [3, 5, 10], "regime": [20, 60, 0]}
FOLDS = [("2022", "2022-01-01", "2022-12-31"),
         ("2023", "2023-01-01", "2023-12-31"),
         ("2024", "2024-01-01", "2024-12-31")]


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
    # 국면: 지수 대신 **유니버스 동일가중 지수**를 쓴다. SPY 를 따로 받지 않아도
    # 되고, 실제로 우리가 담는 종목들의 국면을 직접 반영한다.
    eqw = cl.pct_change().mean(axis=1).add(1).cumprod()
    ind["bench"] = eqw
    ind["reg"] = {r: (eqw > eqw.rolling(r).mean()) if r else None
                  for r in GRID["regime"]}
    ind["codes"] = codes
    ind["names"] = {c: raw[c]["name"] for c in codes}
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
    reg = ind["reg"][cfg["regime"]]
    on = (reg.reindex(idx).fillna(False).values if reg is not None
          else np.ones(len(idx), bool))

    slots, chand = cfg["slots"], cfg["chand"]
    slot_cap = cap / slots
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
        if on[i] and len(pos) < slots:
            nx = O[i + 1]
            ok = ((C[i] > D[i]) & (C[i] > M[i]) & ~np.isnan(R[i])
                  & ~np.isnan(A[i]) & (nx > 0))
            for j in np.argsort(-np.where(ok, R[i], -np.inf)):
                if len(pos) >= slots or cash < slot_cap * 0.99 or not ok[j]:
                    break
                if j in pos:
                    continue
                px = nx[j]
                # ★ 소수점 매수 — 미장은 orderAmount 로 금액 지정이 된다.
                #   한국처럼 1주 단위로 자르지 않는다.
                cash -= slot_cap
                pos[j] = {"qty": slot_cap / px, "entry": px, "peak": px}
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


def bench(ind, a, b):
    s = ind["bench"]
    s = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
    return (float(s.iloc[-1] / s.iloc[0]) - 1) * 100 if len(s) > 1 else 0.0


def main(a):
    ind = build()
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"[v26] 미장 유니버스 {len(ind['codes'])}종목 | 격자 {len(combos)}개")
    print(f"  IS {IS[0]}~{IS[1]} (maximin 3조각) → OOS {OOS[0]}~{OOS[1]} 1회")

    rows = []
    for i, cfg in enumerate(combos):
        fold = []
        for _, l, h in FOLDS:
            eq, tr = simulate(ind, cfg, l, h, a.cap)
            s = stats(eq, tr)
            if s is None or s["n"] < 3:
                fold = None
                break
            fold.append(s["sharpe"])
        if fold:
            rows.append({"cfg": cfg, "worst": min(fold), "mean": float(np.mean(fold)),
                         "sr": fold})
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(combos)}", flush=True)

    if not rows:
        print("  유효 조합 없음")
        return
    rows.sort(key=lambda r: -r["worst"])
    print(f"\n  ── 최악 조각 Sharpe 상위 6 ──")
    for r in rows[:6]:
        c = r["cfg"]
        print(f"  최악 {r['worst']:>5.2f} 평균 {r['mean']:>5.2f} "
              f"[{r['sr'][0]:.2f} {r['sr'][1]:.2f} {r['sr'][2]:.2f}]  "
              f"dc{c['dc']} ma{c['ma']} ch{c['chand']} mom{c['mom']} "
              f"s{c['slots']} rg{c['regime']}")

    best = rows[0]["cfg"]
    eq_is, tr_is = simulate(ind, best, *IS, a.cap)
    s_is = stats(eq_is, tr_is)
    print(f"\n  선정 {best}")
    print(f"  IS  {s_is['tot']:+.1f}%  SR {s_is['sharpe']:.2f}  "
          f"MDD {s_is['mdd']:.1f}%  거래 {s_is['n']}  거래당 {s_is['avg']:+.2f}%")

    eq, tr = simulate(ind, best, *OOS, a.cap)
    s = stats(eq, tr)
    b = bench(ind, *OOS)
    print(f"\n  ══ OOS (봉인 해제, 1회) ══")
    print(f"  {s['tot']:+.1f}%  SR {s['sharpe']:.2f}  MDD {s['mdd']:.1f}%  "
          f"거래 {s['n']}  거래당 {s['avg']:+.2f}%")
    print(f"  대조군(유니버스 동일가중) {b:+.1f}%")

    ok = [s["avg"] > COST, s["tot"] > b, s["n"] >= 30,
          (s_is["sharpe"] > 0) == (s["sharpe"] > 0)]
    for lab, v in zip(("(a) 거래당>비용 0.20%", "(b) 누적>매수보유",
                       "(c) 거래 30+", "(d) SR 동부호"), ok):
        print(f"  {lab:<22}{'O' if v else 'X'}")
    print(f"  → {'★통과' if all(ok) else '기각'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cap", type=float, default=70.0)   # 약 10만원
    main(p.parse_args())
