# -*- coding: utf-8 -*-
"""젯슨 라이브봇(HTF: 1h Donchian돌파+샹들리에트레일링+BTC국면필터) vs v4(국면적응).
같은 90일 다국면 데이터로 정면 비교 — 젯슨 봇을 v4로 바꾸는 게 실제로 나은지 검증.
"""
from collections import Counter

import config
from backtest_long import load_long, CADENCE, WARMUP
from indicators import compute_indicators
from portfolio import Paper
from rule_engine import RuleBot
from meanrev_backtest import MeanRevBot
from regime_adaptive import RegimeAdaptiveBot, classify_regime

CHAND_MULT = 3.0   # 샹들리에 트레일링: 최고가 - 3×ATR


def compute_htf(m60, mday, asof):
    """젯슨 htf_indicators.get_htf 그대로 (시간봉 기준)."""
    d = m60[m60.index <= asof]
    if len(d) < 55:
        return None
    w = d.iloc[-120:]
    close, high, low = w["close"], w["high"], w["low"]
    cur = float(close.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    dc_high = float(high.iloc[-21:-1].max())            # 직전 20봉 고점(현재봉 제외)
    pc = close.shift()
    tr = (high - low).combine((high - pc).abs(), max).combine((low - pc).abs(), max)
    atr = float(tr.rolling(14).mean().iloc[-1])
    mom24 = float(cur / close.iloc[-25] - 1) if len(close) > 25 else 0.0
    if atr != atr or ma50 != ma50:
        return None
    return {"current_price": cur, "ma50": ma50, "dc_high": dc_high,
            "atr": atr, "mom24": mom24}


def btc_risk_on(btc_mday, asof):
    """BTC 일봉 종가 > 일봉 MA50 (마지막 완성봉) → 위험선호."""
    dd = btc_mday[btc_mday.index <= asof]
    if len(dd) < 52:
        return False
    ma50 = dd["close"].rolling(50).mean()
    return bool(dd["close"].iloc[-2] > ma50.iloc[-2])


class HTFBot:
    def __init__(self, paper):
        self.paper = paper

    def step(self, ts, htf, risk_on):
        p = self.paper
        # 청산: 샹들리에 트레일링
        for t in list(p.positions.keys()):
            if t not in htf:
                continue
            pos = p.positions[t]; d = htf[t]; price = d["current_price"]
            peak = max(pos.get("peak_high", pos["buy_price"]), price)
            pos["peak_high"] = peak
            if price <= peak - CHAND_MULT * d["atr"]:
                p.close(t, price, ts, "트레일청산")
        # 진입: BTC 위험선호 + Donchian 돌파 + MA50 위, 모멘텀 강한 순
        if p.n_positions() >= config.MAX_POSITION or not risk_on:
            return
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


def run(days=90):
    candles = load_long(days)
    ref = "KRW-BTC" if "KRW-BTC" in candles else list(candles)[0]
    btc_mday = candles[ref]["m4h"]
    clock = candles[ref]["m5"].index
    idx = list(range(WARMUP, len(clock), CADENCE))
    print(f"[bt] 종목 {len(candles)}, 판단 {len(idx)}회 ({clock[WARMUP]} ~ {clock[-1]})")

    rule = RuleBot(Paper("추세추종(기본)"))
    mr = MeanRevBot(Paper("평균회귀"))
    v4 = RegimeAdaptiveBot(Paper("v4(숏포함)"))
    v4spot = RegimeAdaptiveBot(Paper("v4(현물,숏X)"), allow_short=False)
    htf = HTFBot(Paper("HTF(젯슨현재)"))
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
        rule.step(ts, snap); mr.step(ts, snap)
        v4.step(ts, snap); v4spot.step(ts, snap)
        htf.step(ts, htf_data, btc_risk_on(btc_mday, ts))
        for b in (rule, mr, v4, v4spot, htf):
            b.paper.mark(ts, pm)
        for t, d in snap.items():
            reg[classify_regime(d)] += 1

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
    print("국면 분포:", {k: f"{100*v//tot}%" for k, v in reg.items()})
    print("=" * 66)
    print("  전략               종료자산   수익률%    MDD%   매매  승률%")
    print("=" * 66)
    for b in (rule, mr, htf, v4spot, v4):
        e, r, m, n, w = stat(b.paper)
        print(f"  {b.paper.name:<16} {e:>11,} {r:>7} {m:>7} {n:>5} {w:>6}")
    print("=" * 66)


if __name__ == "__main__":
    run(90)
