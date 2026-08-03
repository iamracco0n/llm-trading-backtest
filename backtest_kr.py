# -*- coding: utf-8 -*-
"""국내주식 백테스트 — 크립토에서 검증한 전략들을 KRX 일봉에 그대로 적용.
  추세추종 / 평균회귀 / 국면적응 v4(현물, 숏X)  정면 비교.
데이터=토스 Open API 일봉(빠른틀) + 주봉(느린틀). 판단=매 거래일 종가.
숏 불가라 v4는 allow_short=False(하락장→현금).

주의: 지표의 return_1h(12봉전 대비)는 일봉에선 '12거래일 모멘텀'으로 의미가 바뀜 —
      크립토 프레임워크를 그대로 재사용하기 위한 근사. 파라미터는 추후 주식용으로 재튜닝 여지.
"""
from collections import Counter

import config
from toss_data import load_stocks
from universe_kr import SYMBOLS, NAME
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot
from meanrev_backtest import MeanRevBot
from regime_adaptive import RegimeAdaptiveBot, classify_regime

WARMUP = 150   # 일봉 150개 지나고부터 판단(주봉 ma20/느린틀 확보)
CADENCE = 1    # 매 거래일


def run(total=400):
    candles = load_stocks(SYMBOLS, total=total)
    if not candles:
        print("데이터 없음 — .env에 토스 키 넣었는지 확인")
        return
    ref = max(candles, key=lambda s: len(candles[s]["m5"]))  # 가장 긴 종목을 클럭으로
    clock = candles[ref]["m5"].index
    idx = list(range(WARMUP, len(clock), CADENCE))
    print(f"[bt] 종목 {len(candles)}, 판단 {len(idx)}일 ({clock[WARMUP].date()} ~ {clock[-1].date()})")

    bots = {
        "추세추종": RuleBot(Paper("추세추종")),
        "평균회귀": MeanRevBot(Paper("평균회귀")),
        "국면적응v4(현물)": RegimeAdaptiveBot(Paper("국면적응v4(현물)"), allow_short=False),
    }
    reg = Counter()
    for i in idx:
        ts = clock[i]
        snap = {}
        for s, c in candles.items():
            ind = compute_indicators(c["m5"], c["m4h"], ts)
            if ind:
                snap[s] = ind
        if not snap:
            continue
        pm = {s: d["current_price"] for s, d in snap.items()}
        for b in bots.values():
            b.step(ts, snap); b.paper.mark(ts, pm)
        for s, d in snap.items():
            reg[classify_regime(d)] += 1

    def stat(paper):
        ec = paper.equity_curve; end = ec[-1][1] if ec else config.START_KRW
        peak = config.START_KRW; mdd = 0
        for _, v in ec:
            peak = max(peak, v); mdd = min(mdd, v / peak - 1)
        sells = [t for t in paper.trades if t["side"] in ("SELL", "COVER")]
        wins = [t for t in sells if t.get("profit_pct", 0) > 0]
        return (round(end), round((end / config.START_KRW - 1) * 100, 2), round(mdd * 100, 2),
                len(sells), round(100 * len(wins) / len(sells), 1) if sells else 0)

    tot = sum(reg.values()) or 1
    print("국면 분포:", {k: f"{100*v//tot}%" for k, v in reg.items()})
    print("=" * 64)
    print("  전략               종료자산   수익률%   MDD%   매매  승률%")
    print("=" * 64)
    for name, b in bots.items():
        e, r, m, n, w = stat(b.paper)
        print(f"  {name:<16} {e:>10,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 64)


if __name__ == "__main__":
    run(400)
