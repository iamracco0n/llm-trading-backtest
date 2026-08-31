# -*- coding: utf-8 -*-
"""미장 추세추종 — 포워드 페이퍼 / 실행. **기본은 페이퍼, 실주문은 이중 잠금.**

━━━ 규칙 (v26 선정, 고정) ━━━
    유니버스  S&P500 + 나스닥 상위 587종목
    진입      직전 **40봉** 고가 돌파  그리고  종가 > **MA120**
              후보는 **20일 모멘텀** 순, 슬롯 **3개**
    청산      샹들리에 트레일링 — 보유 중 최고가 − **3.0 × ATR14**
    국면필터  **없음**(regime0). 한국과 다른 점 — 미장은 IS 탐색에서 필터가
              선택되지 않았고, 하락장이었던 2022 조각에서도 Sharpe 0.82 로 버텼다.
    비용      왕복 0.20% (수수료 0.1%×2, 거래세 없음) + 환전 스프레드(미반영)

**소수점 매수를 쓴다.** 토스 API 명세상 `orderAmount`(금액 지정)는 US MARKET 전용이다.
$72.5 를 3등분하면 슬롯당 약 $24.17 이고, 1주 단위 제약이 없어 비중이 정확히 맞는다.
(한국은 1주 단위라 10만원/3슬롯이면 유니버스의 49%만 살 수 있다.)

━━━ 검증 상태 ━━━
IS 2021-09~2024-12 에서 3조각 maximin 으로 선정 → OOS 2025-01~2026-08 을 **한 번** 열었다.
    IS  +177.1%  SR 1.22  |  OOS +78.9%  SR 1.21  |  대조군 +41.5%
IS·OOS Sharpe 가 거의 같아 과최적화 감쇠가 없다. v27 에서 개선(리스크 패리티·섹터제한)을
시도했으나 IS 에서 선택되지 않아 **원본을 그대로 쓴다.**

━━━ 안전장치 (toss_trade 와 동일 철학) ━━━
`--live` 플래그 **그리고** 환경변수 `TOSS_LIVE=1` 이 둘 다 있어야 실주문이 나간다.
하나만으로는 안 나간다. 주문 금액은 슬롯 크기로 제한되고, 계좌 잔고를 넘지 않는다.

━━━ 사전 기준 (기록 쌓기 전에 고정) ━━━
6개월 또는 거래 30건 중 나중에 오는 시점에:
  (a) 거래당 평균 > 0.20%  (b) 누적 > 유니버스 동일가중  (c) MDD > −30%  (d) 거래 30건+

사용: python3 us_trend_paper.py              # 페이퍼(기본)
      python3 us_trend_paper.py --signals    # 오늘 신호만 보기
      TOSS_LIVE=1 python3 us_trend_paper.py --live   # 실주문(승인 후)
"""
import argparse
import datetime as dt
import json
import os
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cache", "us_trend_state.json")
PXC = os.path.join(HERE, "cache", "v26_us_px.pkl")

# v26 선정 — 고정. 바꾸지 않는다.
DC_ENTRY, MA_TREND, CHAND, MOM, SLOTS = 40, 120, 3.0, 20, 3
ATR_N = 14
COST = 0.20
CAP_USD = 72.5
DEADLINE = 240


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"start": dt.date.today().isoformat(), "cash": CAP_USD,
            "pos": {}, "closed": [], "equity": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def symbols():
    """캐시된 유니버스. 없으면 받아서 캐시한다."""
    if os.path.exists(PXC):
        raw = pickle.load(open(PXC, "rb"))
        return [(c, v["name"]) for c, v in raw.items()]
    raise RuntimeError("유니버스 캐시가 없다 — v26 데이터를 먼저 받을 것")


def us_today():
    """미국 동부 기준 '오늘' 날짜. 서머타임(EDT, UTC−4) 가정.

    한국 밤 22:30 은 미국 당일 09:30 개장 시각이다. 즉 **장중에 실행된다.**
    이때 데이터 소스가 오늘의 **미완성 봉**을 마지막 행으로 줄 수 있는데,
    그걸 종가로 쓰면 신호가 백테스트와 달라진다(백테스트는 완료된 종가로 신호를
    만들고 다음 시가에 산다). 그래서 오늘 날짜 행은 잘라낸다."""
    return (dt.datetime.utcnow() - dt.timedelta(hours=4)).date()


def indicators(d):
    d = d.dropna(subset=["Close"])
    # ⚠️ 장중 실행 시 오늘의 미완성 봉이 붙는다. 신호는 **직전 완료 세션**으로만.
    cut = us_today()
    d = d[d.index.date < cut]
    if len(d) < MA_TREND + 30:
        return None
    hi, lo, cl = d["High"], d["Low"], d["Close"]
    pc = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return {"close": float(cl.iloc[-1]), "high": float(hi.iloc[-1]),
            "atr": float(tr.rolling(ATR_N).mean().iloc[-1]),
            "dc": float(hi.rolling(DC_ENTRY).max().shift(1).iloc[-1]),
            "ma": float(cl.rolling(MA_TREND).mean().iloc[-1]),
            "mom": float(cl.iloc[-1] / cl.iloc[-1 - MOM] - 1)}


def fetch_all(syms):
    import FinanceDataReader as fdr
    since = (dt.date.today() - dt.timedelta(days=500)).isoformat()

    def one(it):
        s, n = it
        try:
            x = indicators(fdr.DataReader(s, since))
            return (s, n, x) if x else None
        except Exception:
            return None

    out, done, t0 = {}, 0, time.time()
    ex = ThreadPoolExecutor(max_workers=8)
    futs = {ex.submit(one, it): it for it in syms}
    try:
        for fu in as_completed(futs, timeout=DEADLINE):
            done += 1
            if done % 150 == 0:
                print(f"    {done}/{len(syms)}  {time.time()-t0:.0f}초", flush=True)
            try:
                r = fu.result(timeout=1)
            except Exception:
                continue
            if r:
                out[r[0]] = (r[1], r[2])
    except TimeoutError:
        print(f"  ⚠️ 마감 {DEADLINE}초 — {done}/{len(syms)} 까지만", flush=True)
    for fu in futs:
        fu.cancel()
    ex.shutdown(wait=False)
    return out


def main(a):
    st = load_state()
    today = dt.date.today().isoformat()
    print(f"===== 미장 추세추종 {'[실주문]' if a.live else '[페이퍼]'}  {today} "
          f"(시작 {st['start']}) =====")
    print(f"  규칙: DC{DC_ENTRY} MA{MA_TREND} 샹들리에{CHAND}xATR 모멘텀{MOM} "
          f"슬롯{SLOTS} 국면필터없음")

    syms = symbols()
    print(f"  신호 기준: 미국 {us_today()} **이전** 완료 세션 (장중 미완성 봉 제외)")
    print(f"  유니버스 {len(syms)}종목 조회...", flush=True)
    ind = fetch_all(syms)
    print(f"  조회 {len(ind)}/{len(syms)}종목")
    if len(ind) < len(syms) * 0.7:
        raise RuntimeError("조회 부족 — 신호 왜곡. 오늘은 기록하지 않는다.")

    slot = CAP_USD / SLOTS

    # 청산
    for s in list(st["pos"]):
        if s not in ind:
            continue
        name, x = ind[s]
        p = st["pos"][s]
        p["peak"] = max(p["peak"], x["high"])
        if x["close"] <= p["peak"] - CHAND * x["atr"]:
            st["cash"] += p["qty"] * x["close"] * (1 - COST / 100)
            r = (x["close"] / p["entry"] - 1) * 100 - COST
            st["closed"].append({"sym": s, "name": name, "ret": round(r, 2),
                                 "in": p["date"], "out": today})
            print(f"  ▣ 청산 {s} ({name[:18]}) {r:+.2f}%")
            del st["pos"][s]

    # 후보
    cands = sorted(((x["mom"], s, nm, x["close"])
                    for s, (nm, x) in ind.items()
                    if x["close"] > x["dc"] and x["close"] > x["ma"]
                    and not np.isnan(x["mom"])), reverse=True)
    print(f"\n  돌파 후보 {len(cands)}개 | 보유 {len(st['pos'])}/{SLOTS}")
    print(f"  {'순위':<4}{'심볼':<7}{'종목':<24}{'현재가':>10}{'모멘텀':>9}")
    print("  " + "-" * 56)
    picks = []
    for i, (m, s, nm, px) in enumerate(cands[:8], 1):
        mark = ""
        if s not in st["pos"] and len(st["pos"]) + len(picks) < SLOTS:
            picks.append((s, nm, px, m))
            mark = "  ← 매수대상"
        print(f"  {i:<4}{s:<7}{nm[:22]:<24}{px:>10,.2f}{m*100:>8.1f}%{mark}")

    if a.signals:
        print(f"\n  --signals 이므로 주문/기록 없음. 슬롯당 ${slot:.2f}")
        return

    # 진입
    for s, nm, px, m in picks:
        amt = min(slot, st["cash"])
        if amt < 1:
            continue
        if a.live:
            if os.environ.get("TOSS_LIVE") != "1":
                print(f"  ⚠️ --live 인데 TOSS_LIVE!=1 — 주문하지 않는다")
                break
            from toss_trade import Toss
            t = Toss()
            # ★ 금액 기반(orderAmount). amt 를 수량 자리에 넘기면 24주를 사려 든다.
            r = t.order(s, side="BUY", market="US", amount=amt, confirm=True)
            print(f"  ▶ [실주문] {s} ${amt:.2f} → {r}")
        else:
            print(f"  ▶ [페이퍼] 매수 {s} ${amt:.2f} @{px:,.2f} "
                  f"(모멘텀 {m*100:+.1f}%)")
        st["cash"] -= amt
        st["pos"][s] = {"qty": amt / px, "entry": px, "peak": px,
                        "date": today, "name": nm}

    mv = st["cash"] + sum(p["qty"] * ind[s][1]["close"]
                          for s, p in st["pos"].items() if s in ind)
    print(f"\n  평가액 ${mv:,.2f} ({(mv/CAP_USD-1)*100:+.2f}%)")
    for s, p in st["pos"].items():
        cur = ind[s][1]["close"] if s in ind else p["entry"]
        print(f"    {s:<6} {p['qty']:.4f}주 @{p['entry']:,.2f} → {cur:,.2f} "
              f"({(cur/p['entry']-1)*100:+.1f}%)")
    if st["closed"]:
        r = [c["ret"] for c in st["closed"]]
        print(f"  청산 {len(r)}건 | 거래당 {np.mean(r):+.2f}% | "
              f"승률 {100*np.mean([x>0 for x in r]):.0f}%")
    st["equity"].append([today, round(mv, 4)])
    save_state(st)
    print(f"  {'실주문 실행됨' if a.live else '실주문 없음(페이퍼)'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--signals", action="store_true")
    main(p.parse_args())
