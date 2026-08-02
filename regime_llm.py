# -*- coding: utf-8 -*-
"""LLM 국면분류 버전 — 규칙(classify_regime) 대신 LLM이 각 코인 국면을 판단.
전략 실행(상승→추세추종/횡보→평균회귀/하락→숏)은 RegimeAdaptiveBot 그대로,
'국면 판단'만 LLM으로 교체. 규칙 국면판단 vs LLM 국면판단을 같은 데이터로 비교.
"""
import re
import json
import requests
import config
from regime_adaptive import RegimeAdaptiveBot, classify_regime

REGIME_SYSTEM = (
    "너는 암호화폐 시장 국면 분류기다. 각 코인 지표를 보고 국면을 셋 중 하나로 판단한다:\n"
    "- up   : 강한 상승추세 (추세추종 롱에 적합)\n"
    "- down : 강한 하락추세 (숏에 적합)\n"
    "- range: 횡보 또는 약한/불확실한 추세 (평균회귀에 적합)\n"
    "확실한 추세가 아니면 range로 분류하라. 출력은 오직 JSON."
)

REGIME_SCHEMA = {
    "type": "object",
    "properties": {
        "regimes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "regime": {"type": "string", "enum": ["up", "down", "range"]},
                },
                "required": ["ticker", "regime"],
            },
        }
    },
    "required": ["regimes"],
}


def _fmt_market(snapshot):
    lines = []
    for t, d in snapshot.items():
        sep = (d["ma20"] - d["ma60"]) / d["ma60"] * 100 if d["ma60"] else 0
        lines.append(
            f"  {t}: 가격 {d['current_price']:.4g}, MA20-60이격 {sep:+.2f}%, "
            f"RSI {d['rsi']:.0f}, MACD {'상향' if d['macd'] > d['signal'] else '하향'}, "
            f"1H {d['return_1h']:+.1f}%, 일봉추세 {'상승' if d['current_4h'] > d['ma20_4h'] else '하락'}"
        )
    return "\n".join(lines)


def ask_regime(snapshot):
    prompt = ("각 코인의 현재 국면을 분류하라.\n\n[지표]\n" + _fmt_market(snapshot)
              + '\n\n출력(JSON): {"regimes":[{"ticker":"KRW-BTC","regime":"up|down|range"}]}')
    payload = {
        "model": config.LLM_MODEL,
        "messages": [{"role": "system", "content": REGIME_SYSTEM},
                     {"role": "user", "content": prompt}],
        "stream": False, "think": False, "format": REGIME_SCHEMA,
        "options": {"temperature": 0.2},
    }
    if config.NUM_GPU is not None:
        payload["options"]["num_gpu"] = config.NUM_GPU
    r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    text = re.sub(r"<think>.*?</think>", "", r.json()["message"]["content"], flags=re.DOTALL)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    out = {}
    if m:
        try:
            for x in json.loads(m.group(0)).get("regimes", []):
                if isinstance(x, dict) and x.get("regime") in ("up", "down", "range"):
                    out[x.get("ticker")] = x["regime"]
        except Exception:
            pass
    return out


class LLMRegimeBot(RegimeAdaptiveBot):
    def __init__(self, paper):
        super().__init__(paper)
        self.agree = 0
        self.total = 0

    def _regimes(self, ts, snapshot):
        try:
            llm = ask_regime(snapshot)
        except Exception as e:
            print(f"[llm] 국면분류 실패 {ts}: {e}")
            llm = {}
        # LLM이 빠뜨린 종목은 규칙으로 보완 + 규칙과 일치율 집계
        out = {}
        for t, d in snapshot.items():
            rule = classify_regime(d)
            reg = llm.get(t, rule)
            out[t] = reg
            self.total += 1
            if reg == rule:
                self.agree += 1
        return out
