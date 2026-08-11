# -*- coding: utf-8 -*-
"""크립토 저변동성 롱숏 — 포워드 페이퍼 (젯슨 배포용).

**왜 배포하나.** 이 전략은 관문 다섯을 통과했다(펀딩비·숏가능성·겹침보정·평균=중앙값
·강제청산). 이 저장소에서 거기까지 온 것은 처음이다. 그런데 전부 **백테스트**다.
백테스트가 아무리 좋아도 실시간 기록이 없으면 확신할 수 없다는 것이 이 프로젝트의
결론이므로, 실주문 없이 기록만 쌓는다.

**규칙(백테스트와 동일하게 고정)**
  · 팩터: 저변동성 = −(20일 일수익률 표준편차). 한국에서 검증된 교과서 팩터.
  · 롱 = 팩터 상위 20, 숏 = 팩터 하위 20. 숏은 **무기한선물 상장분에서만** 고른다.
  · 거래가능 필터: 종가>0, 거래량>0, 20일 평균 거래대금 ≥ $1M, 20일 표준편차>0.
  · 보유 20일. **매일 새 코호트를 연다**(백테스트가 매일 진입하는 구조라 그대로).
    정상 상태에서 코호트 20개가 겹쳐 돌아간다.
  · **레버리지 1배 고정.** L=3이면 청산율 16.2%로 엣지가 부호까지 뒤집힌다.
  · 비용: 왕복 0.12%p, 펀딩비는 보유 중 매일 실제 요율로 누적.

**청산 판정**: 숏은 장중 고가가 진입가×1.995, 롱은 장중 저가가 진입가×0.005에
닿으면 청산(증거금 전액 손실). 무레버리지라 사실상 2배/제로 도달인데,
백테스트에서 실제로 2.65% 발생했다.

사용: python3 crypto_ls_paper.py          # 하루 1회 (cron)
      python3 crypto_ls_paper.py --report # 현황만 출력
"""
import os
import json
import time
import argparse
import datetime as dt
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cache", "ls_paper_state.json")
SPOT = "https://api.binance.com"
FAPI = "https://fapi.binance.com"

TOP_N = 20            # 각 다리 종목 수
HOLD_DAYS = 20        # 보유 기간
LEV = 1.0             # 레버리지 — 1배 고정(청산 실험 근거)
COST = 0.12           # 왕복 %p
CAP_PER_COHORT = 1_000_000 / HOLD_DAYS      # 코호트당 배분(정상상태 20개)
MIN_AMT = 1_000_000   # 20일 평균 거래대금 $1M

# 스테이블·페그 자산 배제 — **이름이 아니라 가격 특성으로 거른다.**
# 이름 목록으로 막으면 신규 스테이블이 나올 때마다 뚫린다(2026-08-11에 실제로
# 뚫렸다: XUSD·BFUSD·USDE가 검증구간 롱 바구니의 53~83%를 차지했다). 저변동성
# 팩터는 변동성이 0에 가까운 것을 무조건 1등으로 뽑는데, 스테이블은 수익도 0이라
# 알파가 아니라 사실상 '시장 숏'이 된다. 1달러 근처에 붙어 안 움직이는 것을 직접 본다.
# **최소 변동성 바닥.** "$1 근처인가"로 걸렀더니 유로 스테이블(EUR·EURI)이 통과했다.
# 이름이든 페그 통화든 쫓아다니는 대신, 근본 성질 하나로 막는다 —
# **일수익률 표준편차가 0.5% 미만이면 크립토에서 위험자산이 아니다.**
# 실측: 스테이블 ~0.02%, 유로 ~0.3%, 지루한 알트도 ~1.5%, BTC ~2~3%.
# 0.5%면 페그류만 깔끔히 잘리고 정상 자산은 안 걸린다. 새 스테이블이 나와도 자동으로
# 막힌다(이름 목록은 반드시 뚫린다 — 2026-08-11에 XUSD/BFUSD/USDE로 실제로 뚫렸다).
MIN_STD = 0.005


def is_pegged(close):
    """변동성이 없어 '저변동성 1등'을 공짜로 먹는 자산인가(스테이블·페그·랩드)."""
    return float(close.tail(20).pct_change().std()) < MIN_STD


# 토큰화 실물자산(금·주식). **크립토가 아니라서 검증 대상이 아니다** —
# 백테스트는 크립토 유니버스에서 돌았으므로 이걸 넣으면 검증한 것과 다른 전략을
# 관측하게 되고, 포워드의 존재 이유가 사라진다.
#
# ⚠️ 성질로 거르려 했으나 **실패했다.** BTC 상관 60일 실측:
#     XAUT 0.59 / QQQB 0.50  vs  TRX 0.55 / HBAR 0.52 / ASTER 0.26
#   토큰화 실물이 정상 크립토보다 오히려 상관이 높다. XAUT를 자르는 임계값은
#   TRX·HBAR도 같이 자른다. 변동성으로도 안 된다(1.4% vs 1.2%로 겹친다).
#   그래서 부득이 이름으로 막는다 — 뚫릴 것을 전제로 아래 감시 장치를 붙였다.
RWA = ("XAUT", "PAXG", "SPYB", "QQQB", "TSLAB", "NVDAB", "AAPLB", "MSTRB",
       "COINB", "METAB", "GOOGLB", "AMZNB")


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5 * (i + 1))


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"start": dt.date.today().isoformat(), "cohorts": [], "closed": [],
            "equity": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def perp_symbols():
    """무기한선물 USDT 상장 심볼 — 숏 가능 여부 판정용."""
    info = _get(f"{FAPI}/fapi/v1/exchangeInfo")
    if not info:
        return set()
    return {s["symbol"] for s in info["symbols"]
            if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"}


def universe():
    info = _get(f"{SPOT}/api/v3/exchangeInfo")
    if not info:
        return []
    return [s["symbol"] for s in info["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"]


def daily(sym, n=30):
    r = _get(f"{SPOT}/api/v3/klines?symbol={sym}&interval=1d&limit={n}")
    if not r or len(r) < 25:
        return None
    df = pd.DataFrame(r).iloc[:, :8]
    df.columns = ["t", "open", "high", "low", "close", "vol", "ct", "amt"]
    for c in ("open", "high", "low", "close", "vol", "amt"):
        df[c] = df[c].astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
    return df


def funding_now(sym):
    """직전 펀딩 요율(비율). 없으면 0."""
    r = _get(f"{FAPI}/fapi/v1/fundingRate?symbol={sym}&limit=3")
    if not r:
        return 0.0
    return float(np.sum([float(x["fundingRate"]) for x in r]))   # 하루치 ~3회


def build_baskets():
    """오늘의 롱/숏 바구니. 반환 (long[], short[], 가격맵, 진단)."""
    perp = perp_symbols()
    syms = universe()
    rows, px, n_peg, n_rwa = [], {}, 0, 0
    for i, s in enumerate(syms):
        d = daily(s)
        if d is None:
            continue
        c = d["close"]
        ret = c.pct_change()
        std20 = float(ret.tail(20).std())
        amt20 = float(d["amt"].tail(20).mean())
        if not (c.iloc[-1] > 0 and d["vol"].iloc[-1] > 0
                and amt20 >= MIN_AMT and std20 > 0):
            continue
        if is_pegged(c):                     # 스테이블·랩드달러 배제
            n_peg += 1
            continue
        if s[:-4] in RWA:                    # 토큰화 금·주식 배제
            n_rwa += 1
            continue
        rows.append({"sym": s, "fac": -std20, "shortable": s in perp})
        px[s] = float(c.iloc[-1])
        if (i + 1) % 100 == 0:
            print(f"  [uni] {i+1}/{len(syms)}", flush=True)
        time.sleep(0.02)
    df = pd.DataFrame(rows)
    if df.empty:
        return [], [], {}, "유니버스 없음"
    longs = df.nlargest(TOP_N, "fac")["sym"].tolist()
    shorts = df[df["shortable"]].nsmallest(TOP_N, "fac")["sym"].tolist()
    diag = (f"거래가능 {len(df)}개 / 숏가능 {int(df['shortable'].sum())}개 "
            f"/ 제외: 페그 {n_peg}, 실물토큰 {n_rwa}")
    return longs, shorts, px, diag


def mark_and_close(state, px):
    """보유 코호트 평가 + 20일 지난 코호트 청산. 청산(liquidation)도 판정."""
    today = dt.date.today()
    still, closed_now = [], []
    for co in state["cohorts"]:
        age = (today - dt.date.fromisoformat(co["date"])).days
        pnl, alive = [], True
        for side, names in (("long", co["long"]), ("short", co["short"])):
            for sym, ent in names.items():
                cur = px.get(sym)
                if cur is None:
                    continue
                raw = (cur / ent - 1) if side == "long" else (ent / cur - 1)
                liq = (cur >= ent * 1.995) if side == "short" else (cur <= ent * 0.005)
                pnl.append(-100.0 if liq else max(raw * LEV * 100, -100.0))
        co["mark"] = float(np.mean(pnl)) - COST if pnl else 0.0
        co["age"] = age
        if age >= HOLD_DAYS:
            co["closed"] = today.isoformat()
            co["ret"] = co["mark"]
            co["krw"] = CAP_PER_COHORT * co["ret"] / 100
            closed_now.append(co)
        else:
            still.append(co)
    state["cohorts"] = still
    state["closed"] += closed_now
    return closed_now


def cmd_run(args):
    state = load_state()
    print(f"===== 크립토 롱숏 포워드 페이퍼  {dt.date.today()} "
          f"(시작 {state['start']}) =====")

    longs, shorts, px, diag = build_baskets()
    if not longs or not shorts:
        print(f"  바구니 구성 실패: {diag}")
        return
    print(f"  {diag}")

    closed = mark_and_close(state, px)
    for co in closed:
        print(f"  ▣ 청산 코호트 {co['date']} → {co['ret']:+.2f}% "
              f"({co['krw']:+,.0f}원)")

    if not args.report:
        state["cohorts"].append({
            "date": dt.date.today().isoformat(),
            "long": {s: px[s] for s in longs if s in px},
            "short": {s: px[s] for s in shorts if s in px},
            "mark": 0.0, "age": 0,
        })
        print(f"  ▶ 신규 코호트: 롱 {len(longs)} / 숏 {len(shorts)}")
        # ⚠️ 전체를 찍는다. 스테이블 오염(2026-08-11)을 잡아낸 것은 통계가 아니라
        # 바구니를 눈으로 본 것이었다. 앞 10개만 찍으면 뒤에 낀 것을 못 본다.
        print(f"     롱  {', '.join(x.replace('USDT','') for x in longs)}")
        print(f"     숏  {', '.join(x.replace('USDT','') for x in shorts)}")

    live = sum(c["mark"] for c in state["cohorts"])
    real = sum(c["ret"] for c in state["closed"])
    n_liq = 0
    print(f"\n  보유 코호트 {len(state['cohorts'])}개 | 평가손익 {live:+.2f}%p")
    print(f"  청산 완료 {len(state['closed'])}개 | 실현 {real:+.2f}%p "
          f"({sum(c.get('krw', 0) for c in state['closed']):+,.0f}원)")
    if state["closed"]:
        r = [c["ret"] for c in state["closed"]]
        print(f"  중앙값 {np.median(r):+.2f}% | 승률 "
              f"{100*np.mean([x > 0 for x in r]):.0f}% | {len(r)}코호트")
        need = 20
        print(f"  ※ 판정에는 코호트 {need}개 이상 필요 — 현재 {len(r)}개")
    state["equity"].append([dt.date.today().isoformat(), round(live + real, 3)])
    if not args.report:
        save_state(state)
    print("  실주문 없음(페이퍼). 레버리지 1배 고정.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="상태만 보고 저장 안 함")
    cmd_run(ap.parse_args())
