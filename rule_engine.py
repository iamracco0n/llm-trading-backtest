# -*- coding: utf-8 -*-
"""규칙봇 = 젯슨 coin_analyzer(점수) + trade_manager(기준치 매매) 그대로 재현."""
import config


def analyze(ind):
    """coin_analyzer.analyze_coin 의 점수/추세 로직 그대로."""
    cp = ind["current_price"]; ma20 = ind["ma20"]; ma60 = ind["ma60"]
    rsi = ind["rsi"]; vr = ind["volume_ratio"]; r1h = ind["return_1h"]
    bb_upper = ind["bb_upper"]; atr = ind["atr"]
    macd = ind["macd"]; signal = ind["signal"]
    current_4h = ind["current_4h"]; ma20_4h = ind["ma20_4h"]

    score = 0
    # 추세
    if cp > ma20 > ma60:
        trend = "상승"; score += 40
    elif cp > ma60:
        trend = "횡보"; score += 20
    else:
        trend = "하락"; score -= 30
    # RSI
    if 45 <= rsi <= 60:   score += 30
    elif 35 <= rsi < 60:  score += 20
    elif 25 <= rsi < 35:  score += 10
    elif 60 <= rsi < 70:  score += 0
    elif 70 <= rsi < 75:  score -= 20
    else:                 score -= 100
    # 거래량
    if vr > 2:     score += 20
    elif vr > 1:   score += 10
    elif vr > 0.7: score += 5
    elif vr < 0.1: score -= 100
    elif vr < 0.2: score -= 20
    elif vr < 0.3: score -= 50
    elif vr < 0.5: score -= 20
    # 최근 1시간 상승률
    if r1h > 5:        score -= 20
    elif r1h > 3:      score -= 10
    elif 0 < r1h < 2:  score += 10
    # 볼린저
    if cp > bb_upper:  score -= 15
    # ATR
    atr_ratio = atr / cp if cp else 0
    if atr_ratio > 0.03:   score -= 15
    elif atr_ratio < 0.01: score += 5
    # MACD
    score += 10 if macd > signal else -10
    # 4시간봉 추세
    score += 10 if current_4h > ma20_4h else -30

    return {"score": score, "trend": trend, "rsi": round(rsi, 1),
            "volume_ratio": round(vr, 2)}


class RuleBot:
    def __init__(self, paper):
        self.paper = paper

    def step(self, ts, snapshot):
        """snapshot = {ticker: indicators}. 젯슨 manage_trade 순서 그대로."""
        p = self.paper
        analysis = {t: analyze(ind) for t, ind in snapshot.items()}

        # ---- 보유 종목 관리 (청산) ----
        for ticker in list(p.positions.keys()):
            if ticker not in snapshot:
                continue
            pos = p.positions[ticker]
            price = snapshot[ticker]["current_price"]
            profit = price / pos["buy_price"] - 1
            hold_h = (ts - pos["buy_time"]).total_seconds() / 3600

            if profit >= config.TAKE_PROFIT:
                p.sell(ticker, price, ts, "익절"); continue
            if profit <= config.STOP_LOSS:
                p.sell(ticker, price, ts, "손절"); continue
            if hold_h >= config.MAX_HOLD_HOURS:
                if profit > config.MAX_HOLD_MIN_PROFIT:
                    p.sell(ticker, price, ts, "시간만료"); continue
                else:
                    pos["buy_time"] = ts  # 보유기간 연장
            # 추세붕괴
            if analysis[ticker]["trend"] == "하락":
                pos["trend_break"] += 1
                if pos["trend_break"] >= config.TREND_BREAK_LIMIT:
                    p.sell(ticker, price, ts, "추세붕괴"); continue
            else:
                pos["trend_break"] = 0

        # ---- 신규 매수 ----
        ranked = sorted(analysis.items(), key=lambda x: x[1]["score"], reverse=True)
        for ticker, a in ranked:
            if p.n_positions() >= config.MAX_POSITION:
                break
            if p.has(ticker):
                continue
            if a["score"] < config.SCORE_MIN:
                continue
            if a["volume_ratio"] < config.VOL_MIN:
                continue
            if a["rsi"] > config.RSI_MAX:
                continue
            price = snapshot[ticker]["current_price"]
            p.buy(ticker, price, ts, reason=f"점수{a['score']}")
