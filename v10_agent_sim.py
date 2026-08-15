# -*- coding: utf-8 -*-
"""v10 — **LLM이 직접 운용한다.** 과거 시점에 서서 보고, 사고, 앞으로 굴린다.

지금까지(v5·v8·v9)는 전부 **분류**였다 — 공시를 읽고 등급을 매기면 스크립트가
그 등급으로 바구니를 만들었다. 이번은 **운용**이다. 매 시점 유니버스를 보고
무엇을 얼마나 살지, 무엇을 팔지 직접 정한다. Alpha Arena가 실제 돈으로 한 것과
같은 구조이고(4/6 손실, GPT-5 −62.66%), 이 저장소에서는 처음이다.

**왜 2026-06부터인가 — 오염 때문이다.**
판정자(Claude Opus 5)의 학습 컷오프가 2026-05다. 그 이전 구간에서 "무엇을 살까"를
정하면 **결과를 알고 사는 것**이라 시뮬레이션이 아니라 기억이다. 컷오프 이후만 쓴다.
짧지만(52거래일) 오염이 0이다. 이것이 이 실험에서 타협할 수 없는 부분이다.

**규칙(시작 전 고정, 중간 변경 금지)**
  · 자본 1,000,000원, 최대 8종목, 종목당 25% 이하, 공매도 없음
  · 주 1회(월요일) 결정. 체결은 **다음 거래일 시가**, 왕복 비용 0.4%
  · 그 시점까지의 데이터만 제공(미래 봉은 코드가 잘라낸다)
  · 벤치마크: KOSPI, 그리고 같은 기간 규칙봇(`trend_recent.py`)

**제공 정보**: 종가·20/60일 수익률·KOSPI 대비 상대강도·20일 변동성·MA20/60 대비
·52주 고저 대비·거래량비·시총. 차트가 보여주는 것을 숫자로 준다.

사용:
  python3 v10_agent_sim.py prep                 # 시세 수집
  python3 v10_agent_sim.py show                 # 현 시점 스냅샷(다음 결정일)
  python3 v10_agent_sim.py trade --file o.json  # 주문 실행 → 다음 주로
  python3 v10_agent_sim.py report               # 성과
"""
import os
import json
import argparse
import datetime as dt

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
PX = os.path.join(CACHE, "v10_prices%s.pkl" % os.environ.get("SIM_PX", ""))
ST = os.path.join(CACHE, "v10_state%s.json" % os.environ.get("SIM_TAG", ""))

# 기간·주기는 환경변수로 바꾼다 — v12(오염 구간 장기)에서 재사용하기 위함.
START = os.environ.get("SIM_START", "2026-06-01")
END = os.environ.get("SIM_END", "2026-08-14")
FREQ = os.environ.get("SIM_FREQ", "W")        # W=주간, M=월간
ST_TAG = os.environ.get("SIM_TAG", "")
# ⚠️ 자본 1,000만원. 100만원으로 시작했더니 **주문이 전부 0주로 잘려나갔다** —
# 삼성전자 34.9만원/주, SK하이닉스 236만원/주라 비중 12~15%로는 1주도 못 산다.
# 한국 주식은 소수점 매수가 안 되므로 자본이 작으면 대형주 포트폴리오 자체가 불가능하다.
# (이것 자체가 실전 제약이다 — 10만원으로 대형주 분산은 성립하지 않는다.)
CAP = 10_000_000
MAX_POS = 8
MAX_W = 0.25
COST = 0.004          # 왕복(수수료+거래세+슬리피지)


def load_px():
    return pd.read_pickle(PX)


def cmd_prep(args):
    ks = fdr.StockListing("KOSPI").dropna(subset=["Marcap", "Amount"])
    f = ks[(ks["Marcap"] >= 5000e8) & (ks["Amount"] >= 30e8)]
    uni = list(zip(f["Code"], f["Name"], f["Marcap"]))
    print(f"[v10] 유니버스 {len(uni)}종목 수집...")
    data = {}
    for i, (c, n, mc) in enumerate(uni):
        try:
            d = fdr.DataReader(c, os.environ.get("SIM_HIST", "2025-05-01"))
        except Exception:
            continue
        if d is None or len(d) < 150:
            continue
        data[c] = {"name": n, "marcap": float(mc), "df": d}
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(uni)}", flush=True)
    data["_KS11"] = {"name": "KOSPI", "marcap": 0,
                     "df": fdr.DataReader("KS11", os.environ.get("SIM_HIST", "2025-05-01"))}
    pd.to_pickle(data, PX)
    print(f"[v10] 저장 {len(data)-1}종목")


def load_state():
    if os.path.exists(ST):
        return json.load(open(ST, encoding="utf-8"))
    return {"cash": CAP, "pos": {}, "log": [], "equity": [], "step": 0}


def save_state(s):
    json.dump(s, open(ST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def decision_dates(data):
    """START~END 사이의 매주 첫 거래일."""
    idx = data["_KS11"]["df"].index
    idx = idx[(idx >= START) & (idx <= END)]
    ser = pd.Series(idx)
    if FREQ == "D":                       # 단타 — 매 거래일 결정
        return list(ser)
    if FREQ == "M":
        return list(ser.groupby(ser.dt.to_period("M")).first())
    # ⚠️ ISO 주차만으로 묶으면 **연도를 넘어 같은 주차가 한 그룹이 된다**
    # (2025년 1주차 + 2026년 1주차). 단일 연도 구간에서는 안 드러나다가
    # 장기 시뮬(v12)에서 첫 결정일이 2025-12-29로 잡혀 발견했다. 연도를 함께 묶는다.
    iso = ser.dt.isocalendar()
    weeks = list(ser.groupby([iso.year, iso.week]).first())
    if FREQ == "2W":                      # 격주 — 주간 첫 거래일을 하나 걸러 취한다
        return weeks[::2]
    return weeks


def snapshot(data, ts, top=200):
    ks = data["_KS11"]["df"]["Close"]
    kh = ks[ks.index <= ts]
    rows = []
    for c, d in data.items():
        if c == "_KS11":
            continue
        df = d["df"]
        h = df[df.index <= ts]                 # ⚠️ 미래 차단
        if len(h) < 120:
            continue
        cl, vol = h["Close"], h["Volume"]
        r20 = cl.iloc[-1] / cl.iloc[-21] - 1
        k20 = kh.iloc[-1] / kh.iloc[-21] - 1
        rows.append({
            "code": c, "name": d["name"][:8],
            "close": float(cl.iloc[-1]),
            "mc": d["marcap"] / 1e12,
            "r5": float(cl.iloc[-1] / cl.iloc[-6] - 1) * 100,
            "r20": r20 * 100, "r60": (cl.iloc[-1] / cl.iloc[-61] - 1) * 100,
            "rel": (r20 - k20) * 100,
            "vol": float(cl.pct_change().tail(20).std() * 100),
            "ma20": (cl.iloc[-1] / cl.tail(20).mean() - 1) * 100,
            "ma60": (cl.iloc[-1] / cl.tail(60).mean() - 1) * 100,
            "hi52": (cl.iloc[-1] / cl.tail(250).max() - 1) * 100,
            "vr": float(vol.iloc[-1] / vol.tail(20).mean()) if vol.tail(20).mean() else 0,
        })
    df = pd.DataFrame(rows)
    # 단타는 시총 상위가 아니라 **실제로 움직이는 종목**을 봐야 한다.
    # SORT=mv 면 (거래량비 × |5일 수익률|) 순으로 급등·급락주를 앞세운다.
    if os.environ.get("SIM_SORT") == "mv":
        df["mv"] = df["vr"] * df["r5"].abs()
        df = df.sort_values("mv", ascending=False)
    else:
        df = df.sort_values("mc", ascending=False)
    return df.head(top)


def mark(data, ts, state):
    mv = state["cash"]
    for c, p in state["pos"].items():
        h = data[c]["df"]
        h = h[h.index <= ts]
        if len(h):
            mv += p["qty"] * float(h["Close"].iloc[-1])
    return mv


def cmd_show(args):
    data = load_px()
    st = load_state()
    dates = decision_dates(data)
    if st["step"] >= len(dates):
        print("모든 결정일 종료. report 를 실행하라."); return
    ts = dates[st["step"]]
    ks = data["_KS11"]["df"]["Close"]
    ksn = ks[ks.index <= ts].iloc[-1]
    ks0 = ks[ks.index >= START].iloc[0]
    eq = mark(data, ts, st)
    print(f"### 결정 {st['step']+1}/{len(dates)} — {ts.date()} "
          f"(KOSPI {100*(ksn/ks0-1):+.1f}% since {START})")
    print(f"### 평가자산 {eq:,.0f}원 ({100*(eq/CAP-1):+.2f}%) | 현금 {st['cash']:,.0f}원")
    if st["pos"]:
        print("### 보유:")
        for c, p in st["pos"].items():
            h = data[c]["df"]; h = h[h.index <= ts]
            cur = float(h["Close"].iloc[-1])
            print(f"  {c} {data[c]['name'][:8]:<9} {p['qty']}주 "
                  f"매입 {p['px']:,.0f} 현재 {cur:,.0f} ({100*(cur/p['px']-1):+.1f}%)")
    else:
        print("### 보유: 없음")
    df = snapshot(data, ts, args.top)
    print(f"\n### 유니버스 {len(df)}종목 (시총순, 단위: 시총 조원 / 나머지 %)")
    print("code name       종가      r5    r20    rel    변동  MA20   52고  거래량")
    for _, r in df.iterrows():
        print(f"{r['code']} {r['name']:<9}{r['close']:>7,.0f} "
              f"{r['r5']:>+6.1f} {r['r20']:>+6.1f} {r['rel']:>+6.1f} {r['vol']:>5.1f} "
              f"{r['ma20']:>+6.1f} {r['hi52']:>+6.1f} {r['vr']:>5.2f}")
    print(f"\n### 주문 형식: {{\"buy\": {{\"005930\": 0.2}}, \"sell\": [\"000660\"]}}")
    print(f"### buy 값은 평가자산 대비 비중(최대 {MAX_W:.0%}), 최대 {MAX_POS}종목")


def cmd_trade(args):
    data = load_px()
    st = load_state()
    dates = decision_dates(data)
    ts = dates[st["step"]]
    orders = json.load(open(args.file, encoding="utf-8"))
    cal = data["_KS11"]["df"].index
    nxt = cal[cal > ts]
    if not len(nxt):
        print("다음 거래일 없음"); return
    ex = nxt[0]                                  # 체결일 = 다음 거래일 시가

    for c in orders.get("sell", []):
        if c not in st["pos"]:
            continue
        h = data[c]["df"]; h = h[h.index == ex]
        if not len(h):
            continue
        px = float(h["Open"].iloc[0])
        st["cash"] += st["pos"][c]["qty"] * px * (1 - COST / 2)
        st["log"].append([str(ex.date()), "SELL", c, px, st["pos"][c]["qty"]])
        del st["pos"][c]

    eq = mark(data, ts, st)
    for c, w in orders.get("buy", {}).items():
        if c in st["pos"] or len(st["pos"]) >= MAX_POS or c not in data:
            continue
        h = data[c]["df"]; h = h[h.index == ex]
        if not len(h):
            continue
        px = float(h["Open"].iloc[0])
        amt = min(float(w), MAX_W) * eq
        qty = int(amt / (px * (1 + COST / 2)))
        cost = qty * px * (1 + COST / 2)
        if qty <= 0:
            print(f"  ⚠️ {c} {data[c]['name']}: 배분 {amt:,.0f}원 < 1주 가격 "
                  f"{px:,.0f}원 → 체결 불가")
            continue
        if cost > st["cash"]:
            print(f"  ⚠️ {c}: 현금 부족({st['cash']:,.0f} < {cost:,.0f}) → 체결 불가")
            continue
        st["cash"] -= cost
        st["pos"][c] = {"qty": qty, "px": px}
        st["log"].append([str(ex.date()), "BUY", c, px, qty])

    st["step"] += 1
    end_ts = dates[st["step"]] if st["step"] < len(dates) else cal[cal <= END][-1]
    for d in cal[(cal > ts) & (cal <= end_ts)]:
        st["equity"].append([str(d.date()), round(mark(data, d, st), 0)])
    save_state(st)
    print(f"[v10] 체결일 {ex.date()} | 보유 {len(st['pos'])}종목 | "
          f"현금 {st['cash']:,.0f} | 평가 {mark(data, end_ts, st):,.0f}원 "
          f"({100*(mark(data, end_ts, st)/CAP-1):+.2f}%)")
    print(f"[v10] 다음 결정 {st['step']+1}/{len(dates)}")


def cmd_report(args):
    data = load_px()
    st = load_state()
    if not st["equity"]:
        print("기록 없음"); return
    s = pd.Series({pd.Timestamp(d): v for d, v in st["equity"]}).sort_index()
    ks = data["_KS11"]["df"]["Close"]
    ks = ks[(ks.index >= s.index[0]) & (ks.index <= s.index[-1])]
    bench = (ks.iloc[-1] / ks.iloc[0] - 1) * 100
    ret = (s.iloc[-1] / CAP - 1) * 100
    mdd = float((s / s.cummax() - 1).min()) * 100
    print("=" * 62)
    print(f"  v10 — LLM 직접 운용 (컷오프 이후, 오염 0)")
    print("=" * 62)
    print(f"  기간 {s.index[0].date()} ~ {s.index[-1].date()} ({len(s)}거래일)")
    print(f"  수익률 {ret:+.2f}%   MDD {mdd:.2f}%")
    print(f"  KOSPI  {bench:+.2f}%   초과 {ret-bench:+.2f}%p")
    print(f"  거래 {len(st['log'])}건 | 보유 {len(st['pos'])}종목")
    for r in st["log"]:
        nm = data[r[2]]["name"][:8] if r[2] in data else r[2]
        print(f"    {r[0]} {r[1]:<4} {nm:<9} {r[3]:>8,.0f}원 x{r[4]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "show", "trade", "report"])
    ap.add_argument("--file")
    ap.add_argument("--top", type=int, default=200)
    a = ap.parse_args()
    {"prep": cmd_prep, "show": cmd_show,
     "trade": cmd_trade, "report": cmd_report}[a.cmd](a)
