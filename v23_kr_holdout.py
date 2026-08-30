# -*- coding: utf-8 -*-
"""v23 — 사전 기준으로는 **기각**. 그런데 기각의 성격이 v22와 전혀 다르다.

━━━ 선정된 조합 ━━━
    {'dc': 20, 'ma': 20, 'chand': 4.0, 'mom': 60, 'slots': 5, 'regime': 20}
    IS 에서 매수보유를 이긴 472/648 중 Sharpe 최고(사전 규칙대로 선정)

━━━ 결과 ━━━
    구간              전략수익%  지수수익%  전략SR  지수SR  전략MDD  지수MDD
    IS  2022~2024      +105.1     −19.7    1.15   −0.33   −20.4   −27.9
    OOS 2025~2026      +160.9    +174.9    2.08    1.75   −21.6   −38.6
    복리 합산(4.5년)    +435.0    +120.7

  사전 기준(OOS)  (a) 거래당 > 비용 0.23%    +21.79%  **O**
                  (b) 누적 > 매수보유        +160.9% vs +174.9%  **X**
                  (c) 거래 30건 이상         37건  **O**
                  (d) IS·OOS Sharpe 동부호   1.15 / 2.08  **O**
                  → **기각** (b 미달)

━━━ ★ 기각을 유지한다. 그러나 기준 (b)가 잘못 설계됐다는 것도 같이 적는다 ━━━
(b)를 통과시키려 기준을 바꾸지 않는다 — 결과를 보고 잣대를 고치는 것이 이 저장소가
가장 경계해온 짓이다. 다만 **(b) 자체가 나쁜 기준이었다**는 것은 사실로 기록한다:

  현금 비중을 갖는 전략의 **한 구간 절대수익**을 매수보유와 비교하면, 전략의 질이
  아니라 **그 구간이 어떤 장이었나**를 재게 된다. 실제로 IS 는 지수 −19.7% 하락장이라
  648개 중 **472개(73%)가 (b)를 통과**했다 — 거의 공짜 관문이었다. 반대로 OOS 는
  지수 +174.9% 강세장이라 현금을 쥐는 전략이 구조적으로 질 수밖에 없었다.
  같은 기준이 한 구간에선 무의미하게 헐겁고 다른 구간에선 거의 불가능했다.

**봉인 구간에서 실제로 관측된 것**(기준 통과 여부와 별개의 사실):
  · Sharpe **2.08 vs 지수 1.75** — 위험조정으로는 지수를 이겼다.
  · MDD **−21.6% vs 지수 −38.6%** — 낙폭이 절반이다.
  · 수익률만 14%p 뒤졌다.
  · 하락장(IS)에서는 지수 −19.7% 일 때 +105.1% 였다.

━━━ 그래서 어떻게 하나 ━━━
**이 OOS 를 새 기준으로 다시 채점하지 않는다.** 이미 본 데이터에 잣대를 맞추면
그 순간 봉인의 의미가 사라진다. 대신 **아무도 안 본 구간 = 포워드**에서
새 기준으로 검증한다. 이 조합은 포워드 후보로서는 정당하다:
  · 파라미터 탐색은 IS 에서만 했고 OOS 는 **조합 하나로 딱 한 번** 열었다.
  · 과최적화 감쇠가 없다(OOS Sharpe 2.08 > IS 1.15). 보통 반대로 나온다.

━━━ 남는 의심 ━━━
· OOS Sharpe 가 IS 보다 **높다**는 건 흔한 일이 아니다. 강세장 운이 섞였을 수 있다.
· 유니버스가 현재 KOSPI 150 이라 **생존편향**이 남는다(추세추종은 과대평가 쪽).
· 슬리피지 0. 슬롯 5개면 회전이 늘어 실제 체결 밀림이 더 크게 작용한다.
· 두 구간 모두 결국 각각 한 번의 국면이다. n=2 로 국면 강건성을 말할 수 없다.

━━━ 이하 원래 설계 ━━━
한국 주식용 추세추종 파라미터를 **봉인 구간으로** 찾는다.

━━━ 왜 ━━━
v22 에서 코인봇 파라미터를 직역했더니 KOSPI 매수보유(+120.7%)에 크게 졌다(+12.7%).
그런데 그 파라미터는 **크립토 1시간봉용**이다 — 24봉 모멘텀이 거기선 하루인데
일봉에선 5주가 된다. 시간축이 안 맞으니 "한국에서 안 된다"가 아니라 "이 값들이
한국에 안 맞는다"일 수 있다. 그래서 한국용 값을 찾아본다.

**그런데 같은 데이터로 찾고 같은 데이터로 검증하면 그건 그냥 과최적화다.**
이 저장소가 v5(실적 PEAD)에서 정확히 그렇게 죽었다 — IS +3.66% 가 OOS −2.60% 였다.
그래서 구간을 갈라 **봉인**한다.

━━━ 설계 ━━━
    IS  2022-01 ~ 2024-12   파라미터 탐색. 여기선 마음껏 뒤진다.
    OOS 2025-01 ~ 2026-07   **봉인.** 최종 1개 조합만 **딱 한 번** 돌린다.

격자 648개(아래 GRID). 격자 크기를 숨기지 않는다 — 648개를 뒤졌다는 사실 자체가
IS 최고 성적을 부풀리므로, 판정은 오직 OOS 로만 한다.

**선정 규칙(결과 보기 전에 고정)**: IS 에서 **매수보유를 이긴 조합들 중 Sharpe 최고**
하나를 고른다. 수익률 최대로 고르면 복권 같은 조합이 뽑히므로 위험조정으로 고른다.

━━━ 사전 기준(OOS, 결과 보기 전에 고정) ━━━
넷 다 만족해야 "한국용 파라미터를 찾았다"가 성립한다:
  (a) OOS 거래당 평균 순수익 > **0.23%**(2026 왕복비용). 비용을 넘는가.
  (b) OOS 누적 > **같은 구간 KOSPI 매수보유**. v22 가 여기서 죽었다.
  (c) OOS 거래 **30건 이상**.
  (d) IS Sharpe 와 OOS Sharpe 가 **같은 부호**. IS 에서만 좋으면 과최적화다.
하나라도 미달이면 기각한다. 부분 통과를 성공으로 포장하지 않는다.

━━━ 한계 ━━━
· 유니버스가 현재 KOSPI 150 이라 **생존편향**이 남는다(상장폐지분 없음).
· 슬리피지 0. 비용은 왕복 0.23% 만 반영.
· OOS 도 결국 한 번의 강세장 구간이다. 통과해도 포워드 검증이 별도로 필요하다.

사용: python3 v23_kr_holdout.py            # 탐색 + OOS 1회
      python3 v23_kr_holdout.py --is-only  # IS 만(봉인 유지)
"""
import argparse
import itertools
import os
import pickle

import numpy as np
import pandas as pd

from v5_oos import CACHE
from v22_htf_kr import PX, _kospi

IS = ("2022-01-01", "2024-12-31")
OOS = ("2025-01-01", "2026-07-31")
COST = 0.23
CAP = 10_000_000
ATR_N = 14
RES = os.path.join(CACHE, "v23_is_results.pkl")

GRID = {
    "dc": [10, 20, 40, 60],
    "ma": [20, 50, 120],
    "chand": [2.0, 3.0, 4.0],
    "mom": [20, 60],
    "slots": [3, 5, 10],
    "regime": [20, 60, 0],        # 0 = 국면필터 없음
}


def build():
    """가격·지표를 **numpy 행렬**로 미리 만든다(날짜 × 종목).

    pandas `.loc` 를 날짜×종목마다 부르면 648개 조합을 도는 것이 불가능하다.
    파라미터 값별로 지표 행렬을 **한 번씩만** 계산해 재사용한다."""
    raw = pickle.load(open(PX, "rb"))
    codes = [c for c, v in raw.items() if len(v["df"]) > 200]
    op = pd.DataFrame({c: raw[c]["df"]["Open"] for c in codes}).sort_index()
    hi = pd.DataFrame({c: raw[c]["df"]["High"] for c in codes}).sort_index()
    lo = pd.DataFrame({c: raw[c]["df"]["Low"] for c in codes}).sort_index()
    cl = pd.DataFrame({c: raw[c]["df"]["Close"] for c in codes}).sort_index()

    pc = cl.shift(1)
    tr = pd.concat([(hi - lo).stack(), (hi - pc).abs().stack(),
                    (lo - pc).abs().stack()], axis=1).max(axis=1).unstack()
    atr = tr.rolling(ATR_N).mean()

    ind = {"op": op, "hi": hi, "lo": lo, "cl": cl, "atr": atr}
    ind["dc"] = {d: hi.rolling(d).max().shift(1) for d in GRID["dc"]}
    ind["ma"] = {m: cl.rolling(m).mean() for m in GRID["ma"]}
    ind["mom"] = {m: cl / cl.shift(m) - 1 for m in GRID["mom"]}

    ks = _kospi()
    ind["reg"] = {r: (ks > ks.rolling(r).mean()) if r else None
                  for r in GRID["regime"]}
    ind["ks"] = ks
    ind["codes"] = codes
    return ind


def simulate(ind, cfg, lo_d, hi_d):
    """한 조합을 한 구간에서. numpy 행 단위로 돈다."""
    cl = ind["cl"]
    m = (cl.index >= pd.Timestamp(lo_d)) & (cl.index <= pd.Timestamp(hi_d))
    idx = cl.index[m]
    if len(idx) < 60:
        return None, []

    O = ind["op"].loc[idx].values
    H = ind["hi"].loc[idx].values
    C = cl.loc[idx].values
    A = ind["atr"].loc[idx].values
    D = ind["dc"][cfg["dc"]].loc[idx].values
    M = ind["ma"][cfg["ma"]].loc[idx].values
    R = ind["mom"][cfg["mom"]].loc[idx].values
    reg = ind["reg"][cfg["regime"]]
    on = (reg.reindex(idx).fillna(False).values if reg is not None
          else np.ones(len(idx), bool))

    slots, chand = cfg["slots"], cfg["chand"]
    slot_cap = CAP / slots
    cash, pos, eq, trades = float(CAP), {}, np.empty(len(idx) - 1), []

    for i in range(len(idx) - 1):
        # 청산: i일 종가 확인 → i+1일 시가
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
        # 진입
        if on[i] and len(pos) < slots:
            ok = ((C[i] > D[i]) & (C[i] > M[i]) & ~np.isnan(R[i])
                  & ~np.isnan(A[i]) & (O[i + 1] > 0))
            for j in np.argsort(-np.where(ok, R[i], -np.inf)):
                if len(pos) >= slots or cash < slot_cap or not ok[j]:
                    break
                if j in pos:
                    continue
                px = O[i + 1, j]
                cash -= slot_cap
                pos[j] = {"qty": slot_cap / px, "entry": px, "peak": px}
        held = sum(p["qty"] * C[i, j] for j, p in pos.items()
                   if not np.isnan(C[i, j]))
        eq[i] = cash + held
    return pd.Series(eq, index=idx[:-1]), trades


def stats(eq, trades):
    if eq is None or len(eq) < 30:
        return None
    r = eq.pct_change().dropna()
    tot = eq.iloc[-1] / eq.iloc[0] - 1
    sd = float(r.std())
    return {"tot": tot * 100, "n": len(trades),
            "avg": float(np.mean(trades)) if trades else 0.0,
            "mdd": float((eq / eq.cummax() - 1).min()) * 100,
            "sharpe": (float(r.mean()) / sd * np.sqrt(252)) if sd else 0.0}


def bh(ind, lo_d, hi_d):
    ks = ind["ks"]
    s = ks[(ks.index >= pd.Timestamp(lo_d)) & (ks.index <= pd.Timestamp(hi_d))]
    return (s.iloc[-1] / s.iloc[0] - 1) * 100 if len(s) > 1 else 0.0


def main(args):
    ind = build()
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    print(f"[v23] 격자 {len(combos)}개 | IS {IS[0]}~{IS[1]} | OOS {OOS[0]}~{OOS[1]}")
    print(f"  ⚠️ {len(combos)}개를 뒤진다는 사실이 IS 최고성적을 부풀린다. 판정은 OOS 로만.")

    is_bh = bh(ind, *IS)
    rows = []
    for i, cfg in enumerate(combos):
        eq, tr = simulate(ind, cfg, *IS)
        s = stats(eq, tr)
        if s:
            rows.append((cfg, s))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(combos)}", flush=True)
    pickle.dump(rows, open(RES, "wb"))

    print(f"\n  IS 매수보유 {is_bh:+.1f}%  |  유효 조합 {len(rows)}개")
    # 선정 규칙: 매수보유를 이긴 것 중 Sharpe 최고 (사전 고정)
    winners = [(c, s) for c, s in rows if s["tot"] > is_bh and s["n"] >= 20]
    print(f"  IS 에서 매수보유를 이긴 조합 {len(winners)}개")
    if not winners:
        print("  → IS 에서조차 매수보유를 이기는 조합이 없다. OOS 를 열지 않는다.")
        return
    best_cfg, best_is = max(winners, key=lambda x: x[1]["sharpe"])
    print(f"\n  선정: {best_cfg}")
    print(f"  IS  누적 {best_is['tot']:+.1f}%  Sharpe {best_is['sharpe']:.2f}  "
          f"MDD {best_is['mdd']:.1f}%  거래 {best_is['n']}건  "
          f"거래당 {best_is['avg']:+.2f}%")
    print(f"  IS 상위 5개 Sharpe: " +
          ", ".join(f"{s['sharpe']:.2f}" for _, s in
                    sorted(winners, key=lambda x: -x[1]["sharpe"])[:5]))

    if args.is_only:
        print("\n  --is-only 이므로 OOS 는 열지 않는다(봉인 유지).")
        return

    eq, tr = simulate(ind, best_cfg, *OOS)
    s = stats(eq, tr)
    o_bh = bh(ind, *OOS)
    print(f"\n  ══ OOS (봉인 해제, 1회) ══")
    print(f"  누적 {s['tot']:+.1f}%  Sharpe {s['sharpe']:.2f}  MDD {s['mdd']:.1f}%")
    print(f"  거래 {s['n']}건  거래당 평균 {s['avg']:+.2f}%")
    print(f"  대조군 KOSPI 매수보유 {o_bh:+.1f}%")

    a = s["avg"] > COST
    b = s["tot"] > o_bh
    c = s["n"] >= 30
    d = (best_is["sharpe"] > 0) == (s["sharpe"] > 0)
    print(f"\n  ── 사전 기준 ──")
    print(f"  (a) 거래당 > 비용 0.23%     {s['avg']:+.2f}%   {'O' if a else 'X'}")
    print(f"  (b) 누적 > 매수보유         {s['tot']:+.1f}% vs {o_bh:+.1f}%   {'O' if b else 'X'}")
    print(f"  (c) 거래 30건 이상          {s['n']}건   {'O' if c else 'X'}")
    print(f"  (d) IS·OOS Sharpe 동부호    {best_is['sharpe']:.2f} / {s['sharpe']:.2f}"
          f"   {'O' if d else 'X'}")
    print(f"  → {'★통과' if (a and b and c and d) else '기각'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--is-only", action="store_true")
    main(ap.parse_args())
