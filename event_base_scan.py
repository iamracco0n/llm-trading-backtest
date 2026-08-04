# -*- coding: utf-8 -*-
"""이벤트 유형별 base 알파 스캔 — LLM 붙이기 전에 '플러스인 판'을 먼저 찾는다.

**v5에서 뼈저리게 배운 것.** 실적공시 PEAD는 LLM을 아무리 잘 써도 안 됐는데, 원인이
LLM이 아니라 **판의 base 알파가 음(−)** 이었다(코스닥 −0.3~−3.1, 코스피 −2.4~−6.8,
심지어 무작위 날짜 대조군보다 나쁨). LLM이 얹을 수 있는 건 +1.6%p 안팎이고
StockBench 기준 세계 최고 모델도 +2.5%p가 천장이다. 즉 **base가 −2%면 게임이 끝난다.**

그래서 이번엔 순서를 바꾼다. **LLM 없이** 여러 공시 유형의 base 알파를 먼저 재서
플러스인 판이 실제로 있는지 확인한다. 있으면 그때 LLM을 붙인다.

**후보 1순위는 자사주(자기주식).** 국내 실증연구들이 일관되게 보고하는 바:
  취득—주가안정/이익소각 → 양(+),  취득—임직원 인센티브 → 음(−)
  처분—운영자금/재무구조   → 양(+),  처분—임직원 보상/신탁해지 → 음(−)
같은 "자기주식취득결정" 공시인데 **목적에 따라 부호가 갈리고, 목적은 제목이 아니라
본문에 있다** → 키워드 규칙으로는 불가능하고 LLM이 필요한 자리. 다만 그건 다음 단계고,
여기서는 자사주 이벤트군의 base가 정말 +인지부터 본다.

실험 구간 2024-01-01~2026-08-03. **2022~2023은 홀드아웃으로 계속 봉인**한다.

사용: python3 event_base_scan.py [--market kospi|kosdaq|both]
"""
import os
import json
import time
import pickle
import argparse
import statistics as st
import urllib.parse
import urllib.request
from collections import defaultdict

import pandas as pd
import FinanceDataReader as fdr

from dart_data import get_corp_map, _key, BASE

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
EV_CACHE = os.path.join(CACHE, "event_scan_events_{market}.pkl")

BGN, END = "20240101", "20260803"          # 2022~2023은 봉인 유지
HORIZONS = [5, 10, 20, 40, 60]

# 공시 유형 그룹 — 앞에서부터 먼저 매칭되는 것으로 분류(순서 중요)
GROUPS = [
    ("자기주식취득", ["자기주식취득", "자기주식 취득"]),
    ("자기주식처분", ["자기주식처분", "자기주식 처분"]),
    ("자사주신탁", ["신탁계약체결", "신탁계약 해지"]),
    ("무상증자", ["무상증자"]),
    ("유상증자", ["유상증자"]),
    ("최대주주변경", ["최대주주"]),
    ("타법인주식취득", ["타법인"]),
    ("공급계약·수주", ["공급계약", "수주"]),
    ("특허·임상·허가", ["특허", "임상", "품목허가"]),
    ("신규시설투자", ["신규시설투자"]),
    ("현금·현물배당", ["현금·현물배당", "현금배당"]),
    ("주식분할·병합", ["주식분할", "주식병합", "액면"]),
    ("합병·분할", ["합병결정", "분할결정"]),
    ("실적공시(대조군)", ["매출액또는손익", "영업(잠정)실적"]),
]
ALL_KW = [k for _, ks in GROUPS for k in ks]


def classify(nm):
    for g, ks in GROUPS:
        if any(k in nm for k in ks):
            return g
    return None


def fetch_events(corp_code, bgn, end):
    """(rcept_dt, rcept_no, report_nm) — 우리 그룹 키워드에 걸리는 공시만."""
    out, page = [], 1
    while True:
        p = urllib.parse.urlencode({"crtfc_key": _key(), "corp_code": corp_code,
                                    "bgn_de": bgn, "end_de": end,
                                    "page_no": page, "page_count": 100})
        with urllib.request.urlopen(f"{BASE}/list.json?" + p, timeout=20) as r:
            j = json.loads(r.read())
        if j.get("status") != "000":
            break
        for it in j.get("list", []):
            nm = it["report_nm"].strip()
            if any(k in nm for k in ALL_KW):
                out.append((it["rcept_dt"], it["rcept_no"], nm))
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.05)
    return out


def universe(market):
    """가격 데이터 + 이름 (상폐 포함 → 생존편향 완화)."""
    data = {}
    if market == "kospi":
        base = pickle.load(open(os.path.join(CACHE, "trend_kospi_long.pkl"), "rb"))
        for c, r in base.items():
            data[c] = {"name": r["name"], "df": r["df"]}
        mk, idx = "KOSPI", "KS11"
    else:
        from surge_backtest import load_data
        for c, r in load_data().items():
            data[c] = {"name": r["name"], "df": r["df"]}
        mk, idx = "KOSDAQ", "KQ11"
    dl = os.path.join(CACHE, "delisted_prices.pkl")
    n_live = len(data)
    if os.path.exists(dl):
        for c, r in pickle.load(open(dl, "rb")).items():
            if r["market"] == mk and c not in data:
                data[c] = {"name": r["name"], "df": r["df"]}
    print(f"[{market}] 현재상장 {n_live} + 상폐 {len(data)-n_live} = {len(data)}종목")
    return data, idx


def collect(market, data):
    path = EV_CACHE.format(market=market)
    if os.path.exists(path):
        ev = pickle.load(open(path, "rb"))
        print(f"[{market}] 이벤트 캐시 사용 ({sum(len(v) for v in ev.values())}건)")
        return ev
    cmap = get_corp_map()
    ev, n, miss = {}, 0, 0
    codes = list(data)
    for i, code in enumerate(codes):
        cc = cmap.get(code)
        if not cc:
            miss += 1
            continue
        try:
            evs = fetch_events(cc, BGN, END)
        except Exception:
            continue
        if evs:
            ev[code] = evs
            n += len(evs)
        if (i + 1) % 50 == 0:
            print(f"[{market}] {i+1}/{len(codes)} 누적 {n}건", flush=True)
        time.sleep(0.05)
    pickle.dump(ev, open(path, "wb"))
    print(f"[{market}] 이벤트 {n}건 / {len(ev)}종목 (corp_code 실패 {miss})")
    return ev


def alpha_by_group(ev, data, index):
    idx = fdr.DataReader(index, "2023-12-01")
    idx.index = pd.to_datetime(idx.index).tz_localize(None)
    ic = idx["Close"]
    io = idx["Open"] if "Open" in idx else idx["Close"]

    res = {h: defaultdict(list) for h in HORIZONS}
    for code, evs in ev.items():
        if code not in data:
            continue
        df = data[code]["df"]; di = df.index
        for d, rn, nm in evs:
            g = classify(nm)
            if not g:
                continue
            dd = pd.to_datetime(d, format="%Y%m%d")
            after = di[di > dd]
            if len(after) < 1:
                continue
            entry = after[0]; pos = di.get_loc(entry)
            eo = df.at[entry, "Open"]
            if pd.isna(eo) or eo <= 0 or entry not in ic.index:
                continue
            mb = io.get(entry, ic.get(entry))
            for h in HORIZONS:
                if pos + h >= len(di):
                    continue
                ex = di[pos + h]; xc = df.iloc[pos + h]["Close"]
                if pd.isna(xc) or ex not in ic.index:
                    continue
                res[h][g].append(((xc / eo - 1) - (ic.get(ex) / mb - 1)) * 100)
    return res


def report(market, res):
    print()
    print("=" * 92)
    print(f"  {market.upper()} — 공시 유형별 base 알파 (LLM 없음, 전체매수)   [중앙값α% / 승률%]")
    print("=" * 92)
    hdr = f"  {'이벤트 유형':<18}{'n':>6}" + "".join(f"{'H+'+str(h):>13}" for h in HORIZONS)
    print(hdr)
    print("-" * 92)
    order = sorted(res[20], key=lambda g: -st.median(res[20][g]) if res[20][g] else 99)
    for g in order:
        n = len(res[20].get(g, []))
        if n < 20:                                   # 표본 20건 미만은 판정 불가
            continue
        row = f"  {g:<18}{n:>6}"
        for h in HORIZONS:
            L = res[h].get(g, [])
            if not L:
                row += f"{'—':>13}"
                continue
            md = st.median(L)
            w = 100 * sum(1 for x in L if x > 0) / len(L)
            row += f"{md:>+8.2f}/{w:>3.0f}%"
        print(row)
    print("-" * 92)
    small = [(g, len(res[20][g])) for g in res[20] if len(res[20][g]) < 20]
    if small:
        print(f"  (표본 20건 미만 제외: {', '.join(f'{g}({n})' for g, n in small)})")
    print("=" * 92)


def run(args):
    markets = ["kospi", "kosdaq"] if args.market == "both" else [args.market]
    for m in markets:
        data, index = universe(m)
        ev = collect(m, data)
        report(m, alpha_by_group(ev, data, index))
    print("\n  ※ 실적공시(대조군)가 음(−)으로 나와야 v5 결과와 일관 — 검산 지표로 볼 것")
    print("  ※ base가 +인 유형이 나오면 그게 다음 LLM 실험의 판이다(자사주 목적분류 등)")
    print("  ※ 2022~2023은 홀드아웃으로 계속 봉인 중")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["kospi", "kosdaq", "both"], default="both")
    run(ap.parse_args())
