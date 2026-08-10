# -*- coding: utf-8 -*-
"""장투 전략이 '요즘 장'에서도 되나 — 최근 N개월만 잘라서 재현.

포워드 페이퍼(젯슨)는 2026-08-03 시작이라 5거래일치뿐이다. 그래서 백테스트로 최근
구간을 잰다. 규칙·비용은 `trend_backtest.py`와 동일하고 **기간만 자른다**.

⚠️ 짧은 구간의 한계를 먼저 적어둔다:
  - 2개월은 이 전략의 보유주기(수주~수개월)보다 짧다. **거래가 몇 건 안 나오고,
    그 몇 건이 결과를 지배한다.** 통계적 판정이 아니라 '요즘 죽지는 않았나' 점검이다.
  - 벤치마크(KOSPI) 대비로 봐야 한다. 지수가 오른 구간이면 전략도 오르는 게 당연하다.
  - 유니버스는 '오늘 기준 대형주'라 엄밀히는 룩어헤드다. 2개월 구간에선 편입/퇴출이
    거의 없어 영향이 작지만, 0은 아니다(전체 기간 검증은 `trend_pit_universe.py`).

사용: python3 trend_recent.py --months 2
"""
import argparse

import pandas as pd
import FinanceDataReader as fdr

from trend_backtest import (load_data, START_KRW, MAX_POS, POS_KRW, CH_MULT,
                            FEE_BUY, FEE_SELL, SLIP)
from trend_regime_backtest import load_regime


def run_window(data, since, slip=SLIP, regime=None):
    """trend_backtest.run()과 동일 로직. 지표 워밍업을 위해 신호 판정은 전 구간을
    돌리되, **매매와 자산곡선은 since 이후만** 집계한다."""
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))[125:]

    def px(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    cash = START_KRW
    positions, pending, trades, equity = {}, [], [], []
    risk_days = []
    for ts in cal:
        risk_on = True if regime is None else bool(regime.get(ts, False))
        if ts >= since:
            risk_days.append(risk_on)
        if ts < since:                      # 워밍업 구간: 신호만 계산하고 매매는 안 함
            pending = []
        for code in pending:
            if code in positions or len(positions) >= MAX_POS:
                continue
            op = px(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + slip)
            shares = int(POS_KRW / fill) if fill > 0 else 0
            if shares <= 0 or shares * fill * (1 + FEE_BUY) > cash:
                continue
            cash -= shares * fill * (1 + FEE_BUY)
            positions[code] = {"shares": shares, "entry": fill, "peak": fill,
                               "entry_ts": ts}
        pending = []

        for code in list(positions.keys()):
            pos = positions[code]
            hi, cl = px(code, ts, "High"), px(code, ts, "Close")
            atr, ma60 = px(code, ts, "atr14"), px(code, ts, "ma60")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            if ((ma60 and cl < ma60) or (atr and cl <= pos["peak"] - CH_MULT * atr)
                    or (regime is not None and not risk_on)):
                fill = cl * (1 - slip)
                proceeds = pos["shares"] * fill * (1 - FEE_SELL)
                cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
                cash += proceeds
                trades.append({"name": data[code]["name"],
                               "ret_pct": (proceeds / cost - 1) * 100,
                               "in": pos["entry_ts"].date(), "out": ts.date()})
                del positions[code]

        if ts >= since:
            mv = cash + sum(pos["shares"] * (px(c, ts, "Close") or 0)
                            for c, pos in positions.items())
            equity.append((ts, mv))

        if len(positions) < MAX_POS and risk_on:
            cands = []
            for code, d in data.items():
                if code in positions:
                    continue
                df = d["df"]
                if ts not in df.index:
                    continue
                r = df.loc[ts]
                if any(pd.isna(r[c]) for c in ("ma120", "ma120_prev", "hh60")):
                    continue
                if (r["Close"] > r["ma120"] and r["ma120"] > r["ma120_prev"]
                        and r["Close"] > r["hh60"]):
                    cands.append((r["Close"] / r["ma120"] - 1, code))
            cands.sort(reverse=True)
            slots = MAX_POS - len(positions) - len(pending)
            for _, code in cands[:max(0, slots)]:
                pending.append(code)

    return positions, trades, equity, risk_days


def summarize(tag, pos, trades, eq, bench, data, risk_days):
    end_v = eq[-1][1]
    peak, mdd = START_KRW, 0
    for _, v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    ret = (end_v / START_KRW - 1) * 100
    w = [t for t in trades if t["ret_pct"] > 0]
    print(f"\n  ── {tag} ──")
    print(f"    수익률 {ret:+.2f}%   MDD {mdd*100:.2f}%   "
          f"KOSPI 대비 {ret-bench:+.2f}%p")
    print(f"    청산 {len(trades)}건 | 보유 {len(pos)}종목 | "
          f"승률 {100*len(w)/len(trades):.0f}%" if trades
          else f"    청산 0건 | 보유 {len(pos)}종목")
    if risk_days:
        on = sum(risk_days)
        print(f"    risk_on 일수 {on}/{len(risk_days)}일 ({100*on/len(risk_days):.0f}%)")
    if trades:
        for t in sorted(trades, key=lambda x: -x["ret_pct"])[:12]:
            print(f"      {t['name'][:10]:<11} {t['in']}→{t['out']} {t['ret_pct']:+7.2f}%")
    for c, p in pos.items():
        cl = data[c]["df"]["Close"].iloc[-1]
        print(f"      [보유] {data[c]['name'][:10]:<11} {p['entry_ts'].date()} "
              f"{(cl/p['entry']-1)*100:+7.2f}%")
    return ret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=2)
    ap.add_argument("--fresh", action="store_true", help="시세 새로 받기")
    a = ap.parse_args()

    data = load_data(days=520, use_cache=not a.fresh)
    last = max(max(d["df"].index) for d in data.values())
    since = last - pd.DateOffset(months=a.months)
    ks = fdr.DataReader("KS11", since.strftime("%Y-%m-%d"))
    bench = (ks["Close"].iloc[-1] / ks["Close"].iloc[0] - 1) * 100

    regime = load_regime(start="2024-01-01")

    print("=" * 66)
    print(f"  장투 — 최근 {a.months}개월 ({since.date()} ~ {last.date()})  "
          f"KOSPI {bench:+.2f}%")
    print("=" * 66)

    r_off = summarize("국면 필터 없음(원본)",
                      *run_window(data, since)[:3], bench, data, None)
    p, t, e, rd = run_window(data, since, regime=regime)
    r_on = summarize("국면 필터 적용(KOSPI MA120)", p, t, e, bench, data, rd)

    print("\n" + "=" * 66)
    print(f"  국면 필터 효과: {r_off:+.2f}% → {r_on:+.2f}%  "
          f"({r_on-r_off:+.2f}%p)")
    print("=" * 66)
    print(f"  ⚠️ {a.months}개월은 보유주기보다 짧다. 통계 판정이 아니라 점검이다.")


if __name__ == "__main__":
    main()
