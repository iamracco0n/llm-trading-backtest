# -*- coding: utf-8 -*-
"""v5-KOSPI — PEAD를 코스닥 소형주가 아닌 **코스피 대형주**에 걸어본다.

**왜 판을 바꾸나 (파라미터 재조정이 아니다).**
코스닥 OOS 검증에서 드러난 진짜 문제는 LLM이 아니라 **판의 base 알파가 마이너스**라는 것이었다:

    실적공시 전체매수의 마켓뉴트럴 알파 —  IS(H+20/40/60/90) −3.06 / −0.57 / −1.81 / −3.03
                                          OOS                −1.47 / −2.34 / −0.34 / −1.36
    → 8/8 전부 마이너스. 코스닥에서 '실적공시 난 종목을 사는 것' 자체가 지수보다 못하다.

그 위에서 LLM은 8/8 전부 개선시켰다(예: OOS H+60 −0.34 → +1.00). **LLM은 밥값을 했다.**
문제는 출발점이 −2%인 판에서 +1.5%p를 보태봐야 −0.5%라는 것. 그래서 모델을 키우거나
프롬프트를 다듬는 방향은 답이 아니다. **base가 마이너스가 아닌 판을 찾아야 한다.**

코스피 대형주는 (a) 이 레포에서 유일하게 살아남은 엣지(장투)가 사는 곳이고,
(b) 코스닥 소형주처럼 실적공시가 악재 편중이지 않을 수 있다(코스닥 OOS는 악재만 330건).

**⚠️ 3차 홀드아웃 봉인 — 이 스크립트의 핵심 장치.**
우리는 이미 코스닥 OOS를 봤다. 결과를 보고 조건을 바꾸면 그 검증은 더 이상 검증이 아니다.
그래서 **2022-01-01~2023-12-31은 봉인**하고 실험은 2024년 이후로만 한다. 봉인 구간은
`--unseal`을 명시적으로 줄 때만 열리며, **딱 한 번 최종 확인용으로만 써야 한다.**
(코드가 막아주지 않으면 사람은 반드시 훔쳐본다. 그래서 기본값으로 막아둔다.)

사용:
  python3 v5_kospi.py events    실적공시 이벤트 수집(실험구간)
  python3 v5_kospi.py judge     LLM 판정(재개 가능)
  python3 v5_kospi.py alpha     마켓뉴트럴 알파(vs KOSPI 지수) + 코스닥 결과와 대조
  python3 v5_kospi.py alpha --unseal   ⚠️봉인 해제(최종 확인 1회용)
"""
import os
import sys
import time
import pickle
import argparse
from collections import Counter

import pandas as pd
import FinanceDataReader as fdr

from dart_data import get_corp_map, get_catalyst_events, fetch_document_text
from llm_earnings import judge_earnings
from v5_oos import _alpha_tables, _s, EARN_KW, HORIZONS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# 실험 구간 / 봉인 구간
EXP_BGN, EXP_END = "20240101", "20260803"
SEAL_BGN, SEAL_END = "20220101", "20231231"

EV = os.path.join(CACHE, "v5_kospi_events.pkl")
JG = os.path.join(CACHE, "v5_kospi_judgments.pkl")
TREND = os.path.join(CACHE, "trend_kospi_long.pkl")
DELISTED = os.path.join(CACHE, "delisted_prices.pkl")


def price_data():
    """코스피 대형주 150(현재상장) + 상폐 KOSPI 49 — 이미 받아둔 캐시 재사용."""
    data = {}
    base = pickle.load(open(TREND, "rb"))
    for c, r in base.items():
        data[c] = {"name": r["name"], "df": r["df"]}
    n_live = len(data)
    if os.path.exists(DELISTED):
        for c, r in pickle.load(open(DELISTED, "rb")).items():
            if r["market"] == "KOSPI" and c not in data:
                data[c] = {"name": r["name"], "df": r["df"]}
    print(f"[universe] 현재상장 {n_live} + 상폐 {len(data)-n_live} = {len(data)}종목")
    return data


def cmd_events(args):
    data = price_data()
    cmap = get_corp_map()
    bgn, end = (SEAL_BGN, SEAL_END) if args.unseal else (EXP_BGN, EXP_END)
    if args.unseal:
        print("⚠️ 봉인 해제 모드 — 최종 확인 1회용")
    print(f"[dart] 구간 {bgn}~{end}")

    events, n_ev, miss = {}, 0, 0
    codes = list(data)
    for i, code in enumerate(codes):
        cc = cmap.get(code)
        if not cc:
            miss += 1
            continue
        try:
            disc = get_catalyst_events(cc, bgn, end)
        except Exception:
            continue
        evs = [(d, rn, nm) for d, rn, nm in disc if any(k in nm for k in EARN_KW)]
        if evs:
            events[code] = evs
            n_ev += len(evs)
        if (i + 1) % 40 == 0:
            print(f"[dart] {i+1}/{len(codes)}  누적 {n_ev}")
        time.sleep(0.05)
    out = EV if not args.unseal else EV.replace(".pkl", "_sealed.pkl")
    pickle.dump(events, open(out, "wb"))
    print(f"[events] {len(events)}종목 / {n_ev}건 → {os.path.basename(out)} "
          f"(corp_code 실패 {miss})")


def cmd_judge(args):
    """전수 3,245건은 20시간이라 과하다. 무작위 표본은 추정값을 편향시키지 않고
    신뢰구간만 넓히므로, 씨드 고정 표본으로 판정한다(--sample)."""
    src = EV if not args.unseal else EV.replace(".pkl", "_sealed.pkl")
    dst = JG if not args.unseal else JG.replace(".pkl", "_sealed.pkl")
    events = pickle.load(open(src, "rb"))
    cache = pickle.load(open(dst, "rb")) if os.path.exists(dst) else {}

    # 실적 수치가 실제로 담긴 공시만: '예고'=발표일 안내라 숫자 없음, '자회사'=모회사 이벤트 아님
    uniq = {rn: nm for evs in events.values() for _, rn, nm in evs
            if "예고" not in nm and "자회사" not in nm}
    if args.sample and len(uniq) > args.sample:
        import random
        random.seed(20260804)
        keys = sorted(uniq)                      # 재현 가능하게 정렬 후 표본추출
        uniq = {k: uniq[k] for k in random.sample(keys, args.sample)}
        print(f"[llm] 무작위 표본 {args.sample}건 (씨드 고정)")
    todo = [(rn, nm) for rn, nm in uniq.items() if rn not in cache]
    print(f"[llm] 대상 {len(uniq)}건 (캐시 {len(uniq)-len(todo)}, 신규 {len(todo)})")
    t0, consec = time.time(), 0
    for i, (rn, nm) in enumerate(todo):
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            cache[rn] = {"verdict": "중립", "score": 0, "reason": "본문없음", "nm": nm}
            continue
        res = None
        for a in range(3):                     # LLM 실패를 '중립'으로 캐시하면 안 된다
            res = judge_earnings(nm, body)
            if res:
                break
            time.sleep(5 * (a + 1))
        if not res:
            consec += 1
            print(f"[llm] 판정 실패({consec}연속) {rn} — 미캐시", flush=True)
            if consec >= 5:
                pickle.dump(cache, open(dst, "wb"))
                sys.exit(f"[llm] 연속 5회 실패 — 연결 확인 후 재실행. 진행분 {len(cache)}건 저장")
            continue
        consec = 0
        cache[rn] = res
        cache[rn]["nm"] = nm
        if (i + 1) % 10 == 0:
            el = time.time() - t0
            print(f"[llm] {i+1}/{len(todo)}  {nm[:14]} → {res['verdict']}({res['score']})  "
                  f"ETA {el/(i+1)*(len(todo)-i-1)/60:.0f}분", flush=True)
            pickle.dump(cache, open(dst, "wb"))
    pickle.dump(cache, open(dst, "wb"))
    print(f"[llm] 완료 {len(cache)}건, {(time.time()-t0)/60:.0f}분")


def cmd_alpha(args):
    src_e = EV if not args.unseal else EV.replace(".pkl", "_sealed.pkl")
    src_j = JG if not args.unseal else JG.replace(".pkl", "_sealed.pkl")
    if args.unseal:
        print("⚠️ 봉인 구간(2022~2023) 결과 — 최종 확인 1회용\n")
    ev = pickle.load(open(src_e, "rb"))
    jg = pickle.load(open(src_j, "rb"))
    data = price_data()

    # 코스피 대형주는 벤치마크가 KOSPI(KS11)
    a, alla, sc = _alpha_tables(ev, jg, data, "2021-12-01", index="KS11")

    print("=" * 80)
    print(f"  v5-KOSPI 대형주 PEAD — 마켓뉴트럴 알파(종목 − KOSPI)  구간 {EXP_BGN}~{EXP_END}")
    print("=" * 80)
    print(f"  {'등급':<10}{'지평':<8}{'n':>6}{'평균α':>10}{'중앙값α':>10}{'승률':>8}")
    print("-" * 80)
    for v in ["강한호재", "약한호재", "중립", "악재"]:
        for h in HORIZONS:
            n, m, md, w = _s(a[h].get(v, []))
            print(f"  {v if h == HORIZONS[0] else '':<10}H+{h:<6}{n:>6}{m:>+10.2f}{md:>+10.2f}{w:>7.0f}%")
        print("-" * 80)

    print("  ── ★base 알파: 실적공시 전체매수 (코스닥은 8/8 전부 마이너스였다) ──")
    for h in HORIZONS:
        n, m, md, w = _s(alla[h])
        mark = "  ← base +" if md > 0 else ""
        print(f"  H+{h:<3} n{n:>4}  평균{m:>+7.2f}  중앙값{md:>+7.2f}  승률{w:>4.0f}%{mark}")
    print("-" * 80)
    print("  ── 규칙(전체) vs LLM(강한호재) ──")
    for h in HORIZONS:
        _, _, mda, _ = _s(alla[h])
        _, _, mdb, _ = _s(a[h].get("강한호재", []))
        print(f"  H+{h:<3} 전체 {mda:>+6.2f}  →  강한호재 {mdb:>+6.2f}   "
              f"({'개선' if mdb > mda else '악화'} {mdb-mda:+.2f}%p)")
    print("-" * 80)
    print("  ── score≥95 (코스닥 IS에서 최적이었던 설정) ──")
    for h in HORIZONS:
        n9, m9, md9, w9 = _s(sc[h].get("95+", []))
        print(f"  H+{h:<3} n{n9:>4}  중앙값α {md9:>+6.2f}  승률 {w9:>3.0f}%")
    print("=" * 80)
    print(f"  판정 분포: {dict(Counter(j['verdict'] for j in jg.values()))}")
    if not args.unseal:
        print(f"  ⚠️ 2022~2023은 봉인 상태 — 최종 확인 때 딱 한 번만 --unseal")
    print("=" * 80)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["events", "judge", "alpha"])
    ap.add_argument("--unseal", action="store_true",
                    help="⚠️봉인된 2022~2023 구간 사용(최종 확인 1회용)")
    ap.add_argument("--sample", type=int, default=0,
                    help="판정 표본 수(0=전수). 무작위·씨드고정")
    a = ap.parse_args()
    {"events": cmd_events, "judge": cmd_judge, "alpha": cmd_alpha}[a.cmd](a)
