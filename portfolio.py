# -*- coding: utf-8 -*-
"""페이퍼(모의) 계좌 — 롱/숏 지원. 수수료·체결 동일 규칙.
숏은 백테스트 시뮬용(가격 하락에 베팅). 실거래는 선물 거래소 필요(업비트=현물전용).
"""
import config


class Paper:
    def __init__(self, name, start_krw=config.START_KRW, fee=config.FEE):
        self.name = name
        self.krw = float(start_krw)
        self.fee = fee
        # long : {"side":"long","qty","buy_price","buy_time","trend_break"}
        # short: {"side":"short","margin","entry_price","buy_time","trend_break"}
        self.positions = {}
        self.trades = []
        self.equity_curve = []

    def n_positions(self):
        return len(self.positions)

    def has(self, ticker):
        return ticker in self.positions

    def side(self, ticker):
        return self.positions.get(ticker, {}).get("side")

    # ---- 롱 진입 ----
    def buy(self, ticker, price, ts, krw_amount=config.BUY_AMOUNT, reason=""):
        if self.krw < krw_amount or price <= 0:
            return False
        qty = (krw_amount * (1 - self.fee)) / price
        self.krw -= krw_amount
        self.positions[ticker] = {
            "side": "long", "qty": qty, "buy_price": price,
            "buy_time": ts, "trend_break": 0,
        }
        self.trades.append({"ts": ts, "ticker": ticker, "side": "BUY",
                            "price": price, "krw": krw_amount, "reason": reason})
        return True

    # ---- 숏 진입 (가격 하락에 베팅, 시뮬) ----
    def short(self, ticker, price, ts, krw_amount=config.BUY_AMOUNT, reason=""):
        if self.krw < krw_amount or price <= 0:
            return False
        self.krw -= krw_amount  # 증거금 락
        self.positions[ticker] = {
            "side": "short", "margin": krw_amount, "entry_price": price,
            "buy_time": ts, "trend_break": 0,
        }
        self.trades.append({"ts": ts, "ticker": ticker, "side": "SHORT",
                            "price": price, "krw": krw_amount, "reason": reason})
        return True

    # ---- 청산 (롱=매도, 숏=커버, 자동 판별) ----
    def close(self, ticker, price, ts, reason=""):
        if ticker not in self.positions:
            return False
        pos = self.positions[ticker]
        if pos["side"] == "long":
            proceeds = pos["qty"] * price * (1 - self.fee)
            profit_pct = (price / pos["buy_price"] - 1) * 100
            self.krw += proceeds
            rec_side = "SELL"
        else:  # short
            m = pos["margin"]; entry = pos["entry_price"]
            pnl = (entry - price) / entry          # 가격 하락 → 이익
            proceeds = m * (1 + pnl) - 2 * self.fee * m   # 진입+청산 수수료
            profit_pct = (proceeds / m - 1) * 100
            self.krw += proceeds
            rec_side = "COVER"
        self.trades.append({"ts": ts, "ticker": ticker, "side": rec_side,
                            "price": price, "profit_pct": profit_pct, "reason": reason})
        del self.positions[ticker]
        return True

    # 하위호환: 기존 롱 봇들은 sell() 호출 → close()로
    def sell(self, ticker, price, ts, reason=""):
        return self.close(ticker, price, ts, reason)

    def equity(self, price_map):
        val = self.krw
        for t, pos in self.positions.items():
            p = price_map.get(t)
            if not p:
                continue
            if pos["side"] == "long":
                val += pos["qty"] * p
            else:  # short: 증거금 + 미실현손익
                m = pos["margin"]; entry = pos["entry_price"]
                val += m * (1 + (entry - p) / entry)
        return val

    def mark(self, ts, price_map):
        self.equity_curve.append((ts, self.equity(price_map)))
