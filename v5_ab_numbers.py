# -*- coding: utf-8 -*-
"""v5 A/B — LLM에게 '텍스트만' 주는 것과 '텍스트+계산된 지표'를 주는 것의 차이.

**왜 이게 빈 칸인가.** 지금까지 나온 두 실패는 정반대 구성이었다:

    Alpha Arena(실제 돈 $10k×6모델) : LLM에게 **수치만** 줌  → 6개 중 4개 손실, GPT-5 −62.66%
      주최측: "LLM은 수치 시계열을 잘 못 다루는데 우리가 준 게 그것뿐이었다"
    우리 Phase 3 / v5                : LLM에게 **텍스트만** 줌 → +73%→+4.25%, IS +3.66%→OOS −2.60%
      `judge_earnings(공시제목, 본문)` — 가격·거래량·추세 맥락을 하나도 안 줬다

**둘을 합친 구성은 아무도 제대로 안 해봤다.** LLM이 못하는 건 수치 계산과 예측이고,
잘하는 건 맥락 결합이다. Phase 3에서 LLM은 무상증자를 '실질 호재 아님'으로 정확히
걸렀는데 그게 오히려 손해였다 — 그 종목이 이미 거래량 폭증 중이라는 걸 **몰랐기 때문**이다.

**설계: 변수 하나만 바꾸는 깨끗한 A/B.**
  이벤트·기간·모델·스키마·평가식 전부 고정. 입력만 다르다.
    A(기존) = 공시 본문
    B(신규) = 공시 본문 + **코드가 계산한 지표**(수익률·거래량비·MA 대비 위치·변동성·신고가 거리)
  차이가 곧 "LLM이 수치를 받아서 실제로 더한 값"이다.

사용: python3 v5_ab_numbers.py judge     (B 판정, 재개 가능)
      python3 v5_ab_numbers.py compare   (A vs B 알파 비교)
"""
import os
import sys
import json
import time
import pickle
import argparse
import urllib.request
from collections import Counter

import numpy as np
import pandas as pd

from dart_data import fetch_document_text
from v5_oos import (_alpha_tables, _s, HORIZONS, EV_IS, JG_IS,
                    EV_OOS, JG_OOS, PX_OOS, CACHE)

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3:30b")
JG_B = os.path.join(CACHE, "v5_ab_numbers_judgments.pkl")
JG_B_OOS = os.path.join(CACHE, "v5_ab_numbers_judgments_oos.pkl")


def dataset(oos):
    """IS(2025-07~2026-08, 445건) / OOS(2024-01~2025-06, 697건).

    ⚠️ IS에서 B가 A를 이긴 것만으로는 결론이 안 난다 — A도 IS에선 +3.66이었다가
    OOS에서 −2.60으로 뒤집혔다. 같은 함정에 두 번 빠지지 않으려면 OOS가 필수다."""
    if oos:
        import pickle as pk
        return (pk.load(open(EV_OOS, "rb")), pk.load(open(PX_OOS, "rb")),
                JG_B_OOS, JG_OOS, "2023-12-01")
    from surge_backtest import load_data
    import pickle as pk
    return (pk.load(open(EV_IS, "rb")), load_data(), JG_B, JG_IS, "2025-05-01")

# A와 동일한 판정 기준. 마지막 문단만 추가됐다(수치를 함께 보라는 지시).
SYSTEM = (
    "너는 한국 주식 실적 공시 분석가다. 주어진 실적 공시 본문을 읽고 '어닝 서프라이즈 강도'를 "
    "냉정하게 등급화한다. 과장·낙관 금지. 판정 기준:\n"
    "- 강한호재: 흑자전환, 또는 영업이익/순이익이 전년동기比 대폭(+30% 이상) 증가, 또는 명백한 대규모 개선.\n"
    "- 약한호재: 영업이익 소폭(+대략 5~30%) 증가, 매출만 늘고 이익은 미미, 개선이지만 강도 약함.\n"
    "- 중립: 실적공시 '예고'(확정치 아님), 변동 미미, 판단 근거 부족.\n"
    "- 악재: 적자전환, 영업이익 감소, 어닝 쇼크.\n"
    "숫자(영업이익/매출의 전년동기比 증감률)가 본문에 있으면 그걸 근거로. score=서프라이즈 강도 0~100.\n\n"
    "★추가로 [시장맥락] 블록이 주어진다. 이는 공시 시점의 가격·거래량 지표다. "
    "실적 내용이 이미 가격에 반영됐는지, 아니면 시장이 아직 모르는지를 함께 고려하라. "
    "예: 좋은 실적인데 이미 급등·거래량 폭증 상태면 서프라이즈 강도를 낮춰라. "
    "나쁜 실적인데 이미 급락한 상태면 악재 강도를 낮춰라. 수치를 직접 계산하려 하지 말고 주어진 값만 해석하라."
)
SCHEMA = {"type": "object",
          "properties": {"verdict": {"type": "string",
                                     "enum": ["강한호재", "약한호재", "중립", "악재"]},
                         "score": {"type": "integer"}, "reason": {"type": "string"}},
          "required": ["verdict", "score", "reason"]}


def context_block(df, date):
    """공시 시점의 지표 — 전부 코드가 계산한다(LLM은 계산하지 않는다)."""
    d = pd.to_datetime(date, format="%Y%m%d")
    hist = df[df.index <= d]
    if len(hist) < 60:
        return None
    c = hist["Close"]
    v = hist["Volume"]
    r = lambda n: (c.iloc[-1] / c.iloc[-1 - n] - 1) * 100 if len(c) > n else float("nan")
    ma = lambda n: (c.iloc[-1] / c.tail(n).mean() - 1) * 100
    vol20 = c.pct_change().tail(20).std() * 100
    vr = v.iloc[-1] / v.tail(20).mean() if v.tail(20).mean() > 0 else float("nan")
    hh60 = hist["High"].tail(60).max()
    return (f"[시장맥락] 공시일 {d.date()}\n"
            f"- 최근수익률: 5일 {r(5):+.1f}% / 20일 {r(20):+.1f}% / 60일 {r(60):+.1f}%\n"
            f"- 이동평균 대비: MA20 {ma(20):+.1f}% / MA60 {ma(60):+.1f}%\n"
            f"- 당일 거래량 / 20일평균 = {vr:.1f}배\n"
            f"- 20일 일간변동성 {vol20:.1f}%\n"
            f"- 60일 최고가 대비 {(c.iloc[-1]/hh60-1)*100:+.1f}%")


def ask(report_nm, body, ctx, timeout=600):
    payload = json.dumps({
        "model": MODEL, "stream": False, "think": False,
        "options": {"temperature": 0.2, "num_predict": 400},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                      f"[공시제목] {report_nm}\n{ctx}\n\n[본문]\n{body}"}],
        "format": SCHEMA,
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    try:
        j = json.loads(out["message"]["content"])
        return {"verdict": j["verdict"], "score": int(j.get("score", 0)),
                "reason": str(j.get("reason", ""))[:120]}
    except Exception:
        return None


def cmd_judge(args):
    events, data, dst, _, _ = dataset(args.oos)
    cache = pickle.load(open(dst, "rb")) if os.path.exists(dst) else {}

    todo = []
    for code, evs in events.items():
        if code not in data:
            continue
        for d, rn, nm in evs:
            if rn not in cache:
                todo.append((code, d, rn, nm))
    print(f"[ab] {'OOS' if args.oos else 'IS'} B(텍스트+지표) 판정 대상 {len(todo)}건 (캐시 {len(cache)}건)")
    t0, consec = time.time(), 0
    for i, (code, d, rn, nm) in enumerate(todo):
        ctx = context_block(data[code]["df"], d)
        if ctx is None:
            cache[rn] = {"verdict": "중립", "score": 0, "reason": "지표부족", "nm": nm}
            continue
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            cache[rn] = {"verdict": "중립", "score": 0, "reason": "본문없음", "nm": nm}
            continue
        res = None
        for a in range(3):
            res = ask(nm, body, ctx)
            if res:
                break
            time.sleep(5 * (a + 1))
        if not res:                      # 실패를 '중립'으로 캐시하면 데이터가 오염된다
            consec += 1
            print(f"[ab] 판정 실패({consec}연속) {rn} — 미캐시", flush=True)
            if consec >= 5:
                pickle.dump(cache, open(dst, "wb"))
                sys.exit(f"[ab] 연속 5회 실패 — 연결 확인 후 재실행. 진행분 {len(cache)}건")
            continue
        consec = 0
        res["nm"] = nm
        cache[rn] = res
        if (i + 1) % 10 == 0:
            el = time.time() - t0
            print(f"[ab] {i+1}/{len(todo)}  {nm[:14]} → {res['verdict']}({res['score']})  "
                  f"ETA {el/(i+1)*(len(todo)-i-1)/60:.0f}분", flush=True)
            pickle.dump(cache, open(dst, "wb"))
    pickle.dump(cache, open(dst, "wb"))
    print(f"[ab] 완료 {len(cache)}건, {(time.time()-t0)/60:.0f}분")


def cmd_compare(args):
    ev, data, dst, src_a, idx_from = dataset(args.oos)
    A = pickle.load(open(src_a, "rb"))
    B = pickle.load(open(dst, "rb"))
    common = set(A) & set(B)
    print(f"  공통 판정 {len(common)}건으로 비교 (A=텍스트만, B=텍스트+지표)")
    A = {k: v for k, v in A.items() if k in common}
    B = {k: v for k, v in B.items() if k in common}
    print(f"  A 분포 {dict(Counter(v['verdict'] for v in A.values()))}")
    print(f"  B 분포 {dict(Counter(v['verdict'] for v in B.values()))}")
    agree = sum(1 for k in common if A[k]["verdict"] == B[k]["verdict"])
    print(f"  판정 일치율 {100*agree/len(common):.1f}%  (낮을수록 지표가 판단을 바꿨다는 뜻)")

    aa, alla, sca = _alpha_tables(ev, A, data, idx_from)
    ab, allb, scb = _alpha_tables(ev, B, data, idx_from)
    print()
    print("=" * 92)
    print("  A(텍스트만) vs B(텍스트+계산지표) — 마켓뉴트럴 중앙값α [n / 중앙α% / 승률%]")
    print("=" * 92)
    for label, ga, gb in (("강한호재", aa, ab), ("score≥95", sca, scb)):
        print(f"  ── {label} ──")
        for h in HORIZONS:
            la = ga[h].get("강한호재", []) if label == "강한호재" else ga[h].get("95+", [])
            lb = gb[h].get("강한호재", []) if label == "강한호재" else gb[h].get("95+", [])
            na, _, mda, wa = _s(la)
            nb, _, mdb, wb = _s(lb)
            if na == 0 and nb == 0:
                continue
            d = mdb - mda
            print(f"    H+{h:<3} A n{na:>3} 중앙{mda:>+6.2f} 승{wa:>3.0f}%   |   "
                  f"B n{nb:>3} 중앙{mdb:>+6.2f} 승{wb:>3.0f}%   차이 {d:>+6.2f}"
                  f"{'  ← B 우위' if d > 0 else ''}")
        print()
    print("  ── 참고: 전체매수(규칙) ──")
    for h in HORIZONS:
        n, _, md, w = _s(alla[h])
        print(f"    H+{h:<3} n{n:>3} 중앙{md:>+6.2f} 승{w:>3.0f}%")
    print("=" * 92)
    print("  판정: B가 A를 전 지평에서 이기면 '수치를 함께 주면 LLM이 나아진다'가 성립")
    print("=" * 92)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["judge", "compare"])
    ap.add_argument("--oos", action="store_true", help="OOS 구간(2024-01~2025-06)에서 실행")
    a = ap.parse_args()
    (cmd_judge if a.cmd == "judge" else cmd_compare)(a)
