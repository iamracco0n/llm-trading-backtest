# -*- coding: utf-8 -*-
"""규칙봇 vs LLM봇 백테스트 — 같은 과거 데이터를 재생하며 두 봇을 동시에 돌린다."""
import os
import sys
import json
import time
import argparse

import config
import data as datamod
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot
from llm_engine import LLMBot

RESULTS = os.path.join(os.path.dirname(__file__), "results")


def run(days, ref="KRW-BTC", no_llm=False, tag=None):
    tag = tag or f"{days}d"
    candles = datamod.load_candles(config.COINS, days)
    if ref not in candles:
        ref = list(candles.keys())[0]
    clock = candles[ref]["m5"].index

    # 판단 시점: 워밍업 이후 DECISION_INTERVAL_BARS 마다
    start_i = config.WARMUP_BARS
    decision_idx = list(range(start_i, len(clock), config.DECISION_INTERVAL_BARS))
    print(f"[bt] 종목 {len(candles)}개, 판단시점 {len(decision_idx)}회 "
          f"({clock[start_i]} ~ {clock[-1]})")

    rule = RuleBot(Paper("규칙봇"))
    llm = LLMBot(Paper("LLM봇"))

    t0 = time.time()
    for n, i in enumerate(decision_idx):
        ts = clock[i]
        snapshot = {}
        for t, c in candles.items():
            ind = compute_indicators(c["m5"], c["m4h"], ts)
            if ind is not None:
                snapshot[t] = ind
        if not snapshot:
            continue
        price_map = {t: d["current_price"] for t, d in snapshot.items()}

        rule.step(ts, snapshot)
        if not no_llm:
            llm.step(ts, snapshot)
            if config.THROTTLE_SEC > 0:
                time.sleep(config.THROTTLE_SEC)  # GPU 식힐 틈 (밤 wedge 방지)

        rule.paper.mark(ts, price_map)
        llm.paper.mark(ts, price_map)

        if n % 5 == 0 or n == len(decision_idx) - 1:
            re_ = rule.paper.equity(price_map)
            le_ = llm.paper.equity(price_map)
            el = time.time() - t0
            print(f"[bt] {n+1}/{len(decision_idx)} {ts} | "
                  f"규칙 {re_:,.0f} | LLM {le_:,.0f} | {el:.0f}s")

    # 최종 저장
    os.makedirs(RESULTS, exist_ok=True)
    _save(rule, llm, tag)
    _scoreboard(rule, llm)
    return rule, llm


def _stats(paper):
    ec = paper.equity_curve
    if not ec:
        return {}
    start = config.START_KRW
    end = ec[-1][1]
    peak = start
    mdd = 0.0
    for _, v in ec:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    sells = [t for t in paper.trades if t["side"] == "SELL"]
    wins = [t for t in sells if t.get("profit_pct", 0) > 0]
    return {
        "종료자산": round(end),
        "총수익률%": round((end / start - 1) * 100, 2),
        "MDD%": round(mdd * 100, 2),
        "매매횟수": len(sells),
        "승률%": round(100 * len(wins) / len(sells), 1) if sells else 0.0,
    }


def _scoreboard(rule, llm):
    rs, ls = _stats(rule.paper), _stats(llm.paper)
    print("\n" + "=" * 52)
    print("  스코어보드          규칙봇        LLM봇")
    print("=" * 52)
    for k in ["종료자산", "총수익률%", "MDD%", "매매횟수", "승률%"]:
        print(f"  {k:<12} {str(rs.get(k,'-')):>12} {str(ls.get(k,'-')):>12}")
    print("=" * 52)
    winner = "LLM봇" if ls.get("총수익률%", -1e9) > rs.get("총수익률%", -1e9) else "규칙봇"
    print(f"  판정: {winner} 우세\n")


def _save(rule, llm, tag):
    with open(os.path.join(RESULTS, f"trades_rule_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(rule.paper.trades, f, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(RESULTS, f"trades_llm_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(llm.paper.trades, f, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(RESULTS, f"llm_decisions_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(llm.decision_log, f, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(RESULTS, f"equity_{tag}.csv"), "w", encoding="utf-8") as f:
        f.write("ts,rule,llm\n")
        rc = {str(t): v for t, v in rule.paper.equity_curve}
        lc = {str(t): v for t, v in llm.paper.equity_curve}
        for t in rc:
            f.write(f"{t},{rc[t]:.0f},{lc.get(t,''):.0f}\n" if t in lc else f"{t},{rc[t]:.0f},\n")
    print(f"[bt] 결과 저장: {RESULTS}/*_{tag}.*")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=config.BACKTEST_DAYS)
    ap.add_argument("--no-llm", action="store_true", help="규칙봇만 (파이프라인 점검용)")
    ap.add_argument("--tag", type=str, default=None, help="결과 파일 태그 (예: 7d_v2)")
    ap.add_argument("--model", type=str, default=None, help="LLM 모델 오버라이드 (예: qwen3:8b)")
    ap.add_argument("--throttle", type=int, default=None, help="LLM 호출 사이 대기초(밤 wedge 방지)")
    ap.add_argument("--cpu", action="store_true", help="순수 CPU 추론(num_gpu=0, GPU 안 씀)")
    args = ap.parse_args()
    if args.cpu:
        config.NUM_GPU = 0
        print("[bt] CPU 전용 모드 (num_gpu=0)")
    if args.model:
        config.LLM_MODEL = args.model
        print(f"[bt] LLM 모델: {config.LLM_MODEL}")
    if args.throttle is not None:
        config.THROTTLE_SEC = args.throttle
        print(f"[bt] throttle: {config.THROTTLE_SEC}초/호출")
    run(args.days, no_llm=args.no_llm, tag=args.tag)
