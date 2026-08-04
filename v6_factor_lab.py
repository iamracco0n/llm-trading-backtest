# -*- coding: utf-8 -*-
"""v6 — LLM을 '판사'가 아니라 '팩터 가설 생성기'로 쓴다. 그 1단계: 팩터 평가 엔진.

**왜 패러다임을 바꾸나.** v1~v5에서 LLM은 텍스트를 읽고 매수/등급을 판정하는 *판사*였다.
그 역할의 천장을 실측했다 — 우리 로컬 30b가 +1.6%p, StockBench 기준 GPT-5·Claude-4도
최고 +2.5%p. base가 −2%인 판에서는 못 넘는다.

QuantaAlpha 계열은 LLM에게 **가격·거래량 위의 알파 팩터 수식을 생성**시키고 채점은
백테스트가 한다(CSI300에서 캔 팩터가 CSI500·S&P500로 zero-shot 이전됐다고 보고).
LLM이 판단하지 않고 **가설만 내놓으며, 검증은 통계가 한다** — 역할이 다르다.

**하지만 팩터 마이닝은 본질적으로 초대형 다중검정이다.** 오늘 140칸 스캔으로 t=4.32짜리
유령(자사주)을 만들어놓고 홀드아웃에서 t=0.22로 무너지는 걸 봤다. 수백 개 팩터를 캐면
그 함정이 수백 배가 된다. 그래서 이 랩은 **방어를 먼저 깔고** 시작한다:

  - 상장폐지 종목 포함(생존편향)          - 거래비용 차감 후 롱온리 수익까지 평가
  - 마이닝/검증 구간 분리 + 최종 봉인      - 생성 팩터 수를 기록해 다중검정 보정
  - **공매도 불가**(개인 국내주식) → 롱온리 성과가 진짜 기준. IC만 좋은 건 못 씀
  - 단타(H+1~5)와 중장기(H+20/60)를 같은 잣대로 동시 평가

**이 파일(1단계)은 LLM을 쓰지 않는다.** 엔진이 맞는지부터 확인한다 — 알려진 팩터
(단기 반전·중기 모멘텀)를 넣어 부호가 문헌대로 나오면 엔진을 신뢰하고, 아니면 엔진이 틀린 것.
'실적공시 대조군이 음(−)이어야 스캐너가 맞다'와 같은 원리다.

사용: python3 v6_factor_lab.py --market kospi          (시드 팩터로 엔진 검증)
      python3 v6_factor_lab.py --market kospi --expr "-ts_return(close,5)"
"""
import os
import re
import math
import pickle
import argparse
import warnings
import statistics as st

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

HORIZONS = [1, 3, 5, 20, 60]          # 단타(1~5) + 중장기(20/60)
TOP_N = 10                            # 롱온리 포트폴리오 종목 수
MIN_AMOUNT = 1e8                      # 거래 가능 최소 20일 평균 거래대금(1억원)
COST = {"kospi": 0.41, "kosdaq": 0.81}   # 왕복 %p (수수료+거래세+슬리피지)
INDEX = {"kospi": "KS11", "kosdaq": "KQ11"}

# 마이닝/검증 구간 — 최종 확인용 구간은 따로 봉인한다
SPLIT = {"mine": ("2022-01-01", "2024-12-31"),
         "valid": ("2025-01-01", "2026-08-03")}


# ───────────────────────── 데이터 ─────────────────────────

def load_panel(market):
    """{field: DataFrame(date × code)} — 상폐 종목 포함."""
    data = {}
    if market == "kospi":
        base = pickle.load(open(os.path.join(CACHE, "trend_kospi_long.pkl"), "rb"))
        for c, r in base.items():
            data[c] = r["df"]
        mk = "KOSPI"
    else:
        from surge_backtest import load_data
        for c, r in load_data().items():
            data[c] = r["df"]
        hp = os.path.join(CACHE, "holdout_prices_kosdaq.pkl")
        if os.path.exists(hp):          # 2022~2024 구간 보강
            for c, r in pickle.load(open(hp, "rb")).items():
                data[c] = pd.concat([r["df"], data[c]]).sort_index() \
                    .loc[lambda d: ~d.index.duplicated()] if c in data else r["df"]
        mk = "KOSDAQ"
    n_live = len(data)
    dl = os.path.join(CACHE, "delisted_prices.pkl")
    if os.path.exists(dl):
        for c, r in pickle.load(open(dl, "rb")).items():
            if r["market"] == mk and c not in data:
                data[c] = r["df"]
    print(f"[panel] {market}: 현재상장 {n_live} + 상폐 {len(data)-n_live} = {len(data)}종목")

    fields = ["Open", "High", "Low", "Close", "Volume"]  # _tradable은 뒤에서 추가
    panel = {f.lower(): pd.DataFrame({c: df[f] for c, df in data.items()}).sort_index()
             for f in fields}
    panel["vwap"] = (panel["high"] + panel["low"] + panel["close"]) / 3

    # ⚠️ 상폐 종목을 넣어 생존편향은 줄였지만, 그 대가로 '거래 불가능한 죽은 종목'이
    # 팩터 상위를 차지하는 새 오염이 생긴다. 실제로 -ts_std(...) 팩터가 가격이 안 움직이는
    # 정지 종목을 전부 골라 롱온리 수익이 +inf, 승률 89%로 나왔다(알파가 아니라 버그).
    # 그날 실제로 살 수 있었던 종목만 남긴다 — 이건 현실 제약이기도 하다.
    amt20 = (panel["close"] * panel["volume"]).rolling(20).mean()
    moved = panel["close"].rolling(20).std() > 0            # 거래정지/정리매매 배제
    panel["_tradable"] = ((panel["close"] > 0) & (panel["volume"] > 0)
                          & (amt20 >= MIN_AMOUNT) & moved)
    print(f"[panel] 거래가능 종목/일 평균 {panel['_tradable'].sum(axis=1).mean():.0f}")
    return panel


# ───────────────────── 팩터 표현식 DSL ─────────────────────
# 안전한 화이트리스트 평가. LLM이 뱉는 건 이 함수들의 조합만 허용한다.

def _ts(f):
    return lambda x, d: getattr(x.rolling(int(d)), f)()


DSL = {
    "ts_mean": _ts("mean"), "ts_std": _ts("std"), "ts_max": _ts("max"),
    "ts_min": _ts("min"), "ts_sum": _ts("sum"),
    "delay": lambda x, d: x.shift(int(d)),
    "delta": lambda x, d: x - x.shift(int(d)),
    "ts_return": lambda x, d: x / x.shift(int(d)) - 1,
    "ts_rank": lambda x, d: x.rolling(int(d)).rank(pct=True),
    "ts_argmax": lambda x, d: x.rolling(int(d)).apply(np.argmax, raw=True),
    "corr": lambda x, y, d: x.rolling(int(d)).corr(y),
    "rank": lambda x: x.rank(axis=1, pct=True),          # 횡단면 순위
    "zscore": lambda x: x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1) + 1e-12, axis=0),
    "log": lambda x: np.log(x.clip(lower=1e-9)),
    "abs": lambda x: x.abs(), "sign": lambda x: np.sign(x),
    "sqrt": lambda x: np.sqrt(x.clip(lower=0)),
    "mul": lambda x, y: x * y, "div": lambda x, y: x / (y.replace(0, np.nan) if hasattr(y, "replace") else y),
    "add": lambda x, y: x + y, "sub": lambda x, y: x - y,
}
ALLOWED = set(DSL) | {"open", "high", "low", "close", "volume", "vwap"}


def eval_factor(expr, panel):
    """화이트리스트 밖의 이름이 있으면 거부(임의 코드 실행 방지)."""
    for name in set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr)):
        if name not in ALLOWED:
            raise ValueError(f"허용되지 않은 이름: {name}")
    env = dict(DSL)
    env.update({k: v for k, v in panel.items() if not k.startswith("_")})
    return eval(expr, {"__builtins__": {}}, env)          # noqa: S307 (화이트리스트 검증됨)


# ───────────────────────── 평가 ─────────────────────────

_FA_CACHE = {}


def forward_alpha(panel, market, h):
    """h일 후 종가까지의 수익 − 같은 구간 지수 수익 (다음날 시가 진입).

    팩터와 무관하므로 (market, h)당 한 번만 계산해 재사용한다 — 팩터를 수백 개 캐는
    마이닝에서 이걸 매번 다시 계산하면 그게 병목이다."""
    key = (market, h, id(panel))
    if key in _FA_CACHE:
        return _FA_CACHE[key]
    op, cl = panel["open"], panel["close"]
    entry = op.shift(-1)                       # 신호일 다음날 시가
    exit_ = cl.shift(-h)
    idx = fdr.DataReader(INDEX[market], "2021-06-01")
    idx.index = pd.to_datetime(idx.index).tz_localize(None)
    io, ic = idx["Open"].reindex(op.index), idx["Close"].reindex(cl.index)
    m_in, m_out = io.shift(-1), ic.shift(-h)
    stock = (exit_ / entry.where(entry > 0) - 1)
    out = stock.sub(m_out / m_in - 1, axis=0) * 100
    out = out.replace([np.inf, -np.inf], np.nan)
    _FA_CACHE[key] = out
    return out


def _rowwise_ic(f, a):
    """일자별 스피어만 IC를 벡터화로. (scipy 불필요 — 순위끼리의 피어슨)"""
    fr, ar = f.rank(axis=1), a.rank(axis=1)
    valid = fr.notna() & ar.notna()
    fr, ar = fr.where(valid), ar.where(valid)
    n = valid.sum(axis=1)
    fm, am = fr.mean(axis=1), ar.mean(axis=1)
    fd, ad = fr.sub(fm, axis=0), ar.sub(am, axis=0)
    cov = (fd * ad).sum(axis=1)
    den = np.sqrt((fd ** 2).sum(axis=1) * (ad ** 2).sum(axis=1))
    ic = cov / den.replace(0, np.nan)
    return ic.where(n >= 20)


def score(fac, panel, market, period, log=True):
    """IC(횡단면) + 롱온리 상위N 성과(비용 차감). 전부 벡터화."""
    s, e = SPLIT[period]
    trad = panel["_tradable"].reindex(fac.index)
    f_all = fac.where(trad)
    m = (f_all.index >= s) & (f_all.index <= e)
    out = {}
    for h in HORIZONS:
        a = forward_alpha(panel, market, h).reindex(f_all.index)
        f, aa = f_all[m], a[m]
        both = f.notna() & aa.notna()
        f, aa = f.where(both), aa.where(both)
        ic_s = _rowwise_ic(f, aa).dropna()
        if len(ic_s) < 20:
            continue
        sel = f.rank(axis=1, ascending=False) <= TOP_N
        longs = aa.where(sel).median(axis=1).dropna()
        if len(longs) < 20:
            continue
        ic = float(ic_s.mean())
        t_ic = ic / (float(ic_s.std()) + 1e-12) * math.sqrt(len(ic_s))
        lo = float(longs.median())
        out[h] = {"n_days": int(len(ic_s)), "ic": ic, "t_ic": t_ic,
                  "long_med": lo, "long_net": lo - COST[market],
                  "win": 100 * float((longs > 0).mean()),
                  "t_long": float(longs.mean()) / (float(longs.std()) + 1e-12) * math.sqrt(len(longs))}
    if log:
        for h, r in out.items():
            flag = "  ✅" if r["long_net"] > 0 and r["win"] >= 50 else ""
            print(f"    H+{h:<3} IC {r['ic']:>+7.4f} (t={r['t_ic']:>+5.2f})   "
                  f"롱온리 중앙 {r['long_med']:>+6.2f}  비용후 {r['long_net']:>+6.2f}  "
                  f"승률 {r['win']:>4.1f}%{flag}")
    return out


# 엔진 검증용 시드 팩터 — 문헌상 부호가 알려진 것들
SEEDS = [
    ("단기반전(5일)", "-ts_return(close,5)"),
    ("중기모멘텀(60일)", "ts_return(close,60)"),
    ("거래량급증", "div(volume, ts_mean(volume,20))"),
    ("변동성(20일, 저변동성 프리미엄)", "-ts_std(ts_return(close,1),20)"),
]


def run(args):
    panel = load_panel(args.market)
    exprs = [(args.name or "사용자식", args.expr)] if args.expr else SEEDS
    print(f"\n{'='*84}\n  v6 팩터 랩 — {args.market.upper()}  "
          f"[마이닝 {SPLIT['mine'][0]}~{SPLIT['mine'][1]}]\n{'='*84}")
    print("  ※ 엔진 검증: 단기반전(+)·중기모멘텀 부호가 문헌과 맞아야 엔진을 신뢰한다")
    print(f"  ※ 롱온리 상위{TOP_N}종목 중앙 알파 − 왕복비용 {COST[args.market]}%p 가 진짜 기준")
    for name, expr in exprs:
        print(f"\n  ▸ {name}   `{expr}`")
        try:
            fac = eval_factor(expr, panel)
            score(fac, panel, args.market, "mine")
        except Exception as ex:
            print(f"    실패: {type(ex).__name__}: {ex}")
    print(f"\n{'='*84}")
    print("  다음 단계: LLM이 이 DSL로 팩터를 생성 → 마이닝 구간 채점 → 상위만 검증 구간으로")
    print("  (생성 개수를 기록해 다중검정 보정. 검증 구간은 그때까지 손대지 않는다)")
    print("=" * 84)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["kospi", "kosdaq"], default="kospi")
    ap.add_argument("--expr", help="직접 평가할 팩터 표현식")
    ap.add_argument("--name", help="표현식 이름")
    run(ap.parse_args())
