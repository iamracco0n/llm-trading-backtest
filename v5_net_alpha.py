# -*- coding: utf-8 -*-
"""v5 순(net) 알파 — 지금까지의 모든 v5 숫자는 **비용 전(前)** 이다.

**왜 필요한가.** 이 레포는 Phase 1에서 이미 배웠다: 급등추격은 슬리피지 0%면 +45%로
천재전략처럼 보이지만 현실 슬리피지를 넣으면 마이너스로 뒤집힌다. 그런데 v5의 알파
숫자들(IS +3.66%, OOS −2.60%, 코스피 base −4.25% …)은 전부 비용을 빼지 않은 값이다.
전문가 체크리스트에도 '거래비용 반영'이 필수 항목으로 들어 있다.

**무엇을 빼나 (왕복 1회 기준).**
  매수: 수수료 0.015%           + 슬리피지
  매도: 수수료 0.015% + 거래세 0.18%  + 슬리피지
  → 슬리피지 0.1%(대형주) 가정 시 왕복 약 0.41%p, 0.3%(소형주) 가정 시 약 0.81%p

PEAD는 보유기간이 길어(H+20~90) 회전율이 낮은 편이라 단타보다 비용 부담이 작다.
그래도 알파 자체가 ±2% 수준이면 0.4~0.8%p는 결코 작지 않다.

**핵심 질문:** 비용을 빼고도 남는 설정이 하나라도 있는가.

사용: python3 v5_net_alpha.py
"""
import os
import pickle
import statistics as st

from v5_oos import _alpha_tables, _s, HORIZONS, EV_OOS, JG_OOS, PX_OOS, EV_IS, JG_IS, CACHE

FEE_BUY = 0.00015
FEE_SELL = 0.00015 + 0.0018          # 수수료 + 증권거래세 0.18%
SLIP_LARGE, SLIP_SMALL = 0.001, 0.003   # 편도. 대형주 0.1% / 소형주 0.3%


def roundtrip_cost(slip):
    """왕복 비용(%p) — 매수·매도 수수료 + 거래세 + 편도 슬리피지 2회."""
    return (FEE_BUY + FEE_SELL + 2 * slip) * 100


def show(title, alpha, alla, score, slip, label):
    cost = roundtrip_cost(slip)
    print()
    print("=" * 78)
    print(f"  {title}   (슬리피지 편도 {slip*100:.1f}% → 왕복 비용 {cost:.2f}%p, {label})")
    print("=" * 78)
    print(f"  {'구분':<16}{'지평':<7}{'n':>6}{'총알파':>10}{'순알파':>10}{'승률':>8}  판정")
    print("-" * 78)

    rows = [("전체매수(규칙)", alla), ("LLM 강한호재", {h: alpha[h].get("강한호재", []) for h in HORIZONS}),
            ("LLM score≥95", {h: score[h].get("95+", []) for h in HORIZONS})]
    for name, src in rows:
        for h in HORIZONS:
            lst = src[h] if isinstance(src, dict) else src
            n, m, md, w = _s(lst)
            if n == 0:
                continue
            net = md - cost
            mark = "✅ 남음" if net > 0 else "❌"
            print(f"  {name if h == HORIZONS[0] else '':<16}H+{h:<5}{n:>6}{md:>+10.2f}{net:>+10.2f}"
                  f"{w:>7.0f}%  {mark}")
        print("-" * 78)


def run():
    # 코스닥 IS / OOS
    from surge_backtest import load_data
    a_i, all_i, sc_i = _alpha_tables(pickle.load(open(EV_IS, "rb")),
                                     pickle.load(open(JG_IS, "rb")),
                                     load_data(), "2025-05-01")
    show("코스닥 IS (2025-07~2026-08)", a_i, all_i, sc_i, SLIP_SMALL, "코스닥 소형주")

    a_o, all_o, sc_o = _alpha_tables(pickle.load(open(EV_OOS, "rb")),
                                     pickle.load(open(JG_OOS, "rb")),
                                     pickle.load(open(PX_OOS, "rb")), "2023-12-01")
    show("코스닥 OOS (2024-01~2025-06)", a_o, all_o, sc_o, SLIP_SMALL, "코스닥 소형주")

    # 코스피 (판정 끝났으면)
    jg_k = os.path.join(CACHE, "v5_kospi_judgments.pkl")
    ev_k = os.path.join(CACHE, "v5_kospi_events.pkl")
    if os.path.exists(jg_k):
        from v5_kospi import price_data
        a_k, all_k, sc_k = _alpha_tables(pickle.load(open(ev_k, "rb")),
                                         pickle.load(open(jg_k, "rb")),
                                         price_data(), "2023-12-01", index="KS11")
        show("코스피 대형주 (2024-01~2026-08)", a_k, all_k, sc_k, SLIP_LARGE, "코스피 대형주")
    else:
        print("\n[skip] 코스피 판정 캐시 없음 — 판정 완료 후 재실행")

    print()
    print("=" * 78)
    print("  요약: 비용을 빼고도 '순알파 +'가 남는 설정이 있는가")
    print("=" * 78)
    print("  ※ 총알파 = 마켓뉴트럴 알파(중앙값, 비용 전) / 순알파 = 총알파 − 왕복비용")
    print("  ※ PEAD는 보유기간이 길어 회전율이 낮다 — 그래도 알파가 ±2%면 0.4~0.8%p는 크다")
    print("=" * 78)


if __name__ == "__main__":
    run()
