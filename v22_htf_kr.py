# -*- coding: utf-8 -*-
"""v22 — 기각. **비용은 문제가 아니었다. 지수를 못 이기는 게 문제였다.**

━━━ 결과 (2022-01 ~ 2026-07, 150종목, 왕복비용 0.23%) ━━━
    누적 +12.7%  연율 +2.6%  MDD **−48.3%**  Sharpe 0.26
    거래 74건 | 거래당 평균 **+0.52%** 중앙값 −5.20% | 승률 34% | 평균보유 33일
    대조군 KOSPI 매수보유 **+120.7%**

  사전 기준  (a) 거래당 평균 > 0        +0.52%  **O**
             (b) 누적 > KOSPI 매수보유  +12.7% vs +120.7%  **X**
             (c) 거래 30건 이상         74건    **O**
             → 기각

━━━ ★ 내가 틀렸던 것 ━━━
"토스 API로 코인봇처럼 굴려보자"에 나는 v13(단타) 숫자로 반대했다 —
엣지 +0.176% < 비용 0.23%. 사용자가 **"1시간에 한 번 보는 거지 파는 게 아니다"**라고
지적했고 그 말이 맞았다. 나는 다른 질문에 답했다.

**비용 민감도가 그것을 증명한다** — 왕복비용을 0.10%(크립토 수준)에서 0.40%까지
네 배로 올려도 거래당 순수익은 **0.53% → 0.51%** 로 거의 안 움직인다.
평균 보유가 33일이라 회전이 적어 **비용은 애초에 이 전략의 문턱이 아니었다.**
v13의 문턱은 '매일 회전'이라는 조건에서만 유효했다.

━━━ 그런데 전략은 여전히 떨어진다. 이유가 다르다 ━━━
**그냥 KOSPI를 사는 것보다 훨씬 못하다**(+12.7% vs +120.7%). 낙폭은 더 크다(−48.3%).
구조를 보면 이유가 보인다 — 승률 34%, **중앙값 −5.20%**, 평균은 +0.52%.
코리아써키트 +189%, 대우건설 +103% 같은 소수의 대박이 다수의 손실을 겨우 덮는데,
슬롯이 3개뿐이라 150종목 중 3개에 몰빵하는 셈이라 분산이 없다. 게다가 국면필터가
off인 구간에 현금으로 앉아 있는 동안 지수는 올랐다.

즉 **"비용 때문에 안 된다"가 아니라 "이 설계로는 지수를 못 이긴다"**가 답이다.
실전에 올릴 이유가 없다 — 인덱스를 사는 게 낫고 낙폭도 절반이다.

━━━ 공정하게 덧붙일 것 ━━━
· 파라미터가 **크립토용으로 맞춰진 것**이다. 24봉 모멘텀이 1시간봉에선 하루인데
  일봉에선 5주가 된다. 시간 축이 안 맞으므로 이 이식은 문자 그대로일 뿐 최적이 아니다.
  다만 **같은 데이터로 다시 튜닝하면 과최적화**이므로 여기서 멈춘다.
· 이 기각이 "한국 추세추종이 안 된다"는 뜻은 아니다. `forward_paper.py`(장투)는
  다른 설계로 관문을 통과했고 지금 포워드 중이다. 죽은 것은 **코인봇 파라미터의
  직역**이다.
· 검증 구간이 KOSPI +120.7% 의 강세장이다. 강세장에서 현금 비중을 갖는 전략이
  지수에 지는 것은 어느 정도 당연하다 — 하지만 그것도 실전 판단에는 그대로 적용된다.

━━━ 이 결과를 내기까지 잡은 내 버그 둘 ━━━
첫 판 결과(누적 +44.3%)는 못 쓴다. 두 가지가 틀려 있었다:
  ① **비용을 자산곡선에 반영하지 않았다.** 거래 리스트에서만 뺐다. 그래서 비용을
     0.10~0.40% 로 바꿔도 누적이 44.3% 로 **한 자도 안 변했다** — 그 이상함이
     단서였다.
  ② **지수 캐시가 2024-05 부터**였다. 국면필터가 그 이전에 전부 False 가 되어
     2022~2024 가 통째로 거래 0 이었고, 매수보유 대조군도 다른 구간을 재고 있었다.
     구간이 다른 두 계열을 비교하면 아무 의미가 없다.

━━━ 이하 원래 설계 ━━━
**젯슨 코인봇 알고리즘을 한국 주식에 그대로 이식**하면 되는가.

━━━ 왜 이걸 하나 (내가 틀린 지점) ━━━
사용자가 "토스 API로 코인봇처럼 굴려보자"고 했을 때 나는 v13(단타)의 숫자를 들어
반대했다 — 엣지 +0.176% < 왕복비용 0.23%. **그런데 그건 다른 질문에 대한 답이었다.**

    v13     신호도 매일, **1일 보유**, 매일 회전   → 연 250회전
    코인봇  1시간마다 **보되**, 평균 38.8시간 보유  → 한 달 23거래(슬롯 3개)

"1시간에 한 번 보는 것"과 "1시간에 한 번 파는 것"은 다르고, 나는 후자를 쟀다.
회전수가 3배 가까이 차이나므로 비용 문턱도 전혀 다르다. 실제로 코인봇 실측은

    거래당 평균 +0.80%  vs  한국 왕복비용 0.23%  →  남는 것 +0.57%

로 **여전히 플러스**다. ATR 트레일링이 승자를 끝까지 들고 가(최고 +19.1%) 거래당
엣지가 두껍기 때문이다. v13의 +0.176%는 하루 만에 파는 규칙이라 얇았던 것이다.
그러므로 v13으로 이 설계를 기각할 수 없다. 재봐야 한다.

━━━ 이식 대상: 젯슨 `htf_indicators.py` / `htf_manager.py` 의 실제 파라미터 ━━━
    돈치안 20봉 상단 돌파  +  종가 > MA50        (진입 조건)
    24봉 모멘텀 순으로 후보 정렬, 슬롯 **3개**
    샹들리에 트레일링: **보유 중 최고가 − 3.0×ATR14** 이탈 시 청산
    국면 필터: 지수(코인봇은 BTC, 여기선 KOSPI) 일봉 > MA20 일 때만 신규 매수

**바꾼 것은 봉 주기 하나**다. 코인봇은 1시간봉인데 한국 주식 일중 데이터가
4.5년치가 없어 **일봉**으로 돌린다. 이건 코인봇보다 **불리한** 조건이다 —
트레일링 이탈을 하루 늦게 감지하고, 체결도 다음날 시가로 잡기 때문이다.
즉 여기서 나오는 수치는 **하한**에 가깝다.

━━━ 룩어헤드 방어 ━━━
· 신호는 t일 종가로 계산, 체결은 **t+1일 시가**. 청산도 동일(t일 종가에 트레일링
  이탈 확인 → t+1일 시가 매도). 코인봇의 장중 청산보다 보수적이다.
· 국면 필터도 t일 종가 기준 지수 MA20.

━━━ 사전 기준 (결과 보기 전에 고정) ━━━
셋 다 만족해야 "코인봇 방식은 한국 주식에서도 성립한다"가 된다:
  (a) **거래당 평균 순수익 > 0** — 비용 0.23% 를 반영하고도 남는가. 이것이
      사용자의 반론에 대한 직접적인 답이다.
  (b) 비용 반영 누적수익 > **KOSPI 매수보유**. 그냥 지수를 산 것보다 나아야 한다.
  (c) 거래 **30건 이상**. 표본이 없으면 (a)(b)는 우연이다.
하나라도 미달이면 기각하고, 부분 통과를 성공으로 포장하지 않는다.

━━━ 한계 (미리 적어둔다) ━━━
· 유니버스가 **현재 KOSPI 150종목**이라 상장폐지분이 빠진 **생존편향**이 남는다.
  추세추종은 하락 종목을 트레일링으로 자르므로 편향이 과대평가 쪽으로 작동한다.
· 슬리피지 0 가정. 시가 체결은 실제로 밀린다. 그래서 비용 민감도를 같이 낸다.
· 코인봇의 근거인 23거래는 그 자체로 표본이 작다. 여기서 통과해도 그것이
  코인봇의 성과를 사후 정당화해주지는 않는다.

사용: python3 v22_htf_kr.py
"""
import os
import pickle

import numpy as np
import pandas as pd

from v5_oos import CACHE

PX = os.path.join(CACHE, "trend_kospi_long.pkl")
IDX = os.path.join(CACHE, "v10_prices_long.pkl")

# 젯슨 배포본과 동일
DC_ENTRY = 20
ATR_N = 14
MA_TREND = 50
MOM_LOOKBACK = 24
REGIME_MA = 20
CHAND_MULT = 3.0
MAX_POSITION = 3

COST = 0.23          # 왕복 %, 2026년 실제(수수료 0.015×2 + 거래세 0.20)
COSTS = [0.10, 0.15, 0.18, 0.23, 0.30, 0.40]
CAP = 10_000_000


def indicators(df):
    d = df.copy()
    hi, lo, cl = d["High"], d["Low"], d["Close"]
    pc = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(ATR_N).mean()
    d["dc"] = hi.rolling(DC_ENTRY).max().shift(1)   # 직전 20봉 고가(당일 제외)
    d["ma"] = cl.rolling(MA_TREND).mean()
    d["mom"] = cl / cl.shift(MOM_LOOKBACK) - 1
    return d


def load():
    raw = pickle.load(open(PX, "rb"))
    data = {c: indicators(v["df"]) for c, v in raw.items() if len(v["df"]) > 200}
    names = {c: v["name"] for c, v in raw.items()}
    ks = _kospi()
    reg = (ks > ks.rolling(REGIME_MA).mean())
    return data, names, reg, ks


def _kospi():
    """KOSPI 종가 전 구간.

    ⚠️ 처음엔 `v10_prices_long.pkl` 의 _KS11 을 썼는데 그 캐시는 **2024-05 부터**다.
    국면필터가 그 이전 날짜에 전부 False 가 되어 **2022~2024 구간이 통째로
    거래 0** 이었고, 매수보유 대조군도 다른(짧고 늦은) 기간을 재고 있었다.
    두 계열의 구간이 다르면 비교 자체가 성립하지 않는다. 그래서 전 구간을 받는다."""
    c = os.path.join(CACHE, "v22_kospi.pkl")
    if os.path.exists(c):
        return pickle.load(open(c, "rb"))
    import FinanceDataReader as fdr
    ks = fdr.DataReader("KS11", "2021-06-01", "2026-08-31")["Close"]
    pickle.dump(ks, open(c, "wb"))
    return ks


def run(data, reg, cost, verbose=False):
    """t일 종가 신호 → t+1일 시가 체결. 반환 (자산곡선, 거래목록)."""
    cal = sorted(set().union(*[set(d.index) for d in data.values()]))
    cash, pos, eq, trades = float(CAP), {}, {}, []
    slot = CAP / MAX_POSITION

    for i, ts in enumerate(cal[:-1]):
        nxt = cal[i + 1]
        # ── 청산: t일 종가에 트레일링 이탈 확인 → t+1 시가 매도
        for code in list(pos):
            d = data[code]
            if ts not in d.index or nxt not in d.index:
                continue
            r = d.loc[ts]
            p = pos[code]
            p["peak"] = max(p["peak"], float(r["High"]))
            if np.isnan(r["atr"]):
                continue
            if float(r["Close"]) <= p["peak"] - CHAND_MULT * float(r["atr"]):
                px = float(d.loc[nxt, "Open"])
                if px <= 0:
                    continue
                gross = px / p["entry"] - 1
                net = gross * 100 - cost
                # ⚠️ 비용을 거래 리스트에만 빼고 현금에서 안 뺐다가, 비용을 바꿔도
                # 누적수익이 44.3% 로 똑같이 나왔다. 자산곡선에 반드시 반영한다.
                cash += p["qty"] * px * (1 - cost / 100.0)
                trades.append({"code": code, "entry": p["entry"], "exit": px,
                               "gross": gross * 100, "net": net,
                               "days": (nxt - p["date"]).days,
                               "in": str(p["date"].date()), "out": str(nxt.date())})
                del pos[code]

        # ── 진입: 국면 on + 돌파 + MA50 위, 모멘텀 상위
        on = bool(reg.get(ts, False))
        if on and len(pos) < MAX_POSITION:
            cands = []
            for code, d in data.items():
                if code in pos or ts not in d.index or nxt not in d.index:
                    continue
                r = d.loc[ts]
                if any(np.isnan(r[k]) for k in ("dc", "ma", "atr", "mom")):
                    continue
                c = float(r["Close"])
                if c > float(r["dc"]) and c > float(r["ma"]):
                    cands.append((float(r["mom"]), code))
            cands.sort(reverse=True)
            for _, code in cands:
                if len(pos) >= MAX_POSITION or cash < slot:
                    break
                px = float(data[code].loc[nxt, "Open"])
                if px <= 0:
                    continue
                qty = slot / px
                cash -= slot
                pos[code] = {"qty": qty, "entry": px, "peak": px, "date": nxt}

        mv = cash + sum(p["qty"] * float(data[c].loc[ts, "Close"])
                        for c, p in pos.items() if ts in data[c].index)
        eq[ts] = mv
    return pd.Series(eq).sort_index(), trades


def stats(eq, trades, cost):
    r = eq.pct_change().dropna()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0] - 1
    mdd = float((eq / eq.cummax() - 1).min()) * 100
    net = [t["net"] for t in trades]
    return {
        "tot": tot * 100, "cagr": ((1 + tot) ** (1 / yrs) - 1) * 100,
        "mdd": mdd, "n": len(trades),
        "avg": float(np.mean(net)) if net else 0.0,
        "med": float(np.median(net)) if net else 0.0,
        "wr": 100 * float(np.mean([x > 0 for x in net])) if net else 0.0,
        "hold": float(np.mean([t["days"] for t in trades])) if trades else 0.0,
        "sharpe": float(r.mean()) / (float(r.std()) + 1e-12) * np.sqrt(252),
    }


def main():
    print("[v22] 코인봇 알고리즘 → 한국 주식 이식 (일봉)")
    data, names, reg, ks = load()
    print(f"  유니버스 {len(data)}종목 | 국면필터 KOSPI > MA{REGIME_MA}")

    eq, tr = run(data, reg, COST)
    s = stats(eq, tr, COST)
    print(f"  구간 {eq.index[0].date()} ~ {eq.index[-1].date()}")

    # 대조군: KOSPI 매수보유
    ks = ks[(ks.index >= eq.index[0]) & (ks.index <= eq.index[-1])]
    bh = (ks.iloc[-1] / ks.iloc[0] - 1) * 100

    print(f"\n  ── 결과 (왕복비용 {COST}%) ──")
    print(f"  누적 {s['tot']:+.1f}%  연율 {s['cagr']:+.1f}%  MDD {s['mdd']:.1f}%  "
          f"Sharpe {s['sharpe']:.2f}")
    print(f"  거래 {s['n']}건 | 거래당 평균 {s['avg']:+.2f}% 중앙값 {s['med']:+.2f}% | "
          f"승률 {s['wr']:.0f}% | 평균보유 {s['hold']:.0f}일")
    print(f"  대조군 KOSPI 매수보유 {bh:+.1f}%")

    print(f"\n  ── 비용 민감도 (거래당 평균 순수익) ──")
    print(f"  {'왕복비용%':>10}{'누적%':>10}{'거래당%':>10}{'거래':>7}")
    for c in COSTS:
        e2, t2 = run(data, reg, c)
        s2 = stats(e2, t2, c)
        tag = "  ← 2026 한국" if abs(c - 0.23) < 1e-9 else ("  ← 크립토 수준" if c == 0.10 else "")
        print(f"  {c:>10.2f}{s2['tot']:>10.1f}{s2['avg']:>10.2f}{s2['n']:>7}{tag}")

    ok_a, ok_b, ok_c = s["avg"] > 0, s["tot"] > bh, s["n"] >= 30
    print(f"\n  ── 사전 기준 ──")
    print(f"  (a) 거래당 평균 > 0        {s['avg']:+.2f}%   {'O' if ok_a else 'X'}")
    print(f"  (b) 누적 > KOSPI 매수보유  {s['tot']:+.1f}% vs {bh:+.1f}%   {'O' if ok_b else 'X'}")
    print(f"  (c) 거래 30건 이상         {s['n']}건   {'O' if ok_c else 'X'}")
    print(f"  → {'★통과' if (ok_a and ok_b and ok_c) else '기각'}")

    if tr:
        print(f"\n  ── 상위/하위 거래 ──")
        for t in sorted(tr, key=lambda x: -x["net"])[:4]:
            print(f"   +{names.get(t['code'],t['code'])[:10]:<10} {t['net']:+7.2f}% "
                  f"({t['in']}~{t['out']}, {t['days']}일)")
        for t in sorted(tr, key=lambda x: x["net"])[:3]:
            print(f"   -{names.get(t['code'],t['code'])[:10]:<10} {t['net']:+7.2f}% "
                  f"({t['in']}~{t['out']}, {t['days']}일)")


if __name__ == "__main__":
    main()
