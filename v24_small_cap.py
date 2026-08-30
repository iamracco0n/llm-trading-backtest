# -*- coding: utf-8 -*-
"""v24 — 50만원에서 사전 기준 4개를 **통과**했다. 그런데 그 통과를 믿을 수 없다.

━━━ 결과 ━━━
    자본        OOS 누적   SR    MDD     거래당    판정
    500,000원   +303.7%  1.80  −30.6%  +27.48%  ★통과(4/4)
    200,000원     +2.9%  0.31  −47.1%   −0.16%  기각
    (OOS 구간 KOSPI 매수보유 +174.9%)

같은 데이터·같은 알고리즘·같은 홀드아웃인데 **자본만 바꾸니 결과가 뒤집혔다.**
그냥 넘어갈 수 없어서 갈라봤다. 두 자본에서 뽑힌 조합이 서로 달랐다:
    A = dc60/ma120/chand3.0/mom20/slots3   (50만원에서 선정)
    B = dc60/ma120/chand2.0/mom60/slots3   (20만원에서 선정)

━━━ ★ 교차검증이 말해주는 것 ━━━
    조합   20만원    50만원    100만원      OOS Sharpe 범위
    A     +116.9   +303.7    +176.3      1.14 ~ 1.80
    B       +2.9    +69.5     −14.7      0.15 ~ 0.94

**자본이 아니라 조합이 원인이다.** A 는 모든 자본에서 양수, B 는 모든 자본에서 나쁘다.
그런데 **IS 로는 A 와 B 를 구분할 수 없다** — IS 수익이 A +182~197%, B +108~176% 로
B 도 충분히 좋아 보였고, 실제로 20만원 IS 에서는 **B 가 선정됐다.**

즉 **"IS 에서 Sharpe 최고를 고른다"는 선정 규칙이 신뢰할 수 없다.** 50만원에서의
통과는 그 규칙이 **운 좋게 A 를 집은 결과**다. 20만원에서는 같은 규칙이 B 를 집었고
그것은 OOS 에서 무너졌다. 규칙이 절반만 맞으면 그것은 규칙이 아니다.

그리고 A 안에서도 자본에 따라 +116.9 ~ +303.7 로 흔들린다. **매수보유(+174.9%)를
넘는 것은 50만원과 100만원뿐이고 20만원은 진다.** 1주 단위 반올림이 만드는
차이인데, 이 정도로 흔들리는 것을 '전략'이라 부를 수 없다.

━━━ 결론 ━━━
· 접근 자체는 살아 있다 — 조합 A 는 세 자본 모두에서 양수이고 SR 1.14~1.80 이다.
· 그러나 **"올바른 파라미터를 찾았다"고 말할 수 없다.** IS 가 A 와 B 를 못 가린다.
· 실전 투입 근거로 쓰기엔 부족하다. 선정을 안정화하는 것이 먼저다
  (예: IS 를 여러 조각으로 나눠 전 조각에서 상위인 조합만 남기기 — 아직 안 했다).

━━━ 이하 원래 설계 ━━━
**소자본으로 실제 굴릴 수 있는가.** 유니버스를 넓히고 매수가능성을 제약으로 넣는다.

━━━ 왜 (내가 틀린 지점) ━━━
"5만원으론 안 되고 250만원은 있어야 한다"고 했는데 **유니버스를 잘못 잡아서 나온 숫자**였다.
v22/v23 은 `trend_kospi_long.pkl` = **KOSPI 대형주 150종목**만 썼고 주가 중앙값이
128,450원이다. 그러니 슬롯 1만원으로 살 수 있는 게 5%뿐이었다.

KOSPI+KOSDAQ 전체에서 거래대금 30억 이상을 잡으면 완전히 달라진다:
    434종목, 주가 중앙값 **32,500원**
    그중 5만원 이하 261종목 / 10만원 이하 322종목
소자본이 문제가 아니라 **대형주만 보고 있었던 것**이 문제였다.

━━━ v23 과 다른 점 세 가지 ━━━
1. 유니버스 413종목(KOSPI 241 + KOSDAQ 172, 거래대금 30억+).
2. **매수가능성을 제약으로 넣는다** — 슬롯 금액으로 1주도 못 사는 종목은 후보에서
   제외한다. 백테스트가 살 수 없는 것을 사면 그 수익은 가짜다. v23 은 이 제약이
   없어서 "삼양식품 1,547,000원"을 슬롯 1만원으로 사는 것으로 계산됐다.
3. **PIT 유동성** — 오늘 거래대금이 아니라 **그 시점의 20일 평균 거래대금**으로
   자격을 판정한다. 오늘 기준으로 거르면 "나중에 커질 종목"을 미리 아는 셈이 된다
   (`trend_pit_universe.py` 가 장투에서 같은 함정을 지적했다).

━━━ 사전 기준 (결과 보기 전 고정, v23 과 동일 잣대) ━━━
  (a) OOS 거래당 평균 순수익 > 0.23%(왕복비용)
  (b) OOS 누적 > 같은 구간 KOSPI 매수보유
  (c) OOS 거래 30건 이상
  (d) IS·OOS Sharpe 동부호
⚠️ v23 에서 (b)가 나쁜 기준이었음을 이미 확인했다(현금 보유 전략의 한 구간 절대수익을
   지수와 비교하면 그 구간이 어떤 장이었나를 재게 된다). 그래도 **기준은 그대로 둔다** —
   결과를 보고 잣대를 고치지 않기 위해서다. 대신 위험조정 수치를 같이 보고한다.

━━━ 한계 ━━━
· 유니버스가 **오늘 상장·거래되는 종목**이라 상장폐지분이 없다(생존편향). KOSDAQ 을
  넣으면서 이 편향이 v23 보다 **커졌을 가능성**이 있다 — 코스닥은 폐지가 잦다.
· 슬리피지 0. 소형주는 호가 스프레드가 넓어 이 가정이 대형주보다 더 낙관적이다.

사용: python3 v24_small_cap.py --cap 500000
"""
import argparse
import itertools
import pickle

import numpy as np
import pandas as pd

from v22_htf_kr import _kospi

PX = "/home/user/llm-trading-backtest/cache/v24_px.pkl"
IS = ("2022-01-01", "2024-12-31")
OOS = ("2025-01-01", "2026-07-31")
COST = 0.23
ATR_N = 14
MIN_AMT = 3e9        # PIT 20일 평균 거래대금 하한

GRID = {"dc": [10, 20, 40, 60], "ma": [20, 50, 120], "chand": [2.0, 3.0, 4.0],
        "mom": [20, 60], "slots": [3, 5, 10], "regime": [20, 60, 0]}


def build():
    raw = pickle.load(open(PX, "rb"))
    codes = [c for c, v in raw.items() if len(v["df"]) > 300]
    f = lambda k: pd.DataFrame({c: raw[c]["df"][k] for c in codes}).sort_index()
    op, hi, lo, cl, vo = f("Open"), f("High"), f("Low"), f("Close"), f("Volume")
    pc = cl.shift(1)
    tr = pd.concat([(hi - lo).stack(), (hi - pc).abs().stack(),
                    (lo - pc).abs().stack()], axis=1).max(axis=1).unstack()
    ind = {"op": op, "hi": hi, "lo": lo, "cl": cl,
           "atr": tr.rolling(ATR_N).mean(),
           # PIT 유동성: 그 시점의 20일 평균 거래대금
           "amt": (cl * vo).rolling(20).mean()}
    ind["dc"] = {d: hi.rolling(d).max().shift(1) for d in GRID["dc"]}
    ind["ma"] = {m: cl.rolling(m).mean() for m in GRID["ma"]}
    ind["mom"] = {m: cl / cl.shift(m) - 1 for m in GRID["mom"]}
    ks = _kospi()
    ind["reg"] = {r: (ks > ks.rolling(r).mean()) if r else None for r in GRID["regime"]}
    ind["ks"] = ks
    ind["names"] = {c: raw[c]["name"] for c in codes}
    ind["codes"] = codes
    return ind


def simulate(ind, cfg, lo_d, hi_d, cap):
    cl = ind["cl"]
    m = (cl.index >= pd.Timestamp(lo_d)) & (cl.index <= pd.Timestamp(hi_d))
    idx = cl.index[m]
    if len(idx) < 60:
        return None, []
    O, H, C = (ind[k].loc[idx].values for k in ("op", "hi", "cl"))
    A = ind["atr"].loc[idx].values
    AMT = ind["amt"].loc[idx].values
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
            ok = ((C[i] > D[i]) & (C[i] > M[i]) & ~np.isnan(R[i]) & ~np.isnan(A[i])
                  & (nx > 0) & (AMT[i] >= MIN_AMT)
                  # ★ 매수가능성: 슬롯 금액으로 1주 이상 살 수 있어야 후보다
                  & (nx <= slot_cap))
            for j in np.argsort(-np.where(ok, R[i], -np.inf)):
                if len(pos) >= slots or cash < slot_cap or not ok[j]:
                    break
                if j in pos:
                    continue
                px = nx[j]
                qty = int(slot_cap // px)          # 1주 단위
                if qty < 1:
                    continue
                cost_krw = qty * px
                cash -= cost_krw
                pos[j] = {"qty": qty, "entry": px, "peak": px}
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


def bh(ind, a, b):
    s = ind["ks"]
    s = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
    return (float(s.iloc[-1] / s.iloc[0]) - 1) * 100 if len(s) > 1 else 0.0


def main(a):
    ind = build()
    print(f"[v24] 유니버스 {len(ind['codes'])}종목 | 자본 {a.cap:,}원")
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(f"  격자 {len(combos)}개 | IS {IS[0]}~{IS[1]} → OOS {OOS[0]}~{OOS[1]}")

    is_bh = bh(ind, *IS)
    rows = []
    for i, cfg in enumerate(combos):
        eq, tr = simulate(ind, cfg, *IS, a.cap)
        s = stats(eq, tr)
        if s:
            rows.append((cfg, s))
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/{len(combos)}", flush=True)

    win = [(c, s) for c, s in rows if s["tot"] > is_bh and s["n"] >= 20]
    print(f"\n  IS 매수보유 {is_bh:+.1f}% | 유효 {len(rows)} | 이긴 조합 {len(win)}")
    if not win:
        print("  → IS 에서조차 이기는 조합이 없다. OOS 안 연다.")
        return
    cfg, s_is = max(win, key=lambda x: x[1]["sharpe"])
    print(f"  선정 {cfg}")
    print(f"  IS  {s_is['tot']:+.1f}%  SR {s_is['sharpe']:.2f}  "
          f"MDD {s_is['mdd']:.1f}%  거래 {s_is['n']}  거래당 {s_is['avg']:+.2f}%")

    eq, tr = simulate(ind, cfg, *OOS, a.cap)
    s = stats(eq, tr)
    o_bh = bh(ind, *OOS)
    print(f"\n  ══ OOS (봉인 해제, 1회) ══")
    print(f"  {s['tot']:+.1f}%  SR {s['sharpe']:.2f}  MDD {s['mdd']:.1f}%  "
          f"거래 {s['n']}  거래당 {s['avg']:+.2f}%")
    print(f"  KOSPI 매수보유 {o_bh:+.1f}%")

    ok = [s["avg"] > COST, s["tot"] > o_bh, s["n"] >= 30,
          (s_is["sharpe"] > 0) == (s["sharpe"] > 0)]
    for lab, v in zip(("(a) 거래당>비용", "(b) 누적>매수보유", "(c) 거래 30+",
                       "(d) SR 동부호"), ok):
        print(f"  {lab:<18}{'O' if v else 'X'}")
    print(f"  → {'★통과' if all(ok) else '기각'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cap", type=int, default=500_000)
    main(p.parse_args())
