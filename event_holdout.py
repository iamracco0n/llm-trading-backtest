# -*- coding: utf-8 -*-
"""봉인 홀드아웃 검증 (2022~2023) — 스캔에서 뜬 후보가 다른 구간에서도 재현되나.

**왜 지금 여는가.** `event_base_scan.py`가 2024~2026 구간에서 코스닥 두 유형을 띄웠다:

    자기주식취득  n133  초과중앙값α H+20 +3.03 / H+60 +4.73,  평균 +12.04%, t=4.32
    신규시설투자  n100  초과중앙값α H+20 +6.71 / H+60 +7.06,  평균 +6.31%,  t=3.75

t=4.32는 140칸 스캔의 본페로니 보정(0.05/140)도 통과한다. 하지만 **한 구간짜리다.**
이 레포는 좋아 보이는 숫자를 네 번 무너뜨렸다(급등 +45%, 공시필터 +73%, 장투 2024 +9.8%,
v5 PEAD +3.66%). 다섯 번째가 되지 않으려면 다른 구간에서 재현돼야 한다.

**기준은 결과를 보기 전에 고정했다(사후 변경 금지):**
    재현    = 무작위 대조군 대비 초과 중앙값α가 H+20과 H+60 둘 다 > 0 AND 승률 ≥ 50%
    실전후보 = 위 통과 + 거래비용(코스닥 왕복 0.81%p)을 뺀 뒤에도 +

**남은 한계(정직하게):** 유니버스가 '오늘 기준 코스닥 187 + 상폐 101'이라 2022~2023에
적용하면 룩어헤드가 남는다(상폐를 넣어 생존편향은 완화). 즉 이 검증도 낙관적이다.

사용: python3 event_holdout.py
"""
import os
import time
import pickle
import random
import statistics as st
import math

import pandas as pd
import FinanceDataReader as fdr

from dart_data import get_corp_map
from event_base_scan import (fetch_events, classify, universe, HORIZONS, CACHE)

HOLD_BGN, HOLD_END = "20220101", "20231231"
PX_BGN, PX_END = "2021-12-01", "2024-03-31"      # H+60 커버
EV_H = os.path.join(CACHE, "holdout_events_kosdaq.pkl")
PX_H = os.path.join(CACHE, "holdout_prices_kosdaq.pkl")

TARGETS = ["자기주식취득", "신규시설투자"]
COST_KOSDAQ = 0.81                                # 왕복 %p


def prices(codes, names):
    if os.path.exists(PX_H):
        d = pickle.load(open(PX_H, "rb"))
        print(f"[price] 캐시 사용 {len(d)}종목")
        return d
    out, fail = {}, 0
    print(f"[price] {len(codes)}종목 {PX_BGN}~{PX_END} 수집...")
    for i, c in enumerate(codes):
        try:
            df = fdr.DataReader(c, PX_BGN, PX_END)
        except Exception:
            fail += 1; continue
        if df is None or len(df) < 100:
            fail += 1; continue
        df.index = pd.to_datetime(df.index)
        out[c] = {"name": names.get(c, c), "df": df[["Open", "High", "Low", "Close", "Volume"]]}
        if (i + 1) % 50 == 0:
            print(f"[price]   {i+1}/{len(codes)} (수집 {len(out)}, 실패 {fail})", flush=True)
        time.sleep(0.03)
    pickle.dump(out, open(PX_H, "wb"))
    print(f"[price] 저장 {len(out)}종목 (실패 {fail})")
    return out


def events(codes):
    if os.path.exists(EV_H):
        ev = pickle.load(open(EV_H, "rb"))
        print(f"[dart] 캐시 사용 ({sum(len(v) for v in ev.values())}건)")
        return ev
    cmap = get_corp_map()
    ev, n = {}, 0
    for i, c in enumerate(codes):
        cc = cmap.get(c)
        if not cc:
            continue
        try:
            e = fetch_events(cc, HOLD_BGN, HOLD_END)
        except Exception:
            continue
        if e:
            ev[c] = e; n += len(e)
        if (i + 1) % 50 == 0:
            print(f"[dart] {i+1}/{len(codes)} 누적 {n}건", flush=True)
        time.sleep(0.05)
    pickle.dump(ev, open(EV_H, "wb"))
    print(f"[dart] 이벤트 {n}건 / {len(ev)}종목")
    return ev


def fwd(df, di, entry, h, ic, io):
    pos = di.get_loc(entry)
    eo = df.at[entry, "Open"]
    if pd.isna(eo) or eo <= 0 or entry not in ic.index or pos + h >= len(di):
        return None
    ex = di[pos + h]; xc = df.iloc[pos + h]["Close"]
    if pd.isna(xc) or ex not in ic.index:
        return None
    mb = io.get(entry, ic.get(entry))
    return ((xc / eo - 1) - (ic.get(ex) / mb - 1)) * 100


def run():
    print("⚠️ 봉인 홀드아웃(2022~2023) 개봉 — 1회용. 기준은 사전 고정됨.\n")
    data0, _ = universe("kosdaq")
    names = {c: r["name"] for c, r in data0.items()}
    codes = list(data0)

    px = prices(codes, names)
    ev = events(codes)

    idx = fdr.DataReader("KQ11", PX_BGN)
    idx.index = pd.to_datetime(idx.index).tz_localize(None)
    ic, io = idx["Close"], (idx["Open"] if "Open" in idx else idx["Close"])
    lo, hi = pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")

    # 1) 이벤트별 알파
    res = {h: {g: [] for g in TARGETS} for h in HORIZONS}
    for code, evs in ev.items():
        if code not in px:
            continue
        df = px[code]["df"]; di = df.index
        for d, rn, nm in evs:
            g = classify(nm)
            if g not in TARGETS:
                continue
            dd = pd.to_datetime(d, format="%Y%m%d")
            after = di[di > dd]
            if len(after) < 1:
                continue
            for h in HORIZONS:
                a = fwd(df, di, after[0], h, ic, io)
                if a is not None:
                    res[h][g].append(a)

    # 2) 무작위 날짜 기준선(같은 구간)
    random.seed(20260804)
    base = {h: [] for h in HORIZONS}
    for code, rec in px.items():
        df = rec["df"]; di = df.index
        cand = [t for t in di if lo <= t <= hi]
        if len(cand) < 100:
            continue
        for entry in random.sample(cand, min(20, len(cand))):
            for h in HORIZONS:
                a = fwd(df, di, entry, h, ic, io)
                if a is not None:
                    base[h].append(a)

    print()
    print("=" * 86)
    print("  홀드아웃 2022~2023 (코스닥) — 무작위 대조군 대비 초과 중앙값α")
    print("=" * 86)
    print("  [무작위 기준선] " + "  ".join(
        f"H+{h}:{st.median(base[h]):+.2f}" for h in HORIZONS))
    print("-" * 86)
    verdict = {}
    for g in TARGETS:
        n20 = len(res[20][g])
        print(f"  {g}  (n={n20})")
        ok = {}
        for h in HORIZONS:
            L = res[h][g]
            if not L:
                continue
            md = st.median(L) - st.median(base[h])
            w = 100 * sum(1 for x in L if x > 0) / len(L)
            ok[h] = (md, w)
            print(f"    H+{h:<3} n{len(L):>4}  초과중앙값α {md:>+7.2f}  승률 {w:>4.1f}%"
                  f"   순(비용후) {md - COST_KOSDAQ:>+7.2f}")
        if n20 >= 20:
            L = res[20][g]
            m, sd = st.mean(L), st.stdev(L)
            se = sd / math.sqrt(len(L))
            print(f"    ↳ H+20 평균 {m:+.2f}%  t={m/se:.2f}  95%CI {m-1.96*se:+.2f}~{m+1.96*se:+.2f}")
        rep = (20 in ok and 60 in ok and ok[20][0] > 0 and ok[60][0] > 0
               and ok[20][1] >= 50 and ok[60][1] >= 50)
        live = rep and (ok[20][0] - COST_KOSDAQ > 0 or ok[60][0] - COST_KOSDAQ > 0)
        verdict[g] = (rep, live, n20)
        print(f"    ▶ 사전기준 재현: {'✅ 통과' if rep else '❌ 실패'}"
              f"   실전후보(비용후): {'✅' if live else '❌'}")
        print()
    print("=" * 86)
    print("  사전 고정 기준: 초과중앙값α가 H+20·H+60 둘 다 >0 AND 승률 ≥50% → 재현")
    print(f"  거래비용(코스닥 왕복) {COST_KOSDAQ}%p 차감 후에도 + 여야 실전 후보")
    for g, (rep, live, n) in verdict.items():
        print(f"    {g:<12} n{n:>4}  재현 {'O' if rep else 'X'}  실전후보 {'O' if live else 'X'}")
    print("=" * 86)


if __name__ == "__main__":
    run()
