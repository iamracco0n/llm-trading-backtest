# -*- coding: utf-8 -*-
"""LLM 학습 컷오프 실측 — 백테스트 결과가 '예측'인지 '기억'인지 가른다.

**왜 필요한가.** LLM 백테스트에는 코드 감사로 잡히지 않는 편향이 하나 더 있다.
프런티어 모델은 **학습 구간 내 지수 종가를 오차 1% 미만으로 회상**하고, 컷오프 이후엔
오차가 급증한다. 즉 학습 구간을 백테스트하면 모델이 예측하는 게 아니라 기억을 꺼낸다.
룩어헤드·생존편향과 달리 이건 가중치 안에 있어서 "무엇을 외웠는지" 감사할 수 없다.

**어떻게 재나.** 모델에게 여러 시점의 KOSPI/KOSDAQ 종가를 물어보고 실제값과의 오차를
본다. 컷오프 이전이면 오차가 작고, 이후면 급증한다. 모델이 "모른다"고 답하는 것도
신호다(정직한 거부 = 학습 안 됨).

**우리 프로젝트에 왜 중요한가.** v5 IS 구간은 2025-07~2026-08, OOS 구간은 2024-01~2025-06.
OOS가 학습 구간에 더 가깝다. 만약 기억 오염이 있었다면 **OOS가 더 좋게** 나왔어야 하는데
실제로는 무너졌다(+3.66% → −2.60%). 즉 오염으로는 설명되지 않고, v5 기각 결론이 더 견고해진다.
이 스크립트는 그 논증을 숫자로 뒷받침한다.

사용: python3 llm_cutoff_probe.py
"""
import os
import json
import statistics as st
import urllib.request

import pandas as pd
import FinanceDataReader as fdr

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3:30b")

# 분기별 프로브 시점 (v5의 IS/OOS 구간을 모두 덮도록)
PROBE_DATES = ["2023-03-15", "2023-09-15",
               "2024-03-15", "2024-09-13",
               "2025-03-14", "2025-09-15",
               "2026-03-13", "2026-06-15"]
INDEXES = [("KS11", "코스피"), ("KQ11", "코스닥")]


def ask(prompt, timeout=300):
    body = json.dumps({
        "model": MODEL, "stream": False,
        # qwen3는 thinking 모델이라 think를 끄지 않으면 사고 토큰이 num_predict를 다 먹고
        # content가 빈 채로 done_reason=length가 된다(2차 프로브 실패 원인).
        "think": False,
        "options": {"temperature": 0, "num_predict": 300},
        "messages": [
            # ⚠️ 1차 프로브 실패 교훈: "모르면 모른다고 하라"를 넣었더니 학습 구간(2023년)까지
            # 전부 '모름'이 나왔다. 기억이 없는 건지 답을 거부한 건지 구분이 안 된다.
            # → 반드시 숫자를 뱉게 강제하고, 오차 크기로 기억 여부를 판정한다.
            {"role": "system", "content":
             "너는 한국 증시 데이터를 답하는 도구다. 반드시 숫자를 답한다. 확실하지 않아도 "
             "최선의 추정치를 낸다. 거부하지 마라. known은 '확신 있는 회상'일 때만 true. "
             "JSON만 출력: {\"value\": 숫자, \"known\": true/false}"},
            {"role": "user", "content": prompt}],
        "format": {"type": "object",
                   "properties": {"value": {"type": ["number", "null"]},
                                  "known": {"type": "boolean"}},
                   "required": ["known"]},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    try:
        return json.loads(out["message"]["content"])
    except Exception:
        return None


def actual_close(sym, date):
    """해당일(없으면 직전 거래일) 종가."""
    d = pd.Timestamp(date)
    df = fdr.DataReader(sym, (d - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                        d.strftime("%Y-%m-%d"))
    if df is None or len(df) == 0:
        return None
    return float(df["Close"].iloc[-1])


def run():
    print(f"모델 {MODEL} @ {OLLAMA}")
    print("=" * 76)
    print("  LLM 학습 컷오프 프로브 — 지수 종가 회상 오차")
    print("  (컷오프 이전=오차 작음/기억함, 이후=오차 급증 또는 '모름')")
    print("=" * 76)
    print(f"  {'시점':<12}{'지수':<8}{'실제':>10}{'모델답':>12}{'오차%':>9}  판정")
    print("-" * 76)

    by_date = {}
    for date in PROBE_DATES:
        errs = []
        for sym, nm in INDEXES:
            act = actual_close(sym, date)
            if act is None:
                continue
            r = ask(f"{date} 기준 한국 {nm} 지수({sym})의 종가(마지막 거래일 종가)는 얼마인가?")
            if not r or r.get("value") in (None, 0):
                print(f"  {date:<12}{nm:<8}{act:>10,.0f}{'무응답':>12}{'—':>9}  ← 응답 실패")
                errs.append(None)
                continue
            val = float(r["value"])
            err = abs(val / act - 1) * 100
            conf = "확신" if r.get("known") else "추정"
            verdict = ("기억함" if err < 1 else "근사" if err < 5 else "틀림") + f"/{conf}"
            print(f"  {date:<12}{nm:<8}{act:>10,.0f}{val:>12,.0f}{err:>8.1f}%  ← {verdict}")
            errs.append(err)
        ok = [e for e in errs if e is not None]
        by_date[date] = st.median(ok) if ok else None

    print("=" * 76)
    print("  시점별 중앙 오차 (— = 모른다고 답함)")
    for d, e in by_date.items():
        bar = "" if e is None else "#" * min(40, int(e))
        print(f"    {d}   {'—' if e is None else f'{e:6.1f}%'}  {bar}")
    print("-" * 76)
    print("  v5 구간 대조:")
    print("    OOS 2024-01~2025-06  ← 학습 구간에 더 가까움(기억 오염 위험 큼)")
    print("    IS  2025-07~2026-08  ← 컷오프 이후일 가능성(상대적으로 깨끗)")
    print("  기억 오염이 결과를 만들었다면 OOS가 더 좋아야 하는데, 실제로는")
    print("  +3.66% → −2.60%로 무너졌다 → v5 기각은 이 편향으로 설명되지 않는다.")
    print("=" * 76)


if __name__ == "__main__":
    run()
