# -*- coding: utf-8 -*-
"""v7 — 제안(propose) → 비평(critique) 다단계 구성. 우리가 아직 안 해본 유일한 변형.

**지금까지 테스트한 앙상블과 뭐가 다른가.**
v5 모델비교에서 잰 앙상블은 **독립 판정 후 합의**였다(A·C·E가 각자 보고 교집합). 결과는
3모델 만장일치가 A 단독과 H+40·H+90 소수점까지 동일 — 얻는 것 없음.

여기서는 **순차 비평**이다. 비평자는 공시 본문뿐 아니라 **제안자의 등급·점수·근거까지**
보고 동의/수정한다. 독립 판정이 아니라 *상호작용*이라 구조가 다르다. TradingAgents 계열
(95k★)이 쓰는 패턴이고, 우리 벤치마크로 검증된 적이 없다.

**왜 그래도 기대가 낮은가(그럼에도 재는 이유).**
비평이 효과를 내려면 제안자가 *틀려야* 한다. 그런데 우리 실측에서 LLM 판정은 이미
정확했다 — 매출 −66.7%·적자전환을 정확히 악재로, 무상증자를 "실질 호재 아님"으로 정확히
분류했다. **틀린 걸 고치는 게 아니라, 맞는데 가격과 무관한 걸 고쳐야 하는 상황**이다.
그래도 이건 추론이고, 재보면 끝난다.

**통과 기준(결과 보기 전 고정)**: 비평 후가 제안자 단독(C)을 **전 지평에서 이기고**,
score≥95 절대값이 **플러스**여야 한다. 못 넘으면 8번째 기각이다.

**설계**: 제안 = 이미 있는 C(qwen3.6:35b) 판정 697건(`reason` 포함, 재사용 → 추가 호출 0).
비평만 새로 돌린다. 변수는 '비평 단계 유무' 하나뿐.

사용:
  LLM_MODEL=qwen3.6:35b python3 v7_critique.py judge --tag self    # 자기비평
  LLM_MODEL=gemma4:12b  python3 v7_critique.py judge --tag cross   # 교차비평
  python3 v7_critique.py compare --tag self
"""
import os
import sys
import json
import time
import pickle
import argparse
import urllib.request
from collections import Counter

from dart_data import fetch_document_text
from v5_oos import (_alpha_tables, _s, HORIZONS, EV_OOS, JG_OOS, PX_OOS, CACHE, jg_path)

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3.6:35b")
NUM_GPU = int(os.environ.get("LLM_NUM_GPU", "0"))     # 기본 CPU (에어컨 없을 때 GPU 금지)

SYSTEM = (
    "너는 실적 공시 판정을 검토하는 2차 심사자다. 1차 분석가의 판정과 근거가 주어진다.\n"
    "본문을 직접 읽고 1차 판정이 타당한지 검토해 **최종 판정**을 내려라.\n"
    "- 1차가 타당하면 그대로 유지한다(동의하는 것도 정당한 결론이다).\n"
    "- 근거가 본문과 어긋나거나, 강도를 과대/과소평가했으면 수정한다.\n"
    "등급 기준: 강한호재=흑자전환 또는 영업이익/순이익 전년동기比 +30%↑ 또는 명백한 대규모 개선. "
    "약한호재=영업이익 +5~30% 또는 개선이나 강도 약함. 중립=예고공시·변동 미미·근거부족. "
    "악재=적자전환·영업이익 감소·어닝쇼크.\n"
    "score는 최종 서프라이즈 강도 0~100. JSON만 출력."
)
SCHEMA = {"type": "object",
          "properties": {"verdict": {"type": "string",
                                     "enum": ["강한호재", "약한호재", "중립", "악재"]},
                         "score": {"type": "integer"},
                         "agree": {"type": "boolean"},
                         "reason": {"type": "string"}},
          "required": ["verdict", "score", "agree"]}


def critique(report_nm, body, first, timeout=900):
    user = (f"[공시제목] {report_nm}\n\n"
            f"[1차 분석가 판정] {first['verdict']} (score {first.get('score', 0)})\n"
            f"[1차 근거] {first.get('reason', '')}\n\n"
            f"[공시 본문]\n{body}\n\n"
            "위 1차 판정을 검토하고 최종 판정을 내려라.")
    payload = json.dumps({
        "model": MODEL, "stream": False, "think": False,
        "options": {"temperature": 0.0, "num_gpu": NUM_GPU, "num_predict": 400},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "format": SCHEMA,
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
        j = json.loads(out["message"]["content"])
        return {"verdict": j["verdict"], "score": int(j.get("score", 0)),
                "agree": bool(j.get("agree", True)), "reason": str(j.get("reason", ""))[:120]}
    except Exception:
        return None


def dst_path(tag):
    return os.path.join(CACHE, f"v7_critique_{tag}.pkl")


def cmd_judge(args):
    events = pickle.load(open(EV_OOS, "rb"))
    first = pickle.load(open(jg_path("qwen36"), "rb"))      # 제안 = C(추가 호출 0)
    dst = dst_path(args.tag)
    cache = pickle.load(open(dst, "rb")) if os.path.exists(dst) else {}

    uniq = {rn: nm for evs in events.values() for _, rn, nm in evs}
    todo = [(rn, nm) for rn, nm in uniq.items() if rn not in cache and rn in first]
    print(f"[v7] 비평 대상 {len(todo)}건 (캐시 {len(cache)})  model={MODEL}  "
          f"{'GPU' if NUM_GPU else 'CPU'} → {os.path.basename(dst)}")
    t0, consec = time.time(), 0
    for i, (rn, nm) in enumerate(todo):
        f = first[rn]
        if f.get("reason") in (None, "본문없음"):
            cache[rn] = dict(f, agree=True)
            continue
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            cache[rn] = dict(f, agree=True)
            continue
        res = None
        for a in range(3):
            res = critique(nm, body, f)
            if res:
                break
            time.sleep(5 * (a + 1))
        if not res:                       # 실패를 '중립'으로 캐시하면 데이터가 오염된다
            consec += 1
            print(f"[v7] 비평 실패({consec}연속) {rn} — 미캐시", flush=True)
            if consec >= 5:
                pickle.dump(cache, open(dst, "wb"))
                sys.exit(f"[v7] 연속 5회 실패 — 연결 확인 후 재실행. 진행분 {len(cache)}건")
            continue
        consec = 0
        res["nm"] = nm
        cache[rn] = res
        if (i + 1) % 10 == 0:
            el = time.time() - t0
            print(f"[v7] {i+1}/{len(todo)}  {nm[:14]} → {res['verdict']}({res['score']})"
                  f"{'' if res['agree'] else ' ★수정'}   ETA {el/(i+1)*(len(todo)-i-1)/60:.0f}분",
                  flush=True)
            pickle.dump(cache, open(dst, "wb"))
    pickle.dump(cache, open(dst, "wb"))
    print(f"[v7] 완료 {len(cache)}건, {(time.time()-t0)/60:.0f}분")


def cmd_compare(args):
    ev = pickle.load(open(EV_OOS, "rb"))
    px = pickle.load(open(PX_OOS, "rb"))
    A = pickle.load(open(JG_OOS, "rb"))
    C = pickle.load(open(jg_path("qwen36"), "rb"))
    V = pickle.load(open(dst_path(args.tag), "rb"))
    common = set(A) & set(C) & set(V)
    A = {k: A[k] for k in common}; C = {k: C[k] for k in common}; V = {k: V[k] for k in common}

    chg = sum(1 for k in common if C[k]["verdict"] != V[k]["verdict"])
    dis = sum(1 for k in common if not V[k].get("agree", True))
    print(f"  공통 {len(common)}건 | 비평이 등급을 바꾼 비율 {100*chg/len(common):.1f}% "
          f"| 비평자가 '동의 안 함' 표시 {100*dis/len(common):.1f}%")
    print(f"  C(제안)  {dict(Counter(v['verdict'] for v in C.values()))}")
    print(f"  V(비평후) {dict(Counter(v['verdict'] for v in V.values()))}")

    tabs = {"A 단독(qwen3:30b)": A, "C 단독=제안자(qwen3.6)": C, f"V 비평후({args.tag})": V}
    print()
    print("=" * 92)
    print(f"  v7 제안→비평 — OOS 마켓뉴트럴 중앙값α  [n / 중앙α% / 승률%]")
    print("=" * 92)
    for label, key in (("강한호재", "강한호재"), ("score≥95", "95+")):
        print(f"  ── {label} ──")
        for name, J in tabs.items():
            a, _, sc = _alpha_tables(ev, J, px, "2023-12-01")
            src = a if key == "강한호재" else sc
            row = f"    {name:<24}"
            for h in HORIZONS:
                n, _, md, w = _s(src[h].get(key, []))
                row += f"{n:>4}/{md:>+6.2f}/{w:>3.0f}%"
            print(row)
        print()
    print("  사전 기준: 비평후가 제안자(C)를 전 지평에서 이기고 score≥95 절대값이 + 여야 통과")
    print("=" * 92)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["judge", "compare"])
    ap.add_argument("--tag", required=True, help="self(자기비평) / cross(교차비평)")
    a = ap.parse_args()
    (cmd_judge if a.cmd == "judge" else cmd_compare)(a)
