# -*- coding: utf-8 -*-
"""Stage 0(B) — 전략 B(급등 + DART 공시촉매) 포워드 페이퍼. 실주문 없음, 결정만 기록.

**왜 만드나 — 판정을 미래 데이터로 넘기기 위해.**
백테스트에서 B는 +73.78%가 나왔다. 하지만 그 수익의 82%가 트레이드 3건(성호전자 +138%,
PS일렉 +85%, 온코닉 +81%)에서 나왔고, 상위 5건을 빼면 평균이 −1.30%/트레이드로 뒤집힌다.
통계적으로도:

    트레이드당 평균 +6.12%, 표준편차 30.5%, 표본 61건
    → t = 1.57,  95% 신뢰구간 −1.53% ~ +13.77%/트레이드  → **0을 포함**

즉 "엣지가 있다"고도 "없다"고도 말할 수 없는 상태다. 과거 데이터를 더 파서 표본을 늘리면
같은 편향(생존편향·유니버스 룩어헤드)이 또 들어간다. **앞으로의 데이터로만 늘릴 수 있다.**

t=1.96을 넘기려면 같은 평균·표준편차 기준 약 96건이 필요하다 → 지금부터 약 35건 더.
B의 신호 빈도(14개월 61건)면 대략 8개월치다. 이 스크립트는 그 35건을 모으는 장치다.

규칙은 `surge_dart_backtest.py`와 완전히 동일하게 유지한다(그래야 표본을 이어붙일 수 있다):
    신호  거래량 ≥ 20일평균×3  AND  당일 +6%  AND  직전 20일 고점 돌파
          AND 신호일 기준 과거 5일 내 DART 촉매공시
    진입  다음 거래일 시가 / 사이징 자본 1/5씩 최대 5종목
    청산  −8% 손절 / 최고가 −3×ATR 트레일 / 15거래일 만료

매일 장 마감 후 1회 실행(cron). 같은 날 두 번 돌려도 멱등.

사용: python3 forward_paper_b.py            오늘분 진행
      python3 forward_paper_b.py --status   상태·통계만
      python3 forward_paper_b.py --force    미확정 봉이어도 강제(테스트)
"""
import os
import json
import argparse
import datetime as dt

import pandas as pd
import FinanceDataReader as fdr

from surge_backtest import (get_universe, START_KRW, MAX_POS, POS_KRW, VOL_SURGE,
                            UP_MIN, CH_MULT, HARD_STOP, MAX_HOLD, FEE_BUY, FEE_SELL)
from surge_dart_backtest import CATALYST_WINDOW_DAYS
from dart_data import get_corp_map, get_disclosures, CATALYST_KW

STATE = os.path.join(os.path.dirname(__file__), "cache", "paper_b_state.json")
SLIP = 0.003
SETTLE = dt.time(16, 0)      # 장중 미확정 봉으로 하루를 소진하지 않기 위한 가드
TARGET_N = 96                # t=1.96 통과에 필요한 대략의 표본 수


def _blank():
    return {"start_date": None, "last_date": None, "cash": START_KRW, "positions": {},
            "pending": [], "equity": [], "trades": [], "universe": []}


def load():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return _blank()


def save(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def bar_settled(bar_date, now=None):
    now = now or dt.datetime.now()
    return True if bar_date < now.date() else now.time() >= SETTLE


def fetch(codes, days=140):
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    for code in codes:
        try:
            df = fdr.DataReader(code, start)
        except Exception:
            continue
        if df is None or len(df) < 45:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df["vma20"] = df["Volume"].rolling(20).mean()
        df["ret1"] = df["Close"].pct_change()
        pc = df["Close"].shift()
        tr = (df["High"] - df["Low"]).combine((df["High"] - pc).abs(), max) \
                                     .combine((df["Low"] - pc).abs(), max)
        df["atr14"] = tr.rolling(14).mean()
        df["hh20"] = df["High"].rolling(20).max().shift(1)
        out[code] = df
    return out


def has_catalyst(code, today, cmap):
    """신호일 기준 과거 CATALYST_WINDOW_DAYS일 내 촉매공시가 있었나 (후보 종목만 조회)."""
    cc = cmap.get(code)
    if not cc:
        return False, "corp_code 없음"
    bgn = (today - pd.Timedelta(days=CATALYST_WINDOW_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        disc = get_disclosures(cc, bgn, end)
    except Exception as e:
        return False, f"조회실패({e.__class__.__name__})"
    hit = [nm for _, nm in disc if any(k in nm for k in CATALYST_KW)]
    return bool(hit), (hit[0] if hit else "촉매 없음")


def tstat(trades):
    """청산된 트레이드로 평균·표준편차·t·신뢰구간."""
    r = [t["ret_pct"] for t in trades]
    n = len(r)
    if n < 2:
        return None
    mean = sum(r) / n
    var = sum((x - mean) ** 2 for x in r) / (n - 1)
    sd = var ** 0.5
    se = sd / (n ** 0.5)
    return {"n": n, "mean": mean, "sd": sd, "se": se, "t": mean / se if se else 0,
            "lo": mean - 1.96 * se, "hi": mean + 1.96 * se}


def run(args):
    s = load()
    if not s["universe"]:
        s["universe"] = [[c, n] for c, n in get_universe()]
        print(f"[init] 유니버스 {len(s['universe'])}종목 스냅샷")
    name = {c: n for c, n in s["universe"]}
    codes = [c for c, _ in s["universe"]]

    if args.status:
        report(s, name); return

    print(f"[data] {len(codes)}종목 일봉 수집...")
    data = fetch(codes)
    if not data:
        print("데이터 없음"); return
    today = max(df.index[-1] for df in data.values())
    tstr = today.strftime("%Y-%m-%d")

    if not args.force and not bar_settled(today.date()):
        print(f"[wait] {tstr} 봉이 미확정(장중). {SETTLE.strftime('%H:%M')} 이후 실행 "
              "— 상태 변경 없음")
        return
    if s["last_date"] == tstr:
        print(f"[skip] {tstr} 이미 처리됨")
        report(s, name); return
    if s["start_date"] is None:
        s["start_date"] = tstr

    def val(code, col):
        df = data.get(code)
        if df is not None and today in df.index:
            v = df.at[today, col]
            return None if pd.isna(v) else float(v)
        return None

    # 1) 예약 → 오늘 시가 체결
    for code in s["pending"]:
        if code in s["positions"] or len(s["positions"]) >= MAX_POS:
            continue
        op = val(code, "Open")
        if op is None:
            continue
        fill = op * (1 + SLIP)
        shares = int(POS_KRW / fill) if fill > 0 else 0
        cost = shares * fill * (1 + FEE_BUY)
        if shares <= 0 or cost > s["cash"]:
            continue
        s["cash"] -= cost
        s["positions"][code] = {"shares": shares, "entry": fill, "peak": fill,
                                "days": 0, "date": tstr, "name": name.get(code, code)}
        print(f"  ▶ 매수(모의) {name.get(code, code)} {shares}주 @ {fill:,.0f}")
    s["pending"] = []

    # 2) 청산 판정
    for code in list(s["positions"].keys()):
        p = s["positions"][code]
        hi, cl, atr = val(code, "High"), val(code, "Close"), val(code, "atr14")
        if cl is None:
            continue
        if hi is not None:
            p["peak"] = max(p["peak"], hi)
        p["days"] += 1
        ret = cl / p["entry"] - 1
        reason = ("손절(-8%)" if ret <= HARD_STOP
                  else "트레일청산" if (atr and cl <= p["peak"] - CH_MULT * atr)
                  else "시간만료(15일)" if p["days"] >= MAX_HOLD else None)
        if reason:
            fill = cl * (1 - SLIP)
            proceeds = p["shares"] * fill * (1 - FEE_SELL)
            cost = p["shares"] * p["entry"] * (1 + FEE_BUY)
            s["cash"] += proceeds
            s["trades"].append({"date": tstr, "name": p["name"],
                                "ret_pct": round((proceeds / cost - 1) * 100, 2),
                                "reason": reason})
            print(f"  ◀ 매도(모의) {p['name']} {(proceeds/cost-1)*100:+.1f}% ({reason})")
            del s["positions"][code]

    # 3) 자산 평가
    mv = s["cash"]
    for code, p in s["positions"].items():
        cl = val(code, "Close")
        if cl:
            mv += p["shares"] * cl
    s["equity"].append([tstr, round(mv)])

    # 4) 신규 신호 스캔 → 촉매 확인 → 내일 예약
    if len(s["positions"]) < MAX_POS:
        cands = []
        for code, df in data.items():
            if code in s["positions"] or today not in df.index:
                continue
            r = df.loc[today]
            if pd.isna(r["vma20"]) or pd.isna(r["hh20"]) or r["vma20"] == 0:
                continue
            vr = float(r["Volume"] / r["vma20"])
            if vr >= VOL_SURGE and r["ret1"] >= UP_MIN and r["Close"] > r["hh20"]:
                cands.append((vr, code))
        cands.sort(reverse=True)
        if cands:
            print(f"  급등 신호 {len(cands)}종목 → 촉매공시 확인")
            cmap = get_corp_map()
            slots = MAX_POS - len(s["positions"])
            for vr, code in cands:
                if slots <= 0:
                    break
                ok, why = has_catalyst(code, today, cmap)
                mark = "✅" if ok else "❌"
                print(f"    {mark} {name.get(code, code)}({code}) 거래량 {vr:.1f}배 — {why}")
                if ok:
                    s["pending"].append(code)
                    slots -= 1
        else:
            print("  급등 신호 없음")

    s["last_date"] = tstr
    save(s)
    report(s, name)


def report(s, name):
    eq = s["equity"][-1][1] if s["equity"] else START_KRW
    peak, mdd = START_KRW, 0
    for _, v in s["equity"]:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    print("=" * 66)
    print(f"  B 포워드 페이퍼 (급등+공시촉매)   기준일 {s['last_date']}  "
          f"(시작 {s['start_date']})")
    print("=" * 66)
    print(f"  평가자산 {eq:,}원 ({(eq/START_KRW-1)*100:+.2f}%)   MDD {mdd*100:.1f}%")
    print(f"  보유 {len(s['positions'])}/{MAX_POS}:",
          ", ".join(p["name"] for p in s["positions"].values()) or "없음")
    if s["pending"]:
        print("  내일 시가 매수 예정:", ", ".join(name.get(c, c) for c in s["pending"]))

    st = tstat(s["trades"])
    print("-" * 66)
    if not st:
        print(f"  표본 {len(s['trades'])}건 — 통계 판정에 {TARGET_N}건 필요 "
              f"(백테스트 61건 + 앞으로 35건)")
    else:
        print(f"  [포워드 표본만] {st['n']}건  평균 {st['mean']:+.2f}%/트레이드  "
              f"표준편차 {st['sd']:.1f}%")
        print(f"    t = {st['t']:.2f}   95% CI {st['lo']:+.2f}% ~ {st['hi']:+.2f}%"
              f"   → {'0 포함(판정 불가)' if st['lo'] <= 0 <= st['hi'] else '0 미포함'}")
        print(f"    진행 {st['n']}/{TARGET_N - 61} (포워드 목표)")
    print("  ※ 백테스트 61건: 평균 +6.12%, t=1.57, CI −1.53%~+13.77% (0 포함=판정 불가)")
    print("=" * 66)
    print("  실주문 없음. 8개월 뒤 t가 1.96을 넘으면 그때 진짜인지 판단한다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="상태·통계만 조회")
    ap.add_argument("--force", action="store_true", help="미확정 봉이어도 강제 진행")
    run(ap.parse_args())
