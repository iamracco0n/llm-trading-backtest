# -*- coding: utf-8 -*-
"""LLM봇 = qwen3:14b가 지표를 보고 진입·청산을 스스로 판단(완전 자율)."""
import re
import json
import requests
import config

SYSTEM = (
    "너는 규율 있는 암호화폐 스윙 트레이더다. 좋은 기회는 확실히 잡되, 잡소리(노이즈)엔 안 흔들린다.\n"
    "규칙:\n"
    f"- 모의투자. 1종목당 {config.BUY_AMOUNT:,}원 고정, 동시 보유 최대 {config.MAX_POSITION}종목.\n"
    "- ★매수 신호: 상승추세(가격>MA20>MA60) + RSI 과열아님(70미만) + MACD 상향 이면 '분명한 기회'다 → 매수하라. 완벽한 확신 기다리지 마라, 셋업이 좋으면 진입.\n"
    "- ★현금만 쥐고 아무것도 안 하는 것도 손해다(기회비용). 상승 종목이 보이면 놓치지 말고 최대 3종목까지 담아라.\n"
    "- 매수 금지: 하락추세거나 RSI 과열(70+)이면 사지 마라. 애매하면(횡보·근거 약함) 관망.\n"
    "- 매도: +3% 익절 목표 / 추세 확실히 붕괴 or 손실 -4%면 손절. 작은 노이즈 등락(±1%)엔 버텨라(왕복 수수료 0.1%).\n"
    "- 요지: 과매매도 동결도 아닌 '규율 있는 매매'. 좋은 셋업=진입, 나쁜 셋업=관망, 애매=hold.\n"
    "- 반드시 이유 한 줄. 출력은 오직 JSON."
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


# 구조화 출력 스키마 — 모델이 무조건 이 형식으로 뱉게 강제 (ollama format)
OUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                    "reason": {"type": "string"},
                },
                "required": ["ticker", "action", "reason"],
            },
        }
    },
    "required": ["decisions"],
}


def _parse(text):
    # <think> 제거 후 첫 JSON 오브젝트 추출
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return []
    if isinstance(obj, dict) and isinstance(obj.get("decisions"), list):
        return obj["decisions"]
    # 폴백: 모델이 {"KRW-BTC":"hold",...} 또는 {"KRW-BTC":{"action":..}} 로 뱉는 경우
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                out.append({"ticker": k, "action": v, "reason": ""})
            elif isinstance(v, dict) and "action" in v:
                out.append({"ticker": k, "action": v.get("action"),
                            "reason": v.get("reason", "")})
    return out


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
        "format": OUT_SCHEMA,
        "options": {"temperature": config.LLM_TEMPERATURE},
    }
    if config.NUM_GPU is not None:
        payload["options"]["num_gpu"] = config.NUM_GPU  # 0 = 순수 CPU
    r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.LLM_TIMEOUT)
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

        # 1) 매도 먼저 (슬롯 확보) — 최소보유시간 레일 적용
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

        # 결정 로깅(이유 보존)
        self.decision_log.append({"ts": str(ts), "decisions": decisions})
