# -*- coding: utf-8 -*-
"""젯슨 실시간 결합 포트폴리오 — 세 전략을 역변동성 비중으로 합산.

**각 봇의 자본금은 건드리지 않는다.** 중간에 바꾸면 (1) 자산곡선이 끊겨 그전 기록과
비교가 안 되고 (2) 코인봇처럼 '포지션당 5만원 × 3종목' 구조는 자본을 줄이면 종목 수나
크기가 달라져 **검증한 그 전략이 아니게 된다.** 비중은 "각 전략을 어떻게 섞어 볼
것인가"의 관점이지 전략 내부를 바꾸라는 뜻이 아니다.

그래서 각 봇은 그대로 두고 **세 기록을 수익률로 환산해 45/20/35로 합산**한다.

비중 근거: `portfolio_mix.py` 역변동성 배분(2023-06~2026-08, 756일).
셋이 사실상 무상관(|ρ| ≤ 0.03)이라 Sharpe 1.25 → 1.75, MDD −19.0% → −16.8%.

⚠️ 전략B(급등+공시촉매)는 결합 분석에 포함되지 않았다(백테스트 t=1.57로 판정 불가).
여기서도 뺀다 — 검증 안 된 것을 섞으면 결합 수치의 의미가 흐려진다.

사용: python3 portfolio_live.py        (젯슨에서 실행)
"""
import json
import os

import numpy as np
import pandas as pd

BASE = "/home/user/llm-trading-backtest"
XAI = "/home/user/xavier_nx_ai"

WEIGHTS = {"장투(KR)": 0.45, "크립토 롱숏": 0.20, "코인봇": 0.35}


def _load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
            return json.loads(t) if t else d
    except Exception:
        return d


def s_trend():
    d = _load(f"{BASE}/cache/paper_state.json", {})
    eq = d.get("equity", [])
    if not eq:
        return None
    s = pd.Series({pd.Timestamp(t): v for t, v in eq}).sort_index()
    return s / s.iloc[0]


def s_ls():
    d = _load(f"{BASE}/cache/ls_paper_state.json", {})
    eq = d.get("equity", [])
    if not eq:
        return None
    # equity 는 누적 %p → 1 + %/100
    s = pd.Series({pd.Timestamp(t): 1 + v / 100 for t, v in eq}).sort_index()
    return s / s.iloc[0]


def s_coin():
    d = _load(f"{XAI}/crypto/equity_htf.json", {})
    if not d:
        return None
    s = pd.Series({pd.Timestamp(k): v for k, v in d.items()}).sort_index()
    return s / s.iloc[0]


def main():
    parts = {"장투(KR)": s_trend(), "크립토 롱숏": s_ls(), "코인봇": s_coin()}
    print("=" * 66)
    print("  젯슨 결합 포트폴리오 (역변동성 비중 45/20/35)")
    print("=" * 66)
    have = {k: v for k, v in parts.items() if v is not None and len(v) >= 2}
    for k, w in WEIGHTS.items():
        v = parts[k]
        if v is None or len(v) < 2:
            print(f"  {k:<14} 비중 {w:.0%}  — 기록 부족(누적 대기)")
        else:
            print(f"  {k:<14} 비중 {w:.0%}  {v.index[0].date()}~{v.index[-1].date()} "
                  f"{len(v)}일  누적 {100*(v.iloc[-1]-1):+.2f}%")
    if len(have) < 2:
        print("\n  결합 계산은 전략 2개 이상 기록이 쌓여야 가능하다.")
        return

    df = pd.DataFrame(have).ffill().dropna()
    if len(df) < 2:
        print("\n  공통 구간 없음 — 며칠 더 쌓여야 한다.")
        return
    r = df.pct_change().dropna()
    w = np.array([WEIGHTS[c] for c in df.columns])
    w = w / w.sum()                      # 일부만 있을 때 정규화
    pr = (r * w).sum(axis=1)
    eq = (1 + pr).cumprod()
    mdd = float((eq / eq.cummax() - 1).min()) * 100
    print(f"\n  공통 구간 {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)")
    print(f"  결합 누적 {100*(float(eq.iloc[-1])-1):+.2f}%  |  MDD {mdd:.2f}%")
    if len(pr) >= 20:
        sh = float(pr.mean()) / (float(pr.std()) + 1e-12) * np.sqrt(252)
        print(f"  연율 Sharpe {sh:+.2f} (표본 {len(pr)}일 — 20일 미만이면 무의미)")
    print("\n  ※ 백테스트 기대치: 연율 31.3%, 변동성 17.9%, Sharpe 1.75, MDD −16.8%")
    print("     포워드가 이에 근접하는지가 판정 기준이다. 최소 수개월 필요.")


if __name__ == "__main__":
    main()
