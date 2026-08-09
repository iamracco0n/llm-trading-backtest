# -*- coding: utf-8 -*-
"""v5 — 실적 공시 본문을 읽고 '어닝 서프라이즈 강도'를 판정(PEAD용).

Phase 3(촉매 유무)와 다름: 여기선 실적의 質·강도를 등급화해서, 강한 서프라이즈만
매수하는 게 규칙(실적개선이면 다 매수)보다 나은지 검증. LLM이 진짜 밥값하는 유일한
니치=텍스트→신호를, 펀더멘털이 가격을 끄는 전략(실적드리프트)에서 시험.

ollama=aurora qwen3:30b(CPU). OLLAMA_HOST 기본 localhost:11435(SSH포워딩).
"""
import os
import json
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3:30b")

SYSTEM = (
    "너는 한국 주식 실적 공시 분석가다. 주어진 실적 공시 본문을 읽고 '어닝 서프라이즈 강도'를 "
    "냉정하게 등급화한다. 과장·낙관 금지. 판정 기준:\n"
    "- 강한호재: 흑자전환, 또는 영업이익/순이익이 전년동기比 대폭(+30% 이상) 증가, 또는 명백한 대규모 개선.\n"
    "- 약한호재: 영업이익 소폭(+대략 5~30%) 증가, 매출만 늘고 이익은 미미, 개선이지만 강도 약함.\n"
    "- 중립: 실적공시 '예고'(확정치 아님), 변동 미미, 판단 근거 부족.\n"
    "- 악재: 적자전환, 영업이익 감소, 어닝 쇼크.\n"
    "숫자(영업이익/매출의 전년동기比 증감률)가 본문에 있으면 그걸 근거로. score=서프라이즈 강도 0~100."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["강한호재", "약한호재", "중립", "악재"]},
        "score": {"type": "integer"},
        "yoy": {"type": "string"},      # 영업이익/매출 전년比 요약(있으면)
        "reason": {"type": "string"},
    },
    "required": ["verdict", "score", "reason"],
}


def judge_earnings(report_nm, body_text, timeout=300):
    prompt = (f"[공시제목] {report_nm}\n[본문]\n{body_text}\n\n"
              "위 실적 공시의 어닝 서프라이즈 강도를 판정해 JSON으로만 답하라.")
    payload = {
        "model": MODEL, "prompt": prompt, "system": SYSTEM,
        "stream": False, "format": SCHEMA, "think": False,
        # num_gpu는 기본 0(CPU) — A(qwen3:30b)·C(qwen3.6:35b) 판정이 이 설정으로 만들어졌으므로
        # 재현성을 위해 기본값을 바꾸지 않는다. GPU로 돌리려면 LLM_NUM_GPU=99 로 실행.
        # ⚠️ CPU↔GPU는 부동소수점 차이로 판정이 미세하게 갈릴 수 있다(모델은 동일).
        "options": {"temperature": 0.0,
                    "num_gpu": int(os.environ.get("LLM_NUM_GPU", "0"))},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/generate", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read())
        out = json.loads(j["response"])
        return {"verdict": out["verdict"], "score": int(out.get("score", 0)),
                "yoy": out.get("yoy", "")[:60], "reason": out.get("reason", "")[:120]}
    except Exception:
        return None


if __name__ == "__main__":
    from dart_data import fetch_document_text
    import pickle
    ev = pickle.load(open("cache/v5_earnings_events.pkl", "rb"))
    code = list(ev)[1]
    _, rn, nm = ev[code][0]
    txt = fetch_document_text(rn)
    print("제목:", nm)
    print("판정:", judge_earnings(nm, txt))
