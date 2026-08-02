# -*- coding: utf-8 -*-
"""평균회귀(Mean Reversion) 전략 백테스트 — 횡보장용. LLM 없이 즉시.
전략: 볼린저 하단 + RSI 과매도에 매수 → 평균(MA20)/상단 복귀 또는 손절에 매도.
같은 데이터로 기존 추세추종 규칙봇과 비교.
"""
import config
import data as datamod
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot   # 기존 추세추종(비교용)

# ===== 평균회귀 파라미터 =====
RSI_BUY = 35        # 이하면 과매도 → 매수 후보
RSI_SELL = 65       # 이상이면 과열 → 매도
STOP_LOSS = -0.04   # 손절
MAX_HOLD_H = 48     # 최대 보유
KNIFE_1H = -6.0     # 최근 1시간 이보다 더 빠졌으면 낙하칼 → 매수 회피


class MeanRevBot:
    def __init__(self, paper):
        self.paper = paper

    def step(self, ts, snapshot):
        p = self.paper
        # ---- 청산 ----
        for t in list(p.positions.keys()):
            if t not in snapshot:
                continue
            pos = p.positions[t]; d = snapshot[t]
            price = d["current_price"]
            profit = price / pos["buy_price"] - 1
            hold_h = (ts - pos["buy_time"]).total_seconds() / 3600
            if profit <= STOP_LOSS:
                p.sell(t, price, ts, "손절"); continue
            # 평균회귀 완료: 가격이 MA20 위로 복귀 or 상단 터치 or RSI 과열
            if price >= d["ma20"] or price >= d["bb_upper"] or d["rsi"] >= RSI_SELL:
                p.sell(t, price, ts, "평균복귀익절"); continue
            if hold_h >= MAX_HOLD_H:
                p.sell(t, price, ts, "시간만료"); continue

        # ---- 진입: 과매도 반등 노림 ----
        # 후보: 볼린저 하단 이하 + RSI 과매도 + 낙하칼 아님, RSI 낮은 순
        cands = []
        for t, d in snapshot.items():
            if p.has(t):
                continue
            if d["current_price"] <= d["bb_lower"] and d["rsi"] <= RSI_BUY \
               and d["return_1h"] > KNIFE_1H:
                cands.append((d["rsi"], t, d["current_price"]))
        cands.sort()  # RSI 낮은(더 과매도) 순
        for _, t, price in cands:
            if p.n_positions() >= config.MAX_POSITION:
                break
            p.buy(t, price, ts, reason="과매도반등")


def run(days=7):
    candles = datamod.load_candles(config.COINS, days)
    clock = candles["KRW-BTC"]["m5"].index
    idx = list(range(config.WARMUP_BARS, len(clock), config.DECISION_INTERVAL_BARS))

    mr = MeanRevBot(Paper("평균회귀"))
    rule = RuleBot(Paper("추세추종규칙봇"))
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
        mr.step(ts, snap); rule.step(ts, snap)
        mr.paper.mark(ts, pm); rule.paper.mark(ts, pm)

    def stat(paper):
        ec = paper.equity_curve; end = ec[-1][1] if ec else config.START_KRW
        peak = config.START_KRW; mdd = 0
        for _, v in ec:
            peak = max(peak, v); mdd = min(mdd, v/peak-1)
        sells = [t for t in paper.trades if t["side"] == "SELL"]
        wins = [t for t in sells if t.get("profit_pct", 0) > 0]
        return (round(end), round((end/config.START_KRW-1)*100, 2), round(mdd*100, 2),
                len(sells), round(100*len(wins)/len(sells), 1) if sells else 0)

    print("=" * 60)
    print("  전략            종료자산   수익률%   MDD%   매매  승률%")
    print("=" * 60)
    for b in [rule, mr]:
        e, r, m, n, w = stat(b.paper)
        print(f"  {b.paper.name:<14} {e:>9,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 60)
    # 평균회귀 체결 상세
    sells = [t for t in mr.paper.trades if t["side"] == "SELL"]
    print(f"\n[평균회귀 체결 {len(sells)}건]")
    for t in sells:
        print("  %-11s %+6.2f%%  %s" % (t["ticker"], t.get("profit_pct", 0), t.get("reason", "")))


if __name__ == "__main__":
    run(7)
