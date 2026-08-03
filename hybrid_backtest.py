# -*- coding: utf-8 -*-
"""하이브리드 실험 — 현물에서 HTF(추세 돌파) + 평균회귀(횡보)를 한 봇에 결합.
동기: 젯슨(현물)은 HTF(+2.19%)가 최선이었지만(5장), HTF는 '돌파'에서만 진입 →
      횡보 구간엔 놀고 있다. 그 빈 구간을 평균회귀 롱으로 메우면 더 벌까?
숏 없음(현물). 같은 90일 다국면 데이터로 HTF/평균회귀/v4현물과 정면 비교.
"""
from collections import Counter

import config
from backtest_long import load_long, CADENCE, WARMUP
from indicators import compute_indicators
from portfolio import Paper
from meanrev_backtest import MeanRevBot
from regime_adaptive import (RegimeAdaptiveBot, classify_regime,
                             MR_RSI_BUY, MR_RSI_SELL, KNIFE_1H, STOP, MAX_HOLD_H)
from htf_vs_v4 import compute_htf, btc_risk_on, HTFBot, CHAND_MULT


class HybridBot:
    """HTF 돌파진입(샹들리에 트레일청산) + 횡보 평균회귀진입(평균복귀 청산)을 결합.
    포지션 한도(MAX_POSITION)는 공유. 돌파를 우선 채우고 남는 슬롯을 평균회귀로.
    각 포지션은 strat 태그로 청산 규칙을 분리.
    """
    def __init__(self, paper):
        self.paper = paper

    def step(self, ts, snap, htf, risk_on):
        p = self.paper
        # ---- 청산: strat별 규칙 ----
        for t in list(p.positions.keys()):
            pos = p.positions[t]; strat = pos.get("strat", "htf")
            if strat == "htf":
                if t not in htf:
                    continue
                d = htf[t]; price = d["current_price"]
                peak = max(pos.get("peak_high", pos["buy_price"]), price)
                pos["peak_high"] = peak
                if price <= peak - CHAND_MULT * d["atr"]:
                    p.close(t, price, ts, "트레일청산")
            else:  # meanrev
                if t not in snap:
                    continue
                d = snap[t]; price = d["current_price"]
                hold_h = (ts - pos["buy_time"]).total_seconds() / 3600
                if price / pos["buy_price"] - 1 <= STOP:
                    p.close(t, price, ts, "손절"); continue
                if price >= d["ma20"] or price >= d["bb_upper"] or d["rsi"] >= MR_RSI_SELL:
                    p.close(t, price, ts, "평균복귀익절"); continue
                if hold_h >= MAX_HOLD_H:
                    p.close(t, price, ts, "시간만료")

        # ---- 진입 1순위: HTF 돌파 (BTC 위험선호일 때만) ----
        if risk_on:
            cands = []
            for t, d in htf.items():
                if p.has(t):
                    continue
                if d["current_price"] > d["dc_high"] and d["current_price"] > d["ma50"]:
                    cands.append((d["mom24"], t, d["current_price"]))
            cands.sort(reverse=True)
            for mom, t, price in cands:
                if p.n_positions() >= config.MAX_POSITION:
                    break
                p.buy(t, price, ts, reason=f"돌파mom{mom*100:.0f}")
                p.positions[t]["peak_high"] = price
                p.positions[t]["strat"] = "htf"

        # ---- 진입 2순위: 남는 슬롯을 횡보 평균회귀로 ----
        mcands = []
        for t, d in snap.items():
            if p.has(t):
                continue
            if classify_regime(d) == "range" and d["current_price"] <= d["bb_lower"] \
               and d["rsi"] <= MR_RSI_BUY and d["return_1h"] > KNIFE_1H:
                mcands.append((d["rsi"], t, d["current_price"]))
        mcands.sort()
        for _, t, price in mcands:
            if p.n_positions() >= config.MAX_POSITION:
                break
            p.buy(t, price, ts, reason="평균회귀진입")
            p.positions[t]["strat"] = "meanrev"


def run(days=90):
    candles = load_long(days)
    ref = "KRW-BTC" if "KRW-BTC" in candles else list(candles)[0]
    btc_mday = candles[ref]["m4h"]
    clock = candles[ref]["m5"].index
    idx = list(range(WARMUP, len(clock), CADENCE))
    print(f"[bt] 종목 {len(candles)}, 판단 {len(idx)}회 ({clock[WARMUP]} ~ {clock[-1]})")

    mr = MeanRevBot(Paper("평균회귀"))
    v4spot = RegimeAdaptiveBot(Paper("v4(현물,숏X)"), allow_short=False)
    htf = HTFBot(Paper("HTF(젯슨현재)"))
    hyb = HybridBot(Paper("하이브리드(HTF+평균회귀)"))
    reg = Counter()
    for i in idx:
        ts = clock[i]
        snap = {}
        for t, c in candles.items():
            ind = compute_indicators(c["m5"], c["m4h"], ts)
            if ind:
                snap[t] = ind
        htf_data = {}
        for t, c in candles.items():
            h = compute_htf(c["m5"], c["m4h"], ts)
            if h:
                htf_data[t] = h
        if not snap:
            continue
        pm = {t: d["current_price"] for t, d in snap.items()}
        ron = btc_risk_on(btc_mday, ts)
        mr.step(ts, snap); v4spot.step(ts, snap)
        htf.step(ts, htf_data, ron); hyb.step(ts, snap, htf_data, ron)
        for b in (mr, v4spot, htf, hyb):
            b.paper.mark(ts, pm)
        for t, d in snap.items():
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

    tot = sum(reg.values())
    print("국면 분포:", {k: f"{100*v//tot}%" for k, v in reg.items()})
    print("=" * 70)
    print("  전략                     종료자산   수익률%    MDD%   매매  승률%")
    print("=" * 70)
    for b in (mr, htf, v4spot, hyb):
        e, r, m, n, w = stat(b.paper)
        print(f"  {b.paper.name:<20} {e:>11,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 70)


if __name__ == "__main__":
    run(90)
