# -*- coding: utf-8 -*-
"""v5 OOS 검증 — PEAD 알파(score≥95 / H+40 중앙값α +3.66%, 승률 56%)가 다른 기간에서도 재현되나.

**왜 이게 진짜 관문인가.**
IS 구간(2025-07-03 ~ 2026-08-03, 445건)에서 LLM 실적판정이 처음으로 마켓뉴트럴 알파를 냈다.
중앙값이 +이고 승률이 50%를 넘어 '몇 개 대박에 기댄 복권'이 아니었다는 점에서 이 프로젝트
통틀어 처음 있는 결과다. 그러나 단일 상승장 구간 하나뿐이라 **"검증"이 아니라 "유망"** 이다.
이 레포는 오늘까지 세 번(급등 +45%, 공시필터 +73%, 장투 2024 +9.8%) "좋아 보이는 숫자"가
편향이나 운이었음을 밝혀냈다. v5도 같은 잣대를 통과해야 한다.

**OOS 설계 — IS와 겹치지 않는 과거 구간에서 파이프라인 전체를 다시 돌린다.**
  - 기간: 2024-01-01 ~ 2025-06-30 (IS 시작 2025-07-03 직전까지, 무겹침)
  - 유니버스: 캐시된 KOSDAQ 187 + **상장폐지 KOSDAQ**(`delisted_prices.pkl`) → 생존편향 완화
  - 규칙·프롬프트·모델을 IS와 **동일하게** 유지(바꾸면 재현 검증이 아니라 새 실험이 된다)
  - 판정: aurora qwen3:30b CPU (`OLLAMA_HOST` 기본 localhost:11435 = SSH 포워딩)
  - 평가: `v5_alpha.py`와 **같은 계산식**(마켓뉴트럴 α = 종목수익 − KQ11 수익, 중앙값 중심)

**무엇을 보면 통과인가.** score≥95 & H+40에서 중앙값 알파가 여전히 + 이고 승률이 50%를 넘는가.
등급 그라디언트(강한호재 > 중립 > 악재)가 유지되는가. 부호만 같고 크기가 반토막이어도
'재현'으로 볼지 미리 정해둔다 — 사후에 기준을 바꾸면 그게 곧 과최적화다.

사용:
  python3 v5_oos.py events    OOS 실적공시 이벤트 수집(DART)
  python3 v5_oos.py prices    OOS 가격데이터 수집(FDR, 상폐 포함)
  python3 v5_oos.py judge     LLM 판정(재개 가능, 10건마다 저장)
  python3 v5_oos.py alpha     마켓뉴트럴 알파 리포트 (IS와 나란히 비교)
"""
import os
import sys
import time
import pickle
import argparse
import statistics as st
from collections import defaultdict, Counter

import pandas as pd
import FinanceDataReader as fdr

from dart_data import get_corp_map, get_catalyst_events, fetch_document_text
from llm_earnings import judge_earnings

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

OOS_BGN, OOS_END = "20240101", "20250630"     # IS(20250703~)와 무겹침
PRICE_BGN, PRICE_END = "2023-12-01", "2025-12-31"   # 이벤트 전후 여유(H+90 커버)

EV_OOS = os.path.join(CACHE, "v5_oos_events.pkl")
PX_OOS = os.path.join(CACHE, "v5_oos_prices.pkl")
JG_OOS = os.path.join(CACHE, "v5_oos_judgments.pkl")

EV_IS = os.path.join(CACHE, "v5_earnings_events.pkl")
JG_IS = os.path.join(CACHE, "v5_earnings_judgments.pkl")
DELISTED = os.path.join(CACHE, "delisted_prices.pkl")

# IS 이벤트 캐시에 실제로 담긴 공시명에서 역산한 필터(동일 조건 유지)
EARN_KW = ["매출액또는손익", "영업(잠정)실적", "결산실적공시예고"]
HORIZONS = [20, 40, 60, 90]


def universe():
    """캐시된 KOSDAQ 187 + 상폐 KOSDAQ(생존편향 완화)."""
    from surge_backtest import load_data
    base = load_data()
    uni = {c: d["name"] for c, d in base.items()}
    n_live = len(uni)
    if os.path.exists(DELISTED):
        for c, r in pickle.load(open(DELISTED, "rb")).items():
            if r["market"] == "KOSDAQ" and c not in uni:
                uni[c] = r["name"]
    print(f"[universe] 현재상장 {n_live} + 상폐 {len(uni)-n_live} = {len(uni)}종목")
    return uni


# ─────────────────────────── 1) 이벤트 ───────────────────────────

def cmd_events(_):
    uni = universe()
    cmap = get_corp_map()
    events, n_ev, miss = {}, 0, 0
    codes = list(uni)
    for i, code in enumerate(codes):
        cc = cmap.get(code)
        if not cc:
            miss += 1
            continue
        try:
            # get_disclosures는 rcept_no를 안 준다(본문 판정 불가) → catalyst_events 사용
            disc = get_catalyst_events(cc, OOS_BGN, OOS_END)
        except Exception:
            continue
        evs = [(d, rn, nm) for d, rn, nm in disc if any(k in nm for k in EARN_KW)]
        if evs:
            events[code] = evs
            n_ev += len(evs)
        if (i + 1) % 40 == 0:
            print(f"[dart] {i+1}/{len(codes)}  누적 이벤트 {n_ev}")
        time.sleep(0.05)
    pickle.dump(events, open(EV_OOS, "wb"))
    print(f"[events] {OOS_BGN}~{OOS_END}: {len(events)}종목 / {n_ev}건 저장 "
          f"(corp_code 매칭실패 {miss})")


# ─────────────────────────── 2) 가격 ───────────────────────────

def cmd_prices(_):
    events = pickle.load(open(EV_OOS, "rb"))
    uni = universe()
    codes = [c for c in events]
    print(f"[price] 이벤트 있는 {len(codes)}종목 일봉 수집...")
    out, fail = {}, 0
    for i, code in enumerate(codes):
        try:
            df = fdr.DataReader(code, PRICE_BGN, PRICE_END)
        except Exception:
            fail += 1; continue
        if df is None or len(df) < 60:
            fail += 1; continue
        df.index = pd.to_datetime(df.index)
        out[code] = {"name": uni.get(code, code), "df": df[["Open", "High", "Low", "Close", "Volume"]]}
        if (i + 1) % 40 == 0:
            print(f"[price]   {i+1}/{len(codes)} (수집 {len(out)}, 실패 {fail})")
        time.sleep(0.03)
    pickle.dump(out, open(PX_OOS, "wb"))
    print(f"[price] 저장 {len(out)}종목 (실패 {fail})")


# ─────────────────────────── 3) LLM 판정 ───────────────────────────

def cmd_judge(args):
    events = pickle.load(open(EV_OOS, "rb"))
    cache = pickle.load(open(JG_OOS, "rb")) if os.path.exists(JG_OOS) else {}
    uniq = {rn: nm for evs in events.values() for _, rn, nm in evs}
    todo = [(rn, nm) for rn, nm in uniq.items() if rn not in cache]
    print(f"[llm] 대상 {len(uniq)}건 (캐시 {len(uniq)-len(todo)}, 신규 {len(todo)})  "
          f"host={os.environ.get('OLLAMA_HOST', 'http://localhost:11435')}")
    t0 = time.time()
    consec_fail = 0
    for i, (rn, nm) in enumerate(todo):
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            # 본문이 없는 건 사실이므로 그대로 기록(판정 불가)
            cache[rn] = {"verdict": "중립", "score": 0, "reason": "본문없음", "nm": nm}
            continue

        # ⚠️ LLM 실패를 '중립'으로 캐시하면 안 된다 — 터널이 끊기면 수백 건이 조용히
        # 중립으로 오염돼 비교표 자체가 무의미해진다. 재시도하고, 계속 실패하면 중단해서
        # 나중에 이어 돌린다(캐시에 안 남기므로 resume 시 다시 시도됨).
        res = None
        for attempt in range(3):
            res = judge_earnings(nm, body)
            if res:
                break
            time.sleep(5 * (attempt + 1))
        if not res:
            consec_fail += 1
            print(f"[llm] 판정 실패({consec_fail}회 연속) rcept={rn} — 캐시에 남기지 않음",
                  flush=True)
            if consec_fail >= 5:
                pickle.dump(cache, open(JG_OOS, "wb"))
                sys.exit(f"[llm] 연속 5회 실패 — LLM 연결 확인 후 재실행(이어서 진행됨). "
                         f"진행분 {len(cache)}건 저장됨")
            continue
        consec_fail = 0
        cache[rn] = res
        cache[rn]["nm"] = nm
        if (i + 1) % 10 == 0:
            el = time.time() - t0
            eta = el / (i + 1) * (len(todo) - i - 1) / 60
            print(f"[llm] {i+1}/{len(todo)}  {nm[:14]} → {cache[rn]['verdict']}"
                  f"({cache[rn]['score']})   ETA {eta:.0f}분", flush=True)
            pickle.dump(cache, open(JG_OOS, "wb"))
    pickle.dump(cache, open(JG_OOS, "wb"))
    print(f"[llm] 완료 {len(cache)}건, {(time.time()-t0)/60:.0f}분")


# ─────────────────────────── 4) 알파 ───────────────────────────

def _alpha_tables(events, judg, data, idx_from):
    """v5_alpha.py와 동일한 계산식: α = 종목수익 − KQ11 수익(같은 구간)."""
    idx = fdr.DataReader("KQ11", idx_from)
    idx.index = pd.to_datetime(idx.index).tz_localize(None)
    ic = idx["Close"]
    io = idx["Open"] if "Open" in idx else idx["Close"]

    alpha = {h: defaultdict(list) for h in HORIZONS}
    alla = {h: [] for h in HORIZONS}
    score_a = {h: defaultdict(list) for h in HORIZONS}
    for code, evs in events.items():
        if code not in data:
            continue
        df = data[code]["df"]; di = df.index
        for d, rn, nm in evs:
            j = judg.get(rn)
            if not j:
                continue
            dd = pd.to_datetime(d, format="%Y%m%d")
            after = di[di > dd]
            if len(after) < 1:
                continue
            entry = after[0]; pos = di.get_loc(entry)
            e_open = df.at[entry, "Open"]
            if pd.isna(e_open) or e_open <= 0 or entry not in ic.index:
                continue
            m_base = io.get(entry, ic.get(entry))
            for h in HORIZONS:
                if pos + h >= len(di):
                    continue
                exit_ts = di[pos + h]
                x_close = df.iloc[pos + h]["Close"]
                if pd.isna(x_close) or exit_ts not in ic.index:
                    continue
                a = ((x_close / e_open - 1) - (ic.get(exit_ts) / m_base - 1)) * 100
                alpha[h][j["verdict"]].append(a)
                alla[h].append(a)
                if j["verdict"] == "강한호재":
                    score_a[h]["95+" if j["score"] >= 95 else "85~94"].append(a)
    return alpha, alla, score_a


def _s(lst):
    if not lst:
        return (0, 0.0, 0.0, 0.0)
    return (len(lst), round(st.mean(lst), 2), round(st.median(lst), 2),
            round(100 * sum(1 for x in lst if x > 0) / len(lst), 0))


def cmd_alpha(_):
    from surge_backtest import load_data
    ev_o = pickle.load(open(EV_OOS, "rb"))
    jg_o = pickle.load(open(JG_OOS, "rb"))
    px_o = pickle.load(open(PX_OOS, "rb"))
    a_o, all_o, sc_o = _alpha_tables(ev_o, jg_o, px_o, "2023-12-01")

    ev_i = pickle.load(open(EV_IS, "rb"))
    jg_i = pickle.load(open(JG_IS, "rb"))
    a_i, all_i, sc_i = _alpha_tables(ev_i, jg_i, load_data(), "2025-05-01")

    print("=" * 84)
    print("  v5 OOS 검증 — 마켓뉴트럴 알파 (종목 − 코스닥지수).  [n / 중앙값α% / 승률%]")
    print(f"  IS  2025-07-03~2026-08-03   vs   OOS  {OOS_BGN}~{OOS_END}")
    print("=" * 84)
    print(f"  {'등급':<10}{'지평':<7}{'IS n':>6}{'IS 중앙α':>10}{'IS 승률':>8}"
          f"{'OOS n':>7}{'OOS 중앙α':>11}{'OOS 승률':>9}")
    print("-" * 84)
    for v in ["강한호재", "약한호재", "중립", "악재"]:
        for h in HORIZONS:
            ni, _, mdi, wi = _s(a_i[h].get(v, []))
            no, _, mdo, wo = _s(a_o[h].get(v, []))
            print(f"  {v if h == HORIZONS[0] else '':<10}H+{h:<5}{ni:>6}{mdi:>+10.2f}{wi:>7.0f}%"
                  f"{no:>7}{mdo:>+11.2f}{wo:>8.0f}%")
        print("-" * 84)

    print("  ── ★핵심 검증: score≥95 (IS 최적 설정) ──")
    for h in HORIZONS:
        ni, _, mdi, wi = _s(sc_i[h].get("95+", []))
        no, _, mdo, wo = _s(sc_o[h].get("95+", []))
        flag = ""
        if no >= 15:
            flag = "  ✅재현" if (mdo > 0 and wo >= 50) else "  ❌미재현"
        print(f"  H+{h:<3} IS n{ni:>3} 중앙α{mdi:>+6.2f} 승{wi:>3.0f}%   |   "
              f"OOS n{no:>3} 중앙α{mdo:>+6.2f} 승{wo:>3.0f}%{flag}")
    print("-" * 84)
    print("  ── 규칙(전체매수) vs LLM(강한호재) ──")
    for h in HORIZONS:
        _, _, mdai, _ = _s(all_i[h]); _, _, mdbi, _ = _s(a_i[h].get("강한호재", []))
        _, _, mdao, _ = _s(all_o[h]); _, _, mdbo, _ = _s(a_o[h].get("강한호재", []))
        print(f"  H+{h:<3} IS: 전체{mdai:>+6.2f} vs 강한호재{mdbi:>+6.2f}   |   "
              f"OOS: 전체{mdao:>+6.2f} vs 강한호재{mdbo:>+6.2f}")
    print("=" * 84)
    print(f"  판정 분포  IS {dict(Counter(j['verdict'] for j in jg_i.values()))}")
    print(f"             OOS {dict(Counter(j['verdict'] for j in jg_o.values()))}")
    print("=" * 84)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["events", "prices", "judge", "alpha"])
    a = ap.parse_args()
    {"events": cmd_events, "prices": cmd_prices,
     "judge": cmd_judge, "alpha": cmd_alpha}[a.cmd](a)
