# -*- coding: utf-8 -*-
"""LLM봇 v1 = qwen3가 지표를 보고 진입·청산을 스스로 판단(완전 자율)."""
import re
import json
import requests
import config

SYSTEM = (
    "너는 암호화폐 단타 트레이더다. 지표만 보고 냉정하게 판단한다.\n"
    "규칙:\n"
    f"- 모의투자다. 1종목당 매수액은 {config.BUY_AMOUNT:,}원 고정, 동시 보유 최대 {config.MAX_POSITION}종목.\n"
    "- 목표는 총자산 극대화. 손실 관리와 수익 실현을 스스로 결정한다.\n"
    "- 보유중 종목은 hold(유지) 또는 sell(매도) 중 선택.\n"
    "- 미보유 종목은 buy(매수) 또는 hold(관망) 중 선택.\n"
    "- 확신 없으면 무리하게 사지 마라. 반드시 이유를 한 줄로 남겨라.\n"
    "- 출력은 오직 JSON. 설명 문장 금지."
)

OUT_SPEC = (
    '{"decisions":[{"ticker":"KRW-BTC","action":"buy|sell|hold","reason":"한줄이유"}]}'
)


def _fmt_positions(paper, snapshot, ts):
    if not paper.positions:
        return "(없음)"
    lines = []
    for t, pos in paper.positions.items():
        price = snapshot.get(t, {}).get("current_price", pos["buy_price"])
        pnl = (price / pos["buy_price"] - 1) * 100
        hold_h = (ts - pos["buy_time"]).total_seconds() / 3600
        lines.append(f"  {t}: 평가손익 {pnl:+.2f}%, 보유 {hold_h:.1f}시간")
    return "\n".join(lines)


def _fmt_market(snapshot):
    lines = []
    for t, d in snapshot.items():
        trend = "상승" if d["current_price"] > d["ma20"] > d["ma60"] else (
            "횡보" if d["current_price"] > d["ma60"] else "하락")
        macd_state = "상향" if d["macd"] > d["signal"] else "하향"
        lines.append(
            f"  {t}: 가격 {d['current_price']:.4g}, 추세 {trend}, "
            f"RSI {d['rsi']:.0f}, 거래량비 {d['volume_ratio']:.2f}, "
            f"1H {d['return_1h']:+.1f}%, MACD {macd_state}, "
            f"4H {'상승' if d['current_4h'] > d['ma20_4h'] else '하락'}"
        )
    return "\n".join(lines)


def _parse(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
        return obj.get("decisions", [])
    except Exception:
        return []


def ask_llm(paper, snapshot, ts):
    prompt = (
        f"[현재 시각] {ts}\n"
        f"[보유 현금] {paper.krw:,.0f}원\n"
        f"[보유 종목]\n{_fmt_positions(paper, snapshot, ts)}\n\n"
        f"[시장 지표]\n{_fmt_market(snapshot)}\n\n"
        f"위 상황에서 각 종목에 대한 매매 결정을 내려라.\n"
        f"출력 형식(JSON): {OUT_SPEC}"
    )
    payload = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": config.LLM_TEMPERATURE},
    }
    r = requests.post(config.OLLAMA_URL, json=payload, timeout=300)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    return _parse(content)


class LLMBot:
    def __init__(self, paper):
        self.paper = paper
        self.decision_log = []

    def step(self, ts, snapshot):
        p = self.paper
        try:
            decisions = ask_llm(p, snapshot, ts)
        except Exception as e:
            print(f"[llm] 호출 실패 {ts}: {e}")
            return

        dmap = {d.get("ticker"): d for d in decisions if isinstance(d, dict)}

        # 1) 매도 먼저 (슬롯 확보)
        for t in list(p.positions.keys()):
            d = dmap.get(t)
            if d and d.get("action") == "sell" and t in snapshot:
                price = snapshot[t]["current_price"]
                p.sell(t, price, ts, "LLM매도:" + str(d.get("reason", ""))[:40])

        # 2) 매수
        for t, d in dmap.items():
            if p.n_positions() >= config.MAX_POSITION:
                break
            if d.get("action") != "buy":
                continue
            if t not in snapshot or p.has(t):
                continue
            price = snapshot[t]["current_price"]
            p.buy(t, price, ts, reason="LLM매수:" + str(d.get("reason", ""))[:40])

        self.decision_log.append({"ts": str(ts), "decisions": decisions})
