# -*- coding: utf-8 -*-
"""v5 — 실적 서프라이즈 드리프트(PEAD). LLM이 실적공시 강도를 판정한 게 드리프트를 예측하나?

핵심 테스트(이벤트 스터디): 실적공시 다음 거래일 시가 진입 → H거래일 후 종가까지 수익률을
LLM 등급(강한호재/약한호재/중립/악재)별로 평균. 강한호재가 진짜 더 드리프트하면 = LLM 신호 有.
비교: A) 규칙(실적공시면 다 매수) vs B) LLM(강한호재만). B가 A 이기면 LLM이 텍스트니치서 밥값.

LLM=aurora qwen3:30b(CPU). 실적판정 445건 캐시.
"""
import os
import pickle
from collections import defaultdict
import pandas as pd

from surge_backtest import load_data
from dart_data import fetch_document_text
from llm_earnings import judge_earnings

EVENTS = "cache/v5_earnings_events.pkl"
JUDGE = "cache/v5_earnings_judgments.pkl"
HORIZONS = [5, 10, 20, 40]   # 드리프트 관찰 거래일


def judge_all():
    events = pickle.load(open(EVENTS, "rb"))
    cache = pickle.load(open(JUDGE, "rb")) if os.path.exists(JUDGE) else {}
    all_ev = [(rn, nm) for evs in events.values() for _, rn, nm in evs]
    # 고유 rcept_no
    uniq = {rn: nm for rn, nm in all_ev}
    todo = [(rn, nm) for rn, nm in uniq.items() if rn not in cache]
    print(f"[llm] 실적판정 대상 {len(uniq)}건 (캐시 {len(uniq)-len(todo)}, 신규 {len(todo)})")
    for i, (rn, nm) in enumerate(todo):
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        res = judge_earnings(nm, body) if body else None
        cache[rn] = res or {"verdict": "중립", "score": 0, "reason": "본문없음/실패"}
        cache[rn]["nm"] = nm
        if (i + 1) % 10 == 0:
            print(f"[llm]   {i+1}/{len(todo)}  {nm[:16]} → {cache[rn]['verdict']}({cache[rn]['score']})")
            pickle.dump(cache, open(JUDGE, "wb"))
    pickle.dump(cache, open(JUDGE, "wb"))
    return cache


def event_study():
    data = load_data()
    events = pickle.load(open(EVENTS, "rb"))
    judg = judge_all()
    # verdict별 / horizon별 forward return 수집
    fwd = {h: defaultdict(list) for h in HORIZONS}
    allret = {h: [] for h in HORIZONS}   # 규칙A = 전체
    for code, evs in events.items():
        if code not in data:
            continue
        df = data[code]["df"]; idx = df.index
        for d, rn, nm in evs:
            j = judg.get(rn)
            if not j:
                continue
            dd = pd.to_datetime(d, format="%Y%m%d")
            after = idx[idx > dd]
            if len(after) < 1:
                continue
            entry_ts = after[0]
            pos = idx.get_loc(entry_ts)
            e_open = df.at[entry_ts, "Open"]
            if pd.isna(e_open) or e_open <= 0:
                continue
            for h in HORIZONS:
                if pos + h >= len(idx):
                    continue
                x_close = df.iloc[pos + h]["Close"]
                if pd.isna(x_close):
                    continue
                r = (x_close / e_open - 1) * 100
                fwd[h][j["verdict"]].append(r)
                allret[h].append(r)

    def stat(lst):
        if not lst:
            return (0, 0, 0)
        import statistics as st
        return (len(lst), round(st.mean(lst), 2), round(100 * sum(1 for x in lst if x > 0) / len(lst), 1))

    from collections import Counter
    vc = Counter(j["verdict"] for j in judg.values())
    print("=" * 74)
    print(f"  v5 실적 드리프트(PEAD) 이벤트 스터디  —  공시 다음날 시가진입, H일 후 종가")
    print(f"  판정 분포: {dict(vc)}")
    print("=" * 74)
    header = "  등급           " + "".join(f"  H+{h:<2}(n/평균%/승률)" for h in HORIZONS)
    print(header)
    print("-" * 74)
    order = ["강한호재", "약한호재", "중립", "악재"]
    for v in order:
        row = f"  {v:<12}"
        for h in HORIZONS:
            n, m, w = stat(fwd[h].get(v, []))
            row += f"  {n:>3}/{m:>+6.2f}/{w:>4.0f}"
        print(row)
    print("-" * 74)
    # 규칙A(전체) vs LLM B(강한호재)
    print("  ── 규칙 vs LLM ──")
    for h in HORIZONS:
        na, ma, wa = stat(allret[h])
        nb, mb, wb = stat(fwd[h].get("강한호재", []))
        print(f"  H+{h:<2}: A)전체매수 n{na} 평균{ma:+.2f}% 승{wa:.0f}%  |  B)LLM강한호재 n{nb} 평균{mb:+.2f}% 승{wb:.0f}%")
    print("=" * 74)


if __name__ == "__main__":
    event_study()
