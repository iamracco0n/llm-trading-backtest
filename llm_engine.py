# -*- coding: utf-8 -*-
"""LLM봇 v2 = 과매매 억제(프롬프트 규율 + 최소보유시간 레일)."""
import re
import json
import requests
import config

SYSTEM = (
    "너는 인내심 있는 암호화폐 스윙 트레이더다. 잦은 매매를 극도로 경계한다.\n"
    "규칙:\n"
    f"- 모의투자다. 1종목당 매수액 {config.BUY_AMOUNT:,}원 고정, 동시 보유 최대 {config.MAX_POSITION}종목.\n"
    "- ★매매할 때마다 왕복 0.1% 수수료가 나간다. 자주 사고팔면 수수료로 반드시 손해본다.\n"
    "- ★기본값은 hold(관망/유지)다. 매수·매도는 '분명한 근거'가 있을 때만 한다.\n"
    "- 작은 등락(±1% 안팎)에 반응하지 마라. 추세가 확실히 꺾이거나(익절), 확실히 살아날 때만 움직여라.\n"
    "- 익절은 서두르지 마라. +0.5% 먹자고 팔면 수수료 빼면 남는 게 없다. 최소 +3% 이상 목표.\n"
    "- 손절은 추세가 확실히 무너졌을 때. 노이즈성 하락엔 버텨라.\n"
    "- 확신 없으면 사지도 팔지도 마라(hold). 반드시 이유를 한 줄로.\n"
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

        # 1) 매도 먼저 — 최소보유시간 레일(뇌동매매 원천차단)
        for t in list(p.positions.keys()):
            d = dmap.get(t)
            if not (d and d.get("action") == "sell" and t in snapshot):
                continue
            pos = p.positions[t]
            price = snapshot[t]["current_price"]
            hold_h = (ts - pos["buy_time"]).total_seconds() / 3600
            profit = price / pos["buy_price"] - 1
            # 아직 어린 포지션은 매도 금지 (단 큰 손실이면 긴급 손절 허용)
            if hold_h < config.MIN_HOLD_HOURS_LLM and profit > config.EMERGENCY_STOP:
                continue
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
