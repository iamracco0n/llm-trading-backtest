# -*- coding: utf-8 -*-
"""v8 — 프런티어 모델(Claude)을 **오염 없이** 재는 유일한 방법: 포워드.

**왜 백테스트로 못 재나.** 우리 OOS 구간은 2024-01~2025-06인데 Claude의 학습 컷오프는
2026-05다. **판정할 공시의 결과를 이미 알고 있다.** 좋은 성적이 나와도 그건 판단력이
아니라 기억이다. `llm_cutoff_probe.py`를 만든 이유가 정확히 이것이었고(로컬 qwen3:30b는
컷오프 2023-08이라 2024년 이후가 깨끗해서 진행할 수 있었다), 프런티어 모델에는 그
방어가 통째로 무너진다.

**그래서 컷오프 이후 공시만 쓴다.** 2026-06-01부터. 이 구간은 어떤 모델도 결과를
학습했을 수 없다.

**설계 — 사전 등록(prices를 보기 전에 고정)**
  · 이벤트: 컷오프 이후 실적공시 전량. 표본을 고르지 않는다(선택 효과 차단).
  · 판정: Claude가 공시 본문만 보고 4등급 + score. 로컬 모델과 **완전히 같은 프롬프트·스키마**.
  · 평가: 마켓뉴트럴 중앙값 알파(종목수익 − KOSPI수익), H+20/40/60/90. 로컬과 같은 식.
  · **통과 기준**: 강한호재 바구니가 **전 지평에서 + 이고, H+40이 로컬 최고(A: −1.41)보다
    높아야** 한다. 못 넘으면 "프런티어도 마찬가지"로 9번째 기각.
  · 판정은 `v8_judgments.json`에 봉인 저장한다. 가격이 쌓인 뒤 기준을 바꾸지 않는다.

**한계를 미리 적는다.** H+40이 채워지려면 8월 판정분 기준 10월은 돼야 한다. 표본도
한 분기치라 작다(2026-08-10 기준 51건). 이건 빠른 답이 아니라 **정직한 답**을 얻는 경로다.

**선행 연구 — 답이 이미 나와 있다.** 이 설계를 짠 뒤 찾아보니 학계가 2026년에 같은 질문에
답했다. 「Detecting Lookahead Bias in LLM Forecasts」(arXiv 2512.23847)는 LAP(Lookahead
Propensity)로 "LLM이 그 종목·날짜의 결과를 이미 아는 정도"를 추정했고, **LAP가 학습 구간
내내 뚜렷하게 양(+)이다가 컷오프 직후 사실상 0으로 붕괴**하며 **LLM 예측력은 LAP가 높은
쌍에서만 증폭되고 컷오프 이후 표본에서는 유의성을 잃는다**고 보고했다. 즉 **LLM의 예측력은
기억이 있는 곳에서만 나타난다.** 관련 연구도 여럿이다 — DatedGPT(arXiv 2603.11838)는 컷오프를
통제한 모델을 새로 학습하는 방식을, arXiv 2512.06607은 그 방식의 비용 문제를, arXiv
2309.17322은 종목명 익명화를 다룬다.

그래서 v8의 값어치는 줄었다. 그럼에도 남는 것: 위 논문들은 **전부 미국 헤드라인·어닝콜**이고
**한국 시장·한국어 공시로는 검증된 바 없다.** 표본이 작아 논문 재현으로는 약하지만,
우리 벤치마크(로컬 4모델, 697건)와 **같은 잣대**로 프런티어 모델을 놓는 유일한 방법이다.

사용:
  python3 v8_forward_claude.py events     # 컷오프 이후 이벤트 수집
  python3 v8_forward_claude.py batch      # 판정할 공시 본문 출력(Claude가 읽을 몫)
  python3 v8_forward_claude.py save       # 판정 결과 저장(JSON 입력)
  python3 v8_forward_claude.py alpha      # 가격이 쌓인 뒤 평가
"""
import os
import json
import time
import pickle
import argparse
import datetime as dt

import pandas as pd
import FinanceDataReader as fdr

from dart_data import get_corp_map, get_catalyst_events, fetch_document_text
from v5_oos import universe, EARN_KW, CACHE, _s, HORIZONS

CUTOFF = "20260601"          # Claude 학습 컷오프(2026-05) 이후
EV = os.path.join(CACHE, "v8_events.pkl")
JG = os.path.join(CACHE, "v8_judgments.json")
PX = os.path.join(CACHE, "v8_prices.pkl")


def cmd_events(_):
    end = dt.date.today().strftime("%Y%m%d")
    uni = universe()
    cmap = get_corp_map()
    events, n = {}, 0
    codes = list(uni)
    for i, code in enumerate(codes):
        cc = cmap.get(code)
        if not cc:
            continue
        try:
            disc = get_catalyst_events(cc, CUTOFF, end)
        except Exception:
            continue
        evs = [(d, rn, nm) for d, rn, nm in disc if any(k in nm for k in EARN_KW)]
        if evs:
            events[code] = evs
            n += len(evs)
        if (i + 1) % 50 == 0:
            print(f"[dart] {i+1}/{len(codes)}  누적 {n}건", flush=True)
        time.sleep(0.05)
    pickle.dump(events, open(EV, "wb"))
    uniq = {rn for evs in events.values() for _, rn, _ in evs}
    print(f"[events] {CUTOFF}~{end}: {len(events)}종목 / {n}건 (고유 공시 {len(uniq)}건)")


def cmd_batch(args):
    """판정할 공시를 본문과 함께 출력한다. Claude가 이걸 읽고 판정한다."""
    events = pickle.load(open(EV, "rb"))
    done = json.load(open(JG)) if os.path.exists(JG) else {}
    uniq = {}
    for code, evs in events.items():
        for d, rn, nm in evs:
            uniq.setdefault(rn, (code, d, nm))
    todo = [(rn, v) for rn, v in uniq.items() if rn not in done]
    print(f"### 남은 {len(todo)}건 중 {min(args.n, len(todo))}건 (완료 {len(done)})\n")
    for rn, (code, d, nm) in todo[:args.n]:
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            continue
        print(f"===== {rn} | {code} | {d} | {nm}")
        print(body.strip()[:1800])
        print()


def cmd_save(args):
    """판정 JSON을 봉인 저장. 기존 항목은 덮어쓰지 않는다(사후 수정 차단)."""
    new = json.load(open(args.file))
    done = json.load(open(JG)) if os.path.exists(JG) else {}
    added = 0
    for rn, v in new.items():
        if rn in done:
            continue
        v["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[rn] = v
        added += 1
    json.dump(done, open(JG, "w"), ensure_ascii=False, indent=1)
    print(f"[save] 신규 {added}건 저장, 누적 {len(done)}건 (기존 항목은 불변)")


def cmd_alpha(_):
    events = pickle.load(open(EV, "rb"))
    J = json.load(open(JG))
    px = pickle.load(open(PX, "rb")) if os.path.exists(PX) else {}
    codes = sorted({c for c, evs in events.items()
                    for _, rn, _ in evs if rn in J})
    if not px:
        print(f"[price] {len(codes)}종목 수집...")
        for c in codes:
            try:
                px[c] = fdr.DataReader(c, CUTOFF)
            except Exception:
                pass
        px["KS11"] = fdr.DataReader("KS11", CUTOFF)
        pickle.dump(px, open(PX, "wb"))

    ks = px["KS11"]["Close"]
    buckets = {h: {} for h in HORIZONS}
    for code, evs in events.items():
        if code not in px:
            continue
        cl = px[code]["Close"]
        for d, rn, nm in evs:
            if rn not in J:
                continue
            ts = pd.Timestamp(d)
            fut = cl.index[cl.index > ts]
            if len(fut) == 0:
                continue
            t0 = fut[0]
            for h in HORIZONS:
                later = cl.index[cl.index >= t0]
                if len(later) <= h:
                    continue
                t1 = later[h]
                a = (cl[t1] / cl[t0] - 1) * 100 - (ks[t1] / ks[t0] - 1) * 100
                v = J[rn]["verdict"]
                buckets[h].setdefault(v, []).append(a)
                if J[rn].get("score", 0) >= 95:
                    buckets[h].setdefault("95+", []).append(a)

    print("=" * 78)
    print(f"  v8 — Claude 포워드 판정 (컷오프 이후, 오염 없음)   [n / 중앙α% / 승률%]")
    print("=" * 78)
    for key in ("강한호재", "95+", "약한호재", "중립", "악재"):
        row = f"  {key:<8}"
        for h in HORIZONS:
            n, _, md, w = _s(buckets[h].get(key, []))
            row += f"  H{h}: {n:>3}/{md:>+6.2f}/{w:>3.0f}%"
        print(row)
    print("=" * 78)
    print("  사전 기준: 강한호재가 전 지평 + 이고 H+40이 로컬 최고(A −1.41)보다 높아야 통과")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["events", "batch", "save", "alpha"])
    ap.add_argument("-n", type=int, default=25, help="batch 건수")
    ap.add_argument("--file", help="save 할 판정 JSON 경로")
    a = ap.parse_args()
    {"events": cmd_events, "batch": cmd_batch,
     "save": cmd_save, "alpha": cmd_alpha}[a.cmd](a)
