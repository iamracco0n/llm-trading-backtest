# -*- coding: utf-8 -*-
"""Phase 3 — 로컬 LLM(qwen)이 공시 '본문'을 읽고 급등 촉매의 質을 판정.

키워드필터(Phase 2)는 제목만 봐서 '공급계약'이면 다 통과 → 매출대비 2.5%짜리 약재료도 삼.
LLM은 본문(계약금액/매출대비/증자목적 등)을 읽고 진짜 호재인지 判定.

ollama(aurora, qwen3:30b CPU) 구조화출력. 호스트는 OLLAMA_HOST(기본 localhost:11435,
=aurora로 SSH 포워딩된 포트). 모델정책: cpu=30b.
"""
import os
import json
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3:30b")

SYSTEM = (
    "너는 한국 주식 공시 분석가다. 주어진 공시 본문을 읽고, 이 공시가 '단기 주가 급등을 "
    "정당화할 실질 호재'인지 냉정하게 판정한다. 과장 금지. 기준:\n"
    "- 공급계약/수주: 계약금액이 최근 매출액 대비 몇 %인지가 핵심. 10%+면 강함, 3% 미만이면 약함.\n"
    "- 유상증자: 대개 악재(주식 희석). 시설투자 목적이면 중립.\n"
    "- 무상증자/자기주식취득: 단기 수급 호재.\n"
    "- 최대주주변경: 세력 유입 가능성(중립~호재), 단 불확실.\n"
    "- 실적: 흑자전환/대폭개선이면 호재, 악화면 악재.\n"
    "verdict는 호재/중립/악재 중 하나, score는 0~100(급등 재료 강도)."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["호재", "중립", "악재"]},
        "score": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "score", "reason"],
}


def judge(report_nm, body_text, timeout=300):
    """공시 하나 판정 → {"verdict","score","reason"} (실패시 None)."""
    prompt = (f"[공시제목] {report_nm}\n[본문]\n{body_text}\n\n"
              "위 공시를 판정해 JSON으로만 답하라.")
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": SYSTEM,
        "stream": False,
        "format": SCHEMA,
        "think": False,
        "options": {"temperature": 0.0, "num_gpu": 0},  # CPU 강제(30b)
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read())
        out = json.loads(j["response"])
        return {"verdict": out["verdict"], "score": int(out.get("score", 0)),
                "reason": out.get("reason", "")[:120]}
    except Exception as e:
        return None


if __name__ == "__main__":
    # 스모크: 방금 프로브한 삼성중공업 공급계약(매출대비 2.5%) 판정 테스트
    from dart_data import fetch_document_text
    txt = fetch_document_text("20260803800398")
    print("본문 일부:", txt[:200])
    print("판정:", judge("단일판매ㆍ공급계약체결", txt))
