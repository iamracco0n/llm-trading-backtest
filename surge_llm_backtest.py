# -*- coding: utf-8 -*-
"""Phase 3 — LLM(공시 본문 質판정) 필터 vs 키워드 필터 vs 무필터, 정면 비교.

A) 급등만            (필터 없음, Phase1)
B) 급등+공시(키워드)  (제목에 촉매 키워드, Phase2)
C) 급등+공시(LLM호재) (qwen이 본문 읽고 '호재'로 판정한 것만)

LLM 판정은 신호를 게이팅하는 고유 공시 99건에만(캐시). ollama=aurora qwen3:30b(CPU).
"""
import os
import pickle
import argparse
import pandas as pd

from surge_backtest import load_data
from surge_dart_backtest import simulate
from dart_data import fetch_document_text
from llm_catalyst import judge

PREP = "cache/phase3_prep.pkl"
JUDGE_CACHE = "cache/llm_catalyst_judgments.pkl"


def judge_all(rcepts, events):
    """rcept_no별 LLM 판정 {rcept_no: {verdict,score,reason,nm}} (캐시, 누락분만)."""
    cache = {}
    if os.path.exists(JUDGE_CACHE):
        cache = pickle.load(open(JUDGE_CACHE, "rb"))
    nm_of = {rn: nm for evs in events.values() for _, rn, nm in evs}
    todo = [r for r in rcepts if r not in cache]
    print(f"[llm] 판정 대상 {len(rcepts)}건 (캐시 {len(rcepts)-len(todo)}, 신규 {len(todo)})")
    for i, rn in enumerate(todo):
        nm = nm_of.get(rn, "")
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        res = judge(nm, body) if body else None
        cache[rn] = res or {"verdict": "중립", "score": 0, "reason": "본문없음/실패"}
        cache[rn]["nm"] = nm
        if (i + 1) % 5 == 0:
            print(f"[llm]   {i+1}/{len(todo)}  최근: {nm[:16]} → {cache[rn]['verdict']}({cache[rn]['score']})")
            pickle.dump(cache, open(JUDGE_CACHE, "wb"))
    pickle.dump(cache, open(JUDGE_CACHE, "wb"))
    return cache


def cat_ts_from_events(events, keep):
    """{code: sorted[Timestamp]} — keep(rcept_no)->True 인 공시 날짜만."""
    out = {}
    for code, evs in events.items():
        ds = sorted({d for d, rn, nm in evs if keep(rn)})
        if ds:
            out[code] = ds
    return out


def run(slip=0.003, min_score=50):
    data = load_data()
    prep = pickle.load(open(PREP, "rb"))
    events, rcepts = prep["events"], prep["rcepts"]
    judg = judge_all(rcepts, events)

    # B: 키워드 촉매 = 모든 촉매 공시 날짜
    cat_kw = cat_ts_from_events(events, lambda rn: True)
    # C: LLM 호재 = verdict 호재 & score>=min_score
    def is_bull(rn):
        j = judg.get(rn)
        return bool(j and j["verdict"] == "호재" and j["score"] >= min_score)
    cat_llm = cat_ts_from_events(events, is_bull)

    empty = {}
    a = simulate(data, slip, require_catalyst=False, cat_ts=empty)
    b = simulate(data, slip, require_catalyst=True, cat_ts=cat_kw)
    c = simulate(data, slip, require_catalyst=True, cat_ts=cat_llm)

    n_bull = sum(1 for rn in rcepts if is_bull(rn))
    from collections import Counter
    vc = Counter(judg[rn]["verdict"] for rn in rcepts)
    print("=" * 70)
    print(f"  급등주 — 필터별 비교 (슬리피지 {slip*100:.1f}%, LLM 호재기준 score≥{min_score})")
    print(f"  {a['cal'][0].date()}~{a['cal'][1].date()},  공시판정 {dict(vc)}, 호재통과 {n_bull}/{len(rcepts)}")
    print("=" * 70)
    print("  전략                수익률%    MDD%   매매  승률%  평균손익%")
    print("-" * 70)
    for name, s in [("A) 급등만", a), ("B) 급등+공시(키워드)", b), ("C) 급등+공시(LLM호재)", c)]:
        print(f"  {name:<20} {s['ret']:>7.2f} {s['mdd']:>7.2f} {s['n']:>5} {s['win']:>6.1f} {s['avg']:>8.2f}")
    print("=" * 70)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=0.003)
    ap.add_argument("--min-score", type=int, default=50)
    a = ap.parse_args()
    run(slip=a.slip, min_score=a.min_score)
