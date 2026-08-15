# -*- coding: utf-8 -*-
"""v8 대조군 — **같은 65건**을 로컬 모델로도 판정한다.

**왜 필요한가(빠뜨렸던 것).** Claude 판정만으로는 v8을 해석할 수 없다. 기존 로컬
수치(A: H+40 −1.41)는 **다른 기간(2024-01~2025-06)·다른 표본(697건)**이라, 그것과
비교하면 "Opus가 나은가"가 아니라 **"2026년 2분기가 2024년과 다른가"**를 재게 된다.

같은 65건을 로컬 모델에도 판정시켜야 **변수가 모델 하나로 고정**된다. 프롬프트·스키마·
등급 기준·평가식은 전부 `llm_earnings.judge_earnings`를 그대로 재사용한다 — 697건
판정을 만든 바로 그 함수다.

**모델**: qwen3.6:35b(MoE, CPU ~22초/건) / gemma4:31b(Dense, CPU ~216초/건).
gemma4:12b는 제외한다 — 이 저장소에서 GPU로 판정한 모델이라 CPU 대조군으로 섞으면
실행 환경이 변수로 끼어든다(CPU↔GPU는 부동소수점 차이로 판정이 미세하게 갈린다).
둘 다 학습 컷오프가 이 구간(2026-06~08)보다 앞서므로 **Claude와 동일하게 오염이 없다.**

**사전 기준은 바꾸지 않는다.** Claude가 통과하려면 강한호재가 전 지평에서 +이고
H+40이 로컬 최고보다 높아야 한다 — 이제 그 '로컬 최고'가 **같은 표본에서** 나온다.

사용: LLM_MODEL=qwen3.6:35b python3 v8_local.py judge --tag qwen36
      LLM_MODEL=gemma4:12b  python3 v8_local.py judge --tag gemma12
      python3 v8_local.py compare
"""
import os
import sys
import json
import time
import pickle
import argparse
import datetime as dt

import pandas as pd

from dart_data import fetch_document_text
from llm_earnings import judge_earnings
from v5_oos import CACHE, _s, HORIZONS
from v8_forward_claude import EV, JG, PX, CUTOFF


def dst(tag):
    return os.path.join(CACHE, f"v8_judgments_{tag}.json")


def cmd_judge(args):
    events = pickle.load(open(EV, "rb"))
    uniq = {}
    for code, evs in events.items():
        for d, rn, nm in evs:
            uniq.setdefault(rn, nm)
    done = json.load(open(dst(args.tag), encoding="utf-8")) if os.path.exists(dst(args.tag)) else {}
    todo = [(rn, nm) for rn, nm in uniq.items() if rn not in done]
    model = os.environ.get("LLM_MODEL", "?")
    gpu = os.environ.get("LLM_NUM_GPU", "0")
    print(f"[v8local] {len(todo)}건 판정 (캐시 {len(done)}) | model={model} "
          f"| {'GPU' if gpu != '0' else 'CPU'}", flush=True)
    t0, fail = time.time(), 0
    for i, (rn, nm) in enumerate(todo):
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            done[rn] = {"verdict": "중립", "score": 50, "reason": "본문없음",
                        "ts": dt.datetime.now().isoformat(timespec="seconds")}
            continue
        res = None
        for a in range(3):
            try:
                res = judge_earnings(nm, body)
            except Exception:
                res = None
            if res:
                break
            time.sleep(5 * (a + 1))
        if not res:                     # 실패를 '중립'으로 저장하면 데이터가 오염된다
            fail += 1
            print(f"  실패 {rn} — 미저장 ({fail})", flush=True)
            continue
        res["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[rn] = res
        if (i + 1) % 5 == 0:
            el = time.time() - t0
            print(f"  {i+1}/{len(todo)} {nm[:14]} → {res['verdict']}({res.get('score',0)})"
                  f"  ETA {el/(i+1)*(len(todo)-i-1)/60:.0f}분", flush=True)
            json.dump(done, open(dst(args.tag), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    json.dump(done, open(dst(args.tag), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[v8local] 완료 {len(done)}건, {(time.time()-t0)/60:.0f}분 (실패 {fail})")


def alpha_table(events, J, px):
    ks = px["KS11"]["Close"]
    buckets = {h: {} for h in HORIZONS}
    for code, evs in events.items():
        if code not in px:
            continue
        cl = px[code]["Close"]
        for d, rn, nm in evs:
            if rn not in J:
                continue
            fut = cl.index[cl.index > pd.Timestamp(d)]
            if len(fut) == 0:
                continue
            t0 = fut[0]
            later = cl.index[cl.index >= t0]
            for h in HORIZONS:
                if len(later) <= h:
                    continue
                t1 = later[h]
                a = (cl[t1] / cl[t0] - 1) * 100 - (ks[t1] / ks[t0] - 1) * 100
                buckets[h].setdefault(J[rn]["verdict"], []).append(a)
                if J[rn].get("score", 0) >= 95:
                    buckets[h].setdefault("95+", []).append(a)
    return buckets


def cmd_compare(args):
    import collections
    events = pickle.load(open(EV, "rb"))
    sets = {"Claude(Opus 5)": JG}
    for tag, label in (("qwen36", "qwen3.6:35b"), ("gemma31", "gemma4:31b"),
                       ("gemma12", "gemma4:12b")):
        if os.path.exists(dst(tag)):
            sets[label] = dst(tag)

    loaded = {k: json.load(open(v, encoding="utf-8")) for k, v in sets.items()}
    common = set.intersection(*[set(v) for v in loaded.values()])
    print(f"\n  공통 판정 {len(common)}건 (모델 {len(loaded)}개)\n")
    print(f"  {'모델':<16}" + "".join(f"{k:>10}" for k in
                                     ("강한호재", "약한호재", "중립", "악재", "95+")))
    print("  " + "-" * 66)
    for name, J in loaded.items():
        c = collections.Counter(J[k]["verdict"] for k in common)
        n95 = sum(1 for k in common if J[k].get("score", 0) >= 95)
        print(f"  {name:<16}" + "".join(f"{c.get(x,0):>10}" for x in
                                        ("강한호재", "약한호재", "중립", "악재")) + f"{n95:>10}")

    # 모델 간 일치율
    names = list(loaded)
    print()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ag = sum(1 for k in common
                     if loaded[names[i]][k]["verdict"] == loaded[names[j]][k]["verdict"])
            print(f"  판정 일치율  {names[i]} vs {names[j]}: {100*ag/len(common):.1f}%")

    if not os.path.exists(PX):
        print("\n  ⚠️ 가격 캐시 없음 — H+20은 9월 중순, H+40은 10월 중순부터 평가 가능")
        print("     그때 `python3 v8_local.py compare` 를 다시 실행한다.")
        return
    px = pickle.load(open(PX, "rb"))
    print("\n" + "=" * 78)
    print("  v8 — 같은 65건, 모델만 교체  [n / 중앙α% / 승률%]")
    print("=" * 78)
    for key in ("강한호재", "95+"):
        print(f"  ── {key} ──")
        for name, J in loaded.items():
            b = alpha_table(events, {k: J[k] for k in common}, px)
            row = f"    {name:<16}"
            for h in HORIZONS:
                n, _, md, w = _s(b[h].get(key, []))
                row += f"{n:>4}/{md:>+6.2f}/{w:>3.0f}%"
            print(row)
        print()
    print("  사전 기준: Claude가 전 지평 + 이고 H+40이 로컬 최고보다 높아야 통과")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["judge", "compare"])
    ap.add_argument("--tag", help="judge: 저장 태그")
    a = ap.parse_args()
    (cmd_judge if a.cmd == "judge" else cmd_compare)(a)
