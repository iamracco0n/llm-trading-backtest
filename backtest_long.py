# -*- coding: utf-8 -*-
"""긴 다국면 백테스트 — 시간봉(60분) 90일 + 일봉(상위추세)로 상승/하락/횡보 섞인 구간 검증.
국면적응 v4가 단일 전략(추세추종/평균회귀)을 이기는지 진짜 시험.
"""
import os
import time
import pickle
from collections import Counter

import config
from data import _fetch_paginated
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot
from meanrev_backtest import MeanRevBot
from regime_adaptive import RegimeAdaptiveBot, classify_regime

CACHE = os.path.join(os.path.dirname(__file__), "cache", "long_60m_90d.pkl")
CADENCE = 6      # 시간봉 6개 = 6시간마다 판단
WARMUP = 65      # 시간봉 워밍업(ma60)


def load_long(days=90):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as f:
            print("[data] 캐시 사용")
            return pickle.load(f)
    base_bars = days * 24 + 100        # 시간봉
    high_bars = days + 120             # 일봉(워밍업 여유)
    out = {}
    for i, t in enumerate(config.COINS):
        print(f"[data] ({i+1}/{len(config.COINS)}) {t}")
        m60 = _fetch_paginated(t, "minute60", base_bars)
        time.sleep(0.15)
        mday = _fetch_paginated(t, "day", high_bars)
        if m60 is None or mday is None or len(m60) < 200 or len(mday) < 40:
            print(f"[data]   {t} 데이터 부족 → 제외")
            continue
        out[t] = {"m5": m60, "m4h": mday}   # 키 재사용(base/high)
        time.sleep(0.2)
    with open(CACHE, "wb") as f:
        pickle.dump(out, f)
    print(f"[data] 저장 (종목 {len(out)})")
    return out


def run(days=90):
    candles = load_long(days)
    ref = "KRW-BTC" if "KRW-BTC" in candles else list(candles)[0]
    clock = candles[ref]["m5"].index
    idx = list(range(WARMUP, len(clock), CADENCE))
    print(f"[bt] 종목 {len(candles)}, 판단 {len(idx)}회 ({clock[WARMUP]} ~ {clock[-1]})")

    bots = {
        "추세추종": RuleBot(Paper("추세추종")),
        "평균회귀": MeanRevBot(Paper("평균회귀")),
        "국면적응v4": RegimeAdaptiveBot(Paper("국면적응v4")),
    }
    reg = Counter()
    # BTC 국면 추이(구간이 다국면인지 확인용)
    btc_reg_timeline = []
    for i in idx:
        ts = clock[i]
        snap = {}
        for t, c in candles.items():
            ind = compute_indicators(c["m5"], c["m4h"], ts)
            if ind:
                snap[t] = ind
        if not snap:
            continue
        pm = {t: d["current_price"] for t, d in snap.items()}
        for b in bots.values():
            b.step(ts, snap); b.paper.mark(ts, pm)
        for t, d in snap.items():
            reg[classify_regime(d)] += 1
        if ref in snap:
            btc_reg_timeline.append(classify_regime(snap[ref]))

    def stat(paper):
        ec = paper.equity_curve; end = ec[-1][1] if ec else config.START_KRW
        peak = config.START_KRW; mdd = 0
        for _, v in ec:
            peak = max(peak, v); mdd = min(mdd, v/peak-1)
        sells = [t for t in paper.trades if t["side"] in ("SELL", "COVER")]
        wins = [t for t in sells if t.get("profit_pct", 0) > 0]
        return (round(end), round((end/config.START_KRW-1)*100, 2), round(mdd*100, 2),
                len(sells), round(100*len(wins)/len(sells), 1) if sells else 0)

    tot = sum(reg.values())
    print("전체 국면 분포:", {k: f"{100*v//tot}%" for k, v in reg.items()})
    # BTC 국면 변화 횟수(다국면성)
    changes = sum(1 for a, b in zip(btc_reg_timeline, btc_reg_timeline[1:]) if a != b)
    print(f"BTC 국면 전환 {changes}회 → 다국면 구간 여부 판단")
    print("=" * 64)
    print("  전략             종료자산   수익률%    MDD%   매매  승률%")
    print("=" * 64)
    for name, b in bots.items():
        e, r, m, n, w = stat(b.paper)
        print(f"  {name:<14} {e:>11,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 64)


if __name__ == "__main__":
    run(90)
