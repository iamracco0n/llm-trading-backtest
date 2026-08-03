# -*- coding: utf-8 -*-
"""소액 단발 단타 실행기 — 10만원으로 급등추격을 '한 번' 시도한다 (페이퍼, 실주문 없음).

⚠️ **이건 돈 버는 알고리즘이 아니다.** 이 레포의 결론은 급등추격에 재현 가능한 엣지가
없다는 것이다(RESULTS_KR.md Phase 1~3). `small_capital.py` 기준 10만원으로 +3만원에
먼저 닿을 확률은 41%, 반대로 −3만원에 먼저 닿을 확률이 59%다. 50거래를 굴리면 잔고
중앙값이 원금의 1/3(약 3.6만원)로 내려간다.

그래서 이 스크립트가 하는 일은 '이기는 것'이 아니라 **세 가지를 강제하는 것**이다:
  1. **규칙대로만** 산다 — 백테스트와 완전히 같은 신호/청산 조건. 감으로 사고파는 걸 막는다.
  2. **한 번만** 한다 — 시도가 끝나면 잠긴다. 재시작하려면 `--reset`을 명시적으로 쳐야 하고,
     그때마다 굴릴수록 나빠진다는 숫자를 다시 보여준다(41%는 '첫 시도' 확률이다).
  3. **확률을 매번 눈앞에 둔다** — 실행할 때마다 41:59를 출력한다.

규칙(= `surge_backtest.py`와 동일):
  신호  거래량 ≥ 20일평균×3  AND  당일 +6% 이상  AND  직전 20일 고점 돌파
  진입  신호 다음 거래일 **시가** (그 종가엔 못 사니까)
  청산  진입 대비 −8% 손절 / 최고가 −3×ATR 트레일 / 15거래일 만료

사용:
  python3 single_shot.py            오늘분 진행(장 마감 후)
  python3 single_shot.py --scan     신호만 조회(상태 변경 없음)
  python3 single_shot.py --status   현재 상태
  python3 single_shot.py --reset    새 시도 시작(경고 후)
"""
import os
import json
import argparse
import datetime as dt

import pandas as pd
import FinanceDataReader as fdr

from surge_backtest import (get_universe, VOL_SURGE, UP_MIN, CH_MULT, HARD_STOP,
                            MAX_HOLD, FEE_BUY, FEE_SELL)

STATE = os.path.join(os.path.dirname(__file__), "cache", "single_shot_state.json")
CAPITAL = 100_000
SLIP = 0.003          # 편도 슬리피지(백테스트 '보통' 가정). 소형주 현실은 이보다 나쁠 수 있다
SETTLE = dt.time(16, 0)   # 장중 미완성 봉으로 하루를 소진하지 않기 위한 가드

ODDS = ("확률 고지 — 10만원 기준 +3만 먼저 41.0% vs −3만 먼저 59.0% "
        "(슬리피지 0.5%면 39:61). 유리한 내기가 아니다.")


def _blank():
    return {"universe": [], "capital": CAPITAL, "position": None, "pending": None,
            "last_date": None, "done": False, "history": []}


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


def scan(data, today, name):
    """오늘 종가 기준 급등 신호 종목 → 거래량비 큰 순."""
    cands = []
    for code, df in data.items():
        if today not in df.index:
            continue
        r = df.loc[today]
        if pd.isna(r["vma20"]) or pd.isna(r["hh20"]) or r["vma20"] == 0:
            continue
        vr = float(r["Volume"] / r["vma20"])
        if vr >= VOL_SURGE and r["ret1"] >= UP_MIN and r["Close"] > r["hh20"]:
            cands.append((vr, code, name.get(code, code), float(r["Close"]),
                          float(r["ret1"]) * 100))
    cands.sort(reverse=True)
    return cands


def run(args):
    s = load()
    print(f"  ⚠ {ODDS}")

    if args.reset:
        if s["position"]:
            print("  보유 중인 포지션이 있다 — 청산 먼저. --reset 취소")
            return
        n = len([h for h in s["history"] if h.get("side") == "SELL"])
        print(f"\n  이미 {n}회 시도했다. 굴릴수록 나빠진다: 50거래 후 잔고 중앙값은 "
              f"원금의 1/3(3.6만원), 원금 이상 남을 확률 23%.")
        print("  그래도 새 시도를 시작한다 (자본 리셋).")
        s["capital"], s["position"], s["pending"], s["done"] = CAPITAL, None, None, False
        save(s)
        report(s)
        return

    if not s["universe"]:
        s["universe"] = [[c, n] for c, n in get_universe()]
        print(f"  [init] 유니버스 {len(s['universe'])}종목 스냅샷")
    name = {c: n for c, n in s["universe"]}
    codes = [c for c, _ in s["universe"]]

    if args.status:
        report(s); return

    print(f"  [data] {len(codes)}종목 일봉 수집...")
    data = fetch(codes)
    if not data:
        print("  데이터 없음"); return
    today = max(df.index[-1] for df in data.values())
    tstr = today.strftime("%Y-%m-%d")

    if not bar_settled(today.date()):
        print(f"  [wait] {tstr} 봉이 미확정(장중). {SETTLE.strftime('%H:%M')} 이후 실행 "
              "— 상태 변경 없음")
        return

    if args.scan:
        cands = scan(data, today, name)
        print(f"\n  [{tstr}] 급등 신호 {len(cands)}종목")
        for vr, code, nm, cl, ch in cands[:10]:
            print(f"    {nm}({code})  종가 {cl:,.0f}  당일 {ch:+.1f}%  거래량 {vr:.1f}배")
        if not cands:
            print("    없음 — 신호 없는 날이 대부분이다")
        return

    if s["done"]:
        print("\n  시도가 종료된 상태다. 새로 하려면 --reset (권장하지 않는다)")
        report(s); return
    if s["last_date"] == tstr:
        print(f"\n  [skip] {tstr} 이미 처리됨")
        report(s); return

    def val(code, col):
        df = data.get(code)
        if df is not None and today in df.index:
            v = df.at[today, col]
            return None if pd.isna(v) else float(v)
        return None

    # 1) 대기 → 오늘 시가 체결
    if s["pending"] and not s["position"]:
        code = s["pending"]
        op = val(code, "Open")
        if op:
            fill = op * (1 + SLIP)
            shares = int(s["capital"] / (fill * (1 + FEE_BUY)))
            if shares > 0:
                cost = shares * fill * (1 + FEE_BUY)
                s["capital"] -= cost
                s["position"] = {"code": code, "name": name.get(code, code), "shares": shares,
                                 "entry": fill, "peak": fill, "days": 0, "date": tstr}
                s["history"].append({"date": tstr, "side": "BUY", "name": name.get(code, code),
                                     "price": round(fill), "shares": shares})
                print(f"\n  ▶ 매수(모의) {name.get(code, code)} {shares}주 @ {fill:,.0f} "
                      f"= {cost:,.0f}원  (잔여현금 {s['capital']:,.0f})")
            else:
                print(f"\n  주가가 자본보다 비싸 1주도 못 산다 — 스킵")
        s["pending"] = None

    # 2) 청산 판정
    if s["position"]:
        p = s["position"]
        hi, cl, atr = val(p["code"], "High"), val(p["code"], "Close"), val(p["code"], "atr14")
        if cl:
            if hi:
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
                s["capital"] += proceeds
                pnl = proceeds - cost
                s["history"].append({"date": tstr, "side": "SELL", "name": p["name"],
                                     "price": round(fill), "ret_pct": round((proceeds/cost-1)*100, 2),
                                     "pnl": round(pnl), "reason": reason})
                print(f"\n  ◀ 매도(모의) {p['name']} @ {fill:,.0f}  {reason}  "
                      f"{(proceeds/cost-1)*100:+.1f}% ({pnl:+,.0f}원)")
                s["position"] = None
                s["done"] = True
                print("  → 시도 종료. 이게 이 스크립트가 강제하는 '한 번'이다.")

    # 3) 신규 신호 → 내일 대기 (보유 없고 시도 안 끝났을 때만)
    if not s["position"] and not s["done"] and not s["pending"]:
        cands = scan(data, today, name)
        if cands:
            vr, code, nm, cl, ch = cands[0]
            s["pending"] = code
            print(f"\n  신호 {len(cands)}종목 중 1위 선택: {nm}({code}) "
                  f"당일 {ch:+.1f}% 거래량 {vr:.1f}배 → 내일 시가 매수 예정")
        else:
            print(f"\n  [{tstr}] 신호 없음 — 대기")

    s["last_date"] = tstr
    save(s)
    report(s)


def report(s):
    pos = s["position"]
    equity = s["capital"] + (pos["shares"] * pos["entry"] if pos else 0)
    print()
    print("=" * 62)
    print(f"  단발 단타 (페이퍼)   기준일 {s['last_date']}")
    print("=" * 62)
    print(f"  현금 {s['capital']:,.0f}원   보유: "
          f"{pos['name'] + ' ' + str(pos['shares']) + '주' if pos else '없음'}")
    sells = [h for h in s["history"] if h.get("side") == "SELL"]
    if sells:
        tot = sum(h["pnl"] for h in sells)
        print(f"  누적 손익 {tot:+,}원  ({len(sells)}회 청산)")
        for h in sells[-3:]:
            print(f"    {h['date']} {h['name']} {h['ret_pct']:+.1f}% "
                  f"({h['pnl']:+,}원) {h['reason']}")
    if s["pending"]:
        nm = dict(s["universe"]).get(s["pending"], s["pending"])
        print(f"  내일 시가 매수 예정: {nm}({s['pending']})")
    if s["done"]:
        print("  상태: 시도 종료 (--reset으로만 재시작)")
    print("=" * 62)
    print("  실주문 없음 — 결정만 기록한다. 실전은 검증된 장투(forward_paper.py)가 먼저다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="신호만 조회(상태 변경 없음)")
    ap.add_argument("--status", action="store_true", help="상태만 조회")
    ap.add_argument("--reset", action="store_true", help="새 시도 시작")
    run(ap.parse_args())
