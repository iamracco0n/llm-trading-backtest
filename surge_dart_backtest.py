# -*- coding: utf-8 -*-
"""Phase 2 — 급등 모멘텀에 'DART 공시 촉매' 필터를 붙이면 엣지가 생기나?

Phase 1 결론: 순수 거래량 급증+급등 돌파는 슬리피지 넣으면 기댓값 ≈ 0(엣지 없음).
가설: "급등 + 그 며칠 안에 진짜 촉매공시(공급계약/실적/무상증자/최대주주변경 등)가 있던
       종목만" 사면 가짜 펌핑을 걸러 승률이 슬리피지를 이길 만큼 오르나?

같은 가격데이터(Phase1 캐시)로 두 전략을 나란히:
  A) 급등만 (Phase1 그대로)
  B) 급등 + 공시촉매(신호일 기준 5일 내 촉매공시 존재)
정직성 장치(다음날 시가 진입/슬리피지/거래세)는 동일.
"""
import argparse
import pandas as pd

from surge_backtest import (load_data, START_KRW, MAX_POS, POS_KRW,
                            VOL_SURGE, UP_MIN, CH_MULT, HARD_STOP, MAX_HOLD,
                            FEE_BUY, FEE_SELL)
from dart_data import build_catalyst_dates

CATALYST_WINDOW_DAYS = 5   # 신호일 기준 과거 N일 내 촉매공시면 인정


def _catalyst_ts(catalyst):
    """{code: set('YYYYMMDD')} → {code: sorted[Timestamp]}."""
    out = {}
    for code, ds in catalyst.items():
        out[code] = sorted(pd.to_datetime(list(ds), format="%Y%m%d"))
    return out


def simulate(data, slip, require_catalyst, cat_ts):
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))[40:]

    def has_catalyst(code, ts):
        arr = cat_ts.get(code)
        if not arr:
            return False
        lo = ts - pd.Timedelta(days=CATALYST_WINDOW_DAYS)
        return any(lo <= d <= ts for d in arr)

    def price_at(code, ts, col):
        df = data[code]["df"]
        if ts in df.index:
            v = df.at[ts, col]
            return None if pd.isna(v) else float(v)
        return None

    cash = START_KRW
    positions, pending, trades, equity = {}, [], [], []
    for i, ts in enumerate(cal):
        for code in pending:                       # 어제신호 → 오늘 시가 진입
            if code in positions or len(positions) >= MAX_POS:
                continue
            op = price_at(code, ts, "Open")
            if op is None:
                continue
            fill = op * (1 + slip)
            shares = int(POS_KRW / fill) if fill > 0 else 0
            if shares <= 0:
                continue
            cost = shares * fill * (1 + FEE_BUY)
            if cost > cash:
                continue
            cash -= cost
            positions[code] = {"shares": shares, "entry": fill, "peak": fill, "i0": i}
        pending = []

        for code in list(positions.keys()):        # 청산
            pos = positions[code]
            hi = price_at(code, ts, "High"); cl = price_at(code, ts, "Close")
            atr = price_at(code, ts, "atr14")
            if cl is None:
                continue
            if hi is not None:
                pos["peak"] = max(pos["peak"], hi)
            ret = cl / pos["entry"] - 1
            reason = ("손절" if ret <= HARD_STOP else
                      "트레일" if (atr and cl <= pos["peak"] - CH_MULT * atr) else
                      "시간" if i - pos["i0"] >= MAX_HOLD else None)
            if reason:
                fill = cl * (1 - slip)
                proceeds = pos["shares"] * fill * (1 - FEE_SELL)
                cost = pos["shares"] * pos["entry"] * (1 + FEE_BUY)
                cash += proceeds
                trades.append({"code": code, "name": data[code]["name"],
                               "ret_pct": (proceeds / cost - 1) * 100})
                del positions[code]

        mv = cash                                   # 마크
        for code, pos in positions.items():
            cl = price_at(code, ts, "Close")
            if cl:
                mv += pos["shares"] * cl
        equity.append((ts, mv))

        if len(positions) < MAX_POS:                # 신호 스캔
            cands = []
            for code, d in data.items():
                if code in positions:
                    continue
                df = d["df"]
                if ts not in df.index:
                    continue
                r = df.loc[ts]
                if pd.isna(r["vma20"]) or pd.isna(r["hh20"]) or r["vma20"] == 0:
                    continue
                if r["Volume"] / r["vma20"] >= VOL_SURGE and r["ret1"] >= UP_MIN \
                        and r["Close"] > r["hh20"]:
                    if require_catalyst and not has_catalyst(code, ts):
                        continue
                    cands.append((r["Volume"] / r["vma20"], code))
            cands.sort(reverse=True)
            slots = MAX_POS - len(positions) - len(pending)
            for _, code in cands[:max(0, slots)]:
                pending.append(code)

    end_v = equity[-1][1] if equity else START_KRW
    peak, mdd = START_KRW, 0
    for _, v in equity:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    wins = [t for t in trades if t["ret_pct"] > 0]
    avg = sum(t["ret_pct"] for t in trades) / len(trades) if trades else 0
    return {"ret": (end_v / START_KRW - 1) * 100, "mdd": mdd * 100,
            "n": len(trades), "win": 100 * len(wins) / len(trades) if trades else 0,
            "avg": avg, "cal": (cal[0], cal[-1]), "trades": trades, "equity": equity}


def run(slip=0.003):
    data = load_data()
    if not data:
        print("가격 데이터 없음 — 먼저 surge_backtest 캐시 필요"); return
    cal = sorted(set().union(*[set(d["df"].index) for d in data.values()]))
    bgn, end = cal[0].strftime("%Y%m%d"), cal[-1].strftime("%Y%m%d")
    print(f"[dart] 촉매공시 수집 {bgn}~{end} (유니버스 {len(data)}종목)")
    catalyst = build_catalyst_dates(list(data.keys()), bgn, end)
    cat_ts = _catalyst_ts(catalyst)

    a = simulate(data, slip, require_catalyst=False, cat_ts=cat_ts)
    b = simulate(data, slip, require_catalyst=True, cat_ts=cat_ts)
    print("=" * 68)
    print(f"  급등주 백테스트 — 공시촉매 필터 유무  (슬리피지 {slip*100:.1f}%/편도)")
    print(f"  {a['cal'][0].date()} ~ {a['cal'][1].date()},  촉매종목 {len(catalyst)}개")
    print("=" * 68)
    print("  전략                수익률%    MDD%   매매  승률%  평균손익%")
    print("-" * 68)
    for name, s in [("A) 급등만", a), ("B) 급등+공시촉매", b)]:
        print(f"  {name:<18} {s['ret']:>7.2f} {s['mdd']:>7.2f} {s['n']:>5} {s['win']:>6.1f} {s['avg']:>8.2f}")
    print("=" * 68)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=0.003)
    a = ap.parse_args()
    run(slip=a.slip)
