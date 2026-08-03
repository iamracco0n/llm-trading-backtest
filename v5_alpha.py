# -*- coding: utf-8 -*-
"""v5 마켓뉴트럴 — 실적 등급별 '알파'(종목수익 − 코스닥지수 수익) 분리.

raw 수익엔 상승장 베타가 섞여 강한호재/악재 다 +로 보임(특히 H+40). 종목수익에서
같은 기간 코스닥(KQ11) 수익을 빼서 시장베타를 걷어내면, LLM '강한호재'가 진짜
종목선택 알파를 갖는지(=시장 이겼는지) 나온다. 평균은 꼬리에 휘둘리니 중앙값도 같이.
"""
import pickle
import statistics as st
from collections import defaultdict
import pandas as pd
import FinanceDataReader as fdr

from surge_backtest import load_data

EVENTS = "cache/v5_earnings_events.pkl"
JUDGE = "cache/v5_earnings_judgments.pkl"
HORIZONS = [20, 40, 60, 90]


def run():
    data = load_data()
    events = pickle.load(open(EVENTS, "rb"))
    judg = pickle.load(open(JUDGE, "rb"))
    # 코스닥 지수
    idx = fdr.DataReader("KQ11", "2025-05-01")
    idx.index = pd.to_datetime(idx.index).tz_localize(None)
    ic = idx["Close"]; io = idx["Open"] if "Open" in idx else idx["Close"]

    alpha = {h: defaultdict(list) for h in HORIZONS}
    alla = {h: [] for h in HORIZONS}
    score_a = {h: defaultdict(list) for h in HORIZONS}  # 강한호재를 score대별로
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
                r_stock = x_close / e_open - 1
                r_mkt = ic.get(exit_ts) / m_base - 1
                a = (r_stock - r_mkt) * 100
                alpha[h][j["verdict"]].append(a)
                alla[h].append(a)
                if j["verdict"] == "강한호재":
                    bucket = "95+" if j["score"] >= 95 else "85~94"
                    score_a[h][bucket].append(a)

    def s(lst):
        if not lst:
            return (0, 0, 0, 0)
        return (len(lst), round(st.mean(lst), 2), round(st.median(lst), 2),
                round(100 * sum(1 for x in lst if x > 0) / len(lst), 0))

    print("=" * 78)
    print("  v5 마켓뉴트럴 알파 (종목수익 − 코스닥지수, 같은 기간)   [n / 평균α% / 중앙값α% / α승률%]")
    print("=" * 78)
    for v in ["강한호재", "약한호재", "중립", "악재"]:
        print(f"  {v}")
        for h in HORIZONS:
            n, m, md, w = s(alpha[h].get(v, []))
            print(f"     H+{h:<2}:  n{n:>3}   평균 {m:>+6.2f}   중앙값 {md:>+6.2f}   승률 {w:>3.0f}%")
    print("-" * 78)
    print("  ── 규칙 vs LLM (알파 기준) ──")
    for h in HORIZONS:
        na, ma, mda, wa = s(alla[h])
        nb, mb, mdb, wb = s(alpha[h].get("강한호재", []))
        print(f"  H+{h:<2}:  A)전체 평균α{ma:>+6.2f}/중앙{mda:>+6.2f}/승{wa:>3.0f}%   |   "
              f"B)강한호재 평균α{mb:>+6.2f}/중앙{mdb:>+6.2f}/승{wb:>3.0f}%")
    print("-" * 78)
    print("  ── 강한호재 score대별 (확신 높을수록 알파 큰가?) ──")
    for h in HORIZONS:
        n9, m9, md9, w9 = s(score_a[h].get("95+", []))
        n8, m8, md8, w8 = s(score_a[h].get("85~94", []))
        print(f"  H+{h:<2}:  95+  n{n9:>3} 평균{m9:>+6.2f}/중앙{md9:>+6.2f}/승{w9:>3.0f}%   |   "
              f"85~94 n{n8:>3} 평균{m8:>+6.2f}/중앙{md8:>+6.2f}/승{w8:>3.0f}%")
    print("=" * 78)


if __name__ == "__main__":
    run()
