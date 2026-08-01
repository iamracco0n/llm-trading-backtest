# -*- coding: utf-8 -*-
"""페이퍼(모의) 계좌 — 두 봇이 각자 하나씩. 수수료·체결 동일 규칙."""
import config


class Paper:
    def __init__(self, name, start_krw=config.START_KRW, fee=config.FEE):
        self.name = name
        self.krw = float(start_krw)
        self.fee = fee
        # positions[ticker] = {"qty", "buy_price", "buy_time", "trend_break": int}
        self.positions = {}
        self.trades = []   # 체결 로그
        self.equity_curve = []  # (timestamp, equity)

    def n_positions(self):
        return len(self.positions)

    def has(self, ticker):
        return ticker in self.positions

    def buy(self, ticker, price, ts, krw_amount=config.BUY_AMOUNT, reason=""):
        if self.krw < krw_amount or price <= 0:
            return False
        qty = (krw_amount * (1 - self.fee)) / price
        self.krw -= krw_amount
        self.positions[ticker] = {
            "qty": qty, "buy_price": price, "buy_time": ts, "trend_break": 0,
        }
        self.trades.append({
            "ts": ts, "ticker": ticker, "side": "BUY", "price": price,
            "krw": krw_amount, "reason": reason,
        })
        return True

    def sell(self, ticker, price, ts, reason=""):
        if ticker not in self.positions:
            return False
        pos = self.positions[ticker]
        proceeds = pos["qty"] * price * (1 - self.fee)
        cost = config.BUY_AMOUNT  # 균일 매수액 기준 손익
        profit_pct = (price / pos["buy_price"] - 1) * 100
        self.krw += proceeds
        self.trades.append({
            "ts": ts, "ticker": ticker, "side": "SELL", "price": price,
            "krw": proceeds, "profit_pct": profit_pct, "reason": reason,
        })
        del self.positions[ticker]
        return True

    def equity(self, price_map):
        """현재 시세로 평가한 총자산(현금 + 보유평가액)."""
        val = self.krw
        for t, pos in self.positions.items():
            p = price_map.get(t)
            if p:
                val += pos["qty"] * p
        return val

    def mark(self, ts, price_map):
        self.equity_curve.append((ts, self.equity(price_map)))
