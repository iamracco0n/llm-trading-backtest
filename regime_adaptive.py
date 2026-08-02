# -*- coding: utf-8 -*-
"""v4 국면 적응형 전략 — 시장 국면을 판단해 국면별 알고리즘을 적용.
  상승장 → 추세추종(눌림목 매수, +3%익절/추세붕괴/-4%손절)
  횡보장 → 평균회귀(볼린저하단+RSI과매도 매수, 평균MA20 복귀/과열 매도)
  하락장 → 방어(신규매수 금지, 보유는 손절만)
규칙 기반 국면판단(즉시). LLM 국면판단 버전은 regime_llm.py 참고.
"""
import config
import data as datamod
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot          # 순수 추세추종(비교용)
from meanrev_backtest import MeanRevBot  # 순수 평균회귀(비교용)

# 평균회귀 파라미터(횡보장 진입/청산)
MR_RSI_BUY = 35
MR_RSI_SELL = 65
KNIFE_1H = -6.0
STOP = -0.04
MAX_HOLD_H = 72


TREND_SEP = 0.006   # MA20-MA60 이격도 0.6% 이상이면 '강한 추세'(아니면 출렁이=range 취급)


def classify_regime(d):
    """국면 판단: up/down은 '강한 추세'일 때만, 약하거나 출렁이면 range(→평균회귀).
    강한 추세 = MA20이 MA60에서 TREND_SEP 이상 벌어짐 + 4시간봉 방향 일치.
    """
    up_4h = d["current_4h"] > d["ma20_4h"]
    price, ma20, ma60 = d["current_price"], d["ma20"], d["ma60"]
    sep = (ma20 - ma60) / ma60 if ma60 else 0
    if price > ma20 and sep > TREND_SEP and up_4h:
        return "up"
    if price < ma20 and sep < -TREND_SEP and not up_4h:
        return "down"
    return "range"


class RegimeAdaptiveBot:
    def __init__(self, paper, allow_short=True):
        self.paper = paper
        self.allow_short = allow_short   # False면 하락장에 숏 대신 현금(현물용)
        self.regime_log = []

    def _regimes(self, ts, snapshot):
        """국면 판단(규칙). 서브클래스가 LLM 판단으로 오버라이드 가능."""
        return {t: classify_regime(d) for t, d in snapshot.items()}

    def step(self, ts, snapshot):
        p = self.paper
        regimes = self._regimes(ts, snapshot)

        # ---- 청산: 롱(추세/평균회귀) / 숏 각각의 규칙 ----
        for t in list(p.positions.keys()):
            if t not in snapshot:
                continue
            pos = p.positions[t]; d = snapshot[t]
            price = d["current_price"]
            hold_h = (ts - pos["buy_time"]).total_seconds() / 3600
            strat = pos.get("strat", "trend")

            if pos["side"] == "short":
                profit = (pos["entry_price"] - price) / pos["entry_price"]  # 하락=이익
                if profit >= config.TAKE_PROFIT:
                    p.close(t, price, ts, "숏익절(하락)"); continue
                if profit <= STOP:
                    p.close(t, price, ts, "숏손절(반등)"); continue
                if regimes[t] != "down" or d["rsi"] <= 28:  # 하락장 끝/과매도 반등 위험
                    p.close(t, price, ts, "숏청산(국면전환)"); continue
                if hold_h >= MAX_HOLD_H:
                    p.close(t, price, ts, "시간만료"); continue
                continue

            # 롱
            profit = price / pos["buy_price"] - 1
            if profit <= STOP:
                p.close(t, price, ts, "손절"); continue
            if hold_h >= MAX_HOLD_H:
                p.close(t, price, ts, "시간만료"); continue
            if strat == "trend":
                if profit >= config.TAKE_PROFIT:
                    p.close(t, price, ts, "추세익절"); continue
                if regimes[t] == "down":
                    p.close(t, price, ts, "국면전환청산"); continue
            else:  # meanrev
                if price >= d["ma20"] or price >= d["bb_upper"] or d["rsi"] >= MR_RSI_SELL:
                    p.close(t, price, ts, "평균복귀익절"); continue

        # ---- 진입: 국면별 후보 수집 ----
        cands = []  # (우선순위, 정렬키, ticker, price, strat)
        for t, d in snapshot.items():
            if p.has(t):
                continue
            reg = regimes[t]
            if reg == "up":
                # 상승장 → 추세추종 롱
                if d["rsi"] <= config.RSI_MAX and d["macd"] > d["signal"] \
                   and d["volume_ratio"] >= config.VOL_MIN:
                    cands.append((0, -d["macd"], t, d["current_price"], "trend"))
            elif reg == "range":
                # 횡보장 → 평균회귀 롱 (과매도 반등)
                if d["current_price"] <= d["bb_lower"] and d["rsi"] <= MR_RSI_BUY \
                   and d["return_1h"] > KNIFE_1H:
                    cands.append((1, d["rsi"], t, d["current_price"], "meanrev"))
            elif reg == "down" and self.allow_short:
                # 하락장 → 숏 (하락에 베팅). 과매도(반등위험) 아닐 때, MACD 하향 확인
                if d["rsi"] >= 38 and d["macd"] < d["signal"]:
                    cands.append((2, d["rsi"], t, d["current_price"], "short"))
            # 하락장 + 숏금지(현물) → 현금 방어(진입 안 함)
        cands.sort(key=lambda x: (x[0], x[1]))
        for _, _, t, price, strat in cands:
            if p.n_positions() >= config.MAX_POSITION:
                break
            if strat == "short":
                p.short(t, price, ts, reason="숏진입(하락장)")
            else:
                p.buy(t, price, ts, reason=f"{strat}진입")
            p.positions[t]["strat"] = strat

        self.regime_log.append({"ts": str(ts),
                                "regimes": {t: r for t, r in regimes.items()}})


def run(days=7):
    candles = datamod.load_candles(config.COINS, days)
    clock = candles["KRW-BTC"]["m5"].index
    idx = list(range(config.WARMUP_BARS, len(clock), config.DECISION_INTERVAL_BARS))

    bots = {
        "추세추종": RuleBot(Paper("추세추종")),
        "평균회귀": MeanRevBot(Paper("평균회귀")),
        "국면적응v4": RegimeAdaptiveBot(Paper("국면적응v4")),
    }
    from collections import Counter
    reg_count = Counter()
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
            reg_count[classify_regime(d)] += 1

    def stat(paper):
        ec = paper.equity_curve; end = ec[-1][1] if ec else config.START_KRW
        peak = config.START_KRW; mdd = 0
        for _, v in ec:
            peak = max(peak, v); mdd = min(mdd, v/peak-1)
        sells = [t for t in paper.trades if t["side"] == "SELL"]
        wins = [t for t in sells if t.get("profit_pct", 0) > 0]
        return (round(end), round((end/config.START_KRW-1)*100, 2), round(mdd*100, 2),
                len(sells), round(100*len(wins)/len(sells), 1) if sells else 0)

    tot = sum(reg_count.values())
    print("국면 분포:", {k: f"{v}({100*v//tot}%)" for k, v in reg_count.items()})
    print("=" * 62)
    print("  전략             종료자산   수익률%   MDD%   매매  승률%")
    print("=" * 62)
    for name, b in bots.items():
        e, r, m, n, w = stat(b.paper)
        print(f"  {name:<14} {e:>10,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 62)


if __name__ == "__main__":
    run(7)
