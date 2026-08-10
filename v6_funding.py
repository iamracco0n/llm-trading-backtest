# -*- coding: utf-8 -*-
"""v6-크립토 최종 관문 — 펀딩비와 '숏 가능 여부'를 넣어도 알파가 남나.

v6-크립토는 프로젝트 전체에서 **유일하게 "엣지가 있다"로 끝난 결과**다. 그런데 두 가지가
빠져 있었다(`v6_crypto.py` 27행에 "펀딩비 미반영"이라고 스스로 적어뒀다):

1. **펀딩비 미반영.** 현물 봉으로 롱숏 수익을 계산했다. 실제로 숏을 치려면 무기한선물이고,
   8시간마다 펀딩을 주고받는다. **5일 보유면 펀딩 이벤트가 15번**이다.
2. **숏 가능 여부 미검증.** 유니버스는 현물 USDT 페어 전체(421개, 죽은 코인 40개 포함)인데,
   **무기한선물이 없는 코인은 애초에 숏을 칠 수 없다.** 하위 바구니에 그런 코인이 섞여
   있었다면 그 알파는 종이 위에만 존재한다.

이 둘은 방향이 반대일 수 있다. 펀딩은 롱이 숏에게 주는 게 보통(상승장)이라 **숏 쪽엔
수입**이 될 수도 있고, 하락장에선 반대다. 재보기 전엔 모른다.

**부호 규약** (틀리면 결과가 통째로 뒤집히므로 명시한다):
  펀딩률 > 0  →  롱이 숏에게 지급.  즉 롱은 −rate, 숏은 +rate.
  LS 손익 = (롱 알파 − 롱 펀딩) − (숏 알파 − 숏 펀딩)

**사전 기준(결과 보기 전 고정)**: 펀딩비와 숏가능 필터를 둘 다 넣은 뒤에도
검증구간(2025-01~) 롱숏이 **양(+)이고 t≥2** 여야 "엣지가 실재한다"가 유지된다.

사용: python3 v6_funding.py fetch     # 펀딩 이력 수집(오래 걸림, 캐시됨)
      python3 v6_funding.py check     # 판정
"""
import os
import sys
import json
import time
import math
import pickle
import argparse
import urllib.request

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, CACHE, TOP_N
from v6_crypto import load_panel, forward_alpha, HORIZONS, SPLIT, COST, SEEDS

FAPI = "https://fapi.binance.com"
FUND = os.path.join(CACHE, "v6_funding.pkl")
PERP = os.path.join(CACHE, "v6_perp_info.pkl")


def _get(url, tries=4):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=30).read())
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(2 * (i + 1))


def fetch_perp_info():
    """무기한선물(USDT 마진) 상장 정보 — 심볼별 상장일(onboardDate)."""
    if os.path.exists(PERP):
        return pickle.load(open(PERP, "rb"))
    info = _get(f"{FAPI}/fapi/v1/exchangeInfo")
    out = {}
    for s in info["symbols"]:
        if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT":
            out[s["symbol"]] = int(s.get("onboardDate", 0))
    pickle.dump(out, open(PERP, "wb"))
    print(f"[perp] 무기한선물 USDT 페어 {len(out)}개")
    return out


def fetch_funding(symbols, start="2021-12-01"):
    """심볼별 펀딩 이력. 8시간마다 1건이라 4년치면 심볼당 ~4400건."""
    cache = pickle.load(open(FUND, "rb")) if os.path.exists(FUND) else {}
    t0 = int(pd.Timestamp(start).timestamp() * 1000)
    todo = [s for s in symbols if s not in cache]
    print(f"[fund] 수집 대상 {len(todo)}개 (캐시 {len(cache)})")
    for i, sym in enumerate(todo):
        rows, cur = [], t0
        while True:
            r = _get(f"{FAPI}/fapi/v1/fundingRate?symbol={sym}&startTime={cur}&limit=1000")
            if not r:
                break
            rows += r
            if len(r) < 1000:
                break
            cur = r[-1]["fundingTime"] + 1
            time.sleep(0.12)
        if rows:
            s = pd.Series({pd.to_datetime(x["fundingTime"], unit="ms"): float(x["fundingRate"])
                           for x in rows})
            cache[sym] = s.sort_index()
        else:
            cache[sym] = pd.Series(dtype=float)
        if (i + 1) % 25 == 0:
            print(f"[fund] {i+1}/{len(todo)}  {sym} {len(cache[sym])}건", flush=True)
            pickle.dump(cache, open(FUND, "wb"))
        time.sleep(0.08)
    pickle.dump(cache, open(FUND, "wb"))
    print(f"[fund] 완료 {len(cache)}개")
    return cache


def daily_funding(cache, index, columns):
    """일별 펀딩 합계(8시간×3회) 패널. 단위는 비율(0.0001 = 0.01%)."""
    cols = {}
    for sym in columns:
        s = cache.get(sym)
        if s is None or len(s) == 0:
            continue
        d = s.groupby(s.index.normalize()).sum()
        cols[sym] = d
    if not cols:
        return pd.DataFrame(index=index, columns=columns, dtype=float)
    df = pd.DataFrame(cols)
    df.index = pd.to_datetime(df.index)
    return df.reindex(index=index, columns=columns).fillna(0.0)


def cmd_fetch(args):
    panel = load_panel(full=True)
    syms = list(panel["close"].columns)
    perp = fetch_perp_info()
    have = [s for s in syms if s in perp]
    print(f"[perp] 현물 유니버스 {len(syms)}개 중 무기한선물 있는 것 {len(have)}개 "
          f"({100*len(have)/len(syms):.0f}%)")
    fetch_funding(have)


def _stats(x):
    x = x.dropna()
    if len(x) < 20:
        return None
    t = float(x.mean()) / (float(x.std()) + 1e-12) * math.sqrt(len(x))
    return len(x), float(x.median()), t, 100 * float((x > 0).mean())


def cmd_check(args):
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns

    # 숏 가능 = 무기한선물이 그 시점에 이미 상장돼 있음
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    trad = panel["_tradable"]
    print(f"  거래가능 종목/일 평균           {trad.sum(axis=1).mean():.0f}")
    print(f"  그중 숏까지 가능(무기한선물)     {(trad & onb).sum(axis=1).mean():.0f}"
          f"   ← 하위 바구니는 여기서만 뽑아야 한다")

    D = daily_funding(cache, idx, cols)
    C = D.cumsum()

    for name, expr in SEEDS:
        fac = eval_factor(expr, panel)
        if fac is None:
            continue
        print(f"\n  ▸ {name}   `{expr}`")
        for period in ("mine", "valid"):
            s, e = SPLIT[period]
            m = (idx >= s) & (idx <= e)
            line = f"    {period:<6}"
            for h in HORIZONS:
                a = forward_alpha(panel, h)
                fund = (C.shift(-h) - C) * 100          # 보유구간 펀딩 합계(%)

                f_long = fac.where(trad)                # 롱은 현물로도 되므로 필터 그대로
                f_shrt = fac.where(trad & onb)          # 숏은 무기한선물 있는 것만

                hi_r = f_long.rank(axis=1, ascending=False) <= TOP_N
                lo_r = f_shrt.rank(axis=1, ascending=True) <= TOP_N

                hi_raw = a.where(hi_r).median(axis=1)
                lo_raw = a.where(lo_r).median(axis=1)
                # 롱은 펀딩을 낸다(−), 숏은 받는다(+) → 숏바스켓 수익률에서 펀딩을 빼두면
                # LS = hi_adj − lo_adj 로 부호가 자동으로 맞는다
                hi_adj = (a - fund).where(hi_r).median(axis=1)
                lo_adj = (a - fund).where(lo_r).median(axis=1)

                raw = (hi_raw - lo_raw)[m].dropna() - 2 * COST
                adj = (hi_adj - lo_adj)[m].dropna() - 2 * COST
                r, d = _stats(raw), _stats(adj)
                if not r or not d:
                    line += f"  H{h}:  n/a "
                    continue
                line += f"  H{h}: {r[1]:+6.2f}→{d[1]:+6.2f}(t{d[2]:+4.1f})"
            print(line)

    print("\n  표기: 펀딩 미반영 → 펀딩·숏가능 반영(t값)")
    print("  사전 기준: valid 구간이 + 이고 t≥2 여야 '엣지 실재' 유지")




def cmd_deep(args):
    """왜 숫자가 너무 좋은가 — 겹침·평균/중앙값·꼬리를 판다.

    check 결과(저변동성 valid H+60 +22.98%, t=33.4)는 현실적이지 않다. 의심 세 가지:
      1) **겹치는 창** — 일별 관측 × h일 보유면 표본이 √h배 뻥튀기된다. t를 √h로 나눠야 한다.
      2) **중앙값이 숏을 미화한다** — 숏은 손실이 무한대다. 중앙값은 그 꼬리를 안 보여준다.
         평균이 중앙값보다 크게 낮으면 '평소 조금 벌고 가끔 크게 잃는' 구조다.
      3) **비중첩 표본** — h일마다 한 번만 뽑아 다시 재면 진짜 t가 나온다.
    """
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    trad = panel["_tradable"]
    D = daily_funding(cache, idx, cols)
    C = D.cumsum()

    name, expr = SEEDS[0]
    fac = eval_factor(expr, panel)
    print(f"\n  ▸ {name}  `{expr}`  — 검증구간 2025-01~\n")
    s, e = SPLIT["valid"]
    m = (idx >= s) & (idx <= e)
    print(f"  {'H':>4} {'표본':>6} {'중앙':>8} {'평균':>8} {'최악':>9} "
          f"{'t(겹침)':>9} {'t(비중첩)':>10} {'승률':>6}")
    print("  " + "-" * 68)
    for h in HORIZONS:
        a = forward_alpha(panel, h)
        fund = (C.shift(-h) - C) * 100
        hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
        lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N
        hi = (a - fund).where(hi_r).median(axis=1)
        lo = (a - fund).where(lo_r).median(axis=1)
        sp = (hi - lo)[m].dropna() - 2 * COST
        if len(sp) < 20:
            continue
        t_ov = sp.mean() / (sp.std() + 1e-12) * math.sqrt(len(sp))
        nonov = sp.iloc[::h]                       # h일마다 한 번 — 겹치지 않게
        t_no = (nonov.mean() / (nonov.std() + 1e-12) * math.sqrt(len(nonov))
                if len(nonov) >= 8 else float("nan"))
        print(f"  {h:>4} {len(sp):>6} {sp.median():>+8.2f} {sp.mean():>+8.2f} "
              f"{sp.min():>+9.2f} {t_ov:>+9.1f} {t_no:>+10.1f} "
              f"{100*(sp>0).mean():>5.0f}%")

    # 숏 다리만 따로 — 진짜 위험이 어디 있나
    print(f"\n  ── 숏 다리(하위 바구니) 단독 수익률, H+20 ──")
    h = 20
    a = forward_alpha(panel, h)
    fund = (C.shift(-h) - C) * 100
    lo_r = fac.where(trad & onb).rank(axis=1, ascending=True) <= TOP_N
    short_pnl = -((a - fund).where(lo_r))[m]        # 숏이므로 부호 반전
    flat = short_pnl.stack().dropna()
    print(f"    개별 포지션 {len(flat):,}건 | 중앙 {flat.median():+.2f}% | "
          f"평균 {flat.mean():+.2f}%")
    print(f"    최악 {flat.min():+.1f}%  |  −50% 이하 {100*(flat<-50).mean():.2f}%  "
          f"|  −100% 이하(원금초과) {100*(flat<-100).mean():.3f}%")
    q = flat.quantile([0.01, 0.05, 0.5, 0.95, 0.99])
    print(f"    분위: 1% {q[0.01]:+.1f} | 5% {q[0.05]:+.1f} | 50% {q[0.5]:+.1f} | "
          f"95% {q[0.95]:+.1f} | 99% {q[0.99]:+.1f}")

def cmd_decomp(args):
    """무엇이 얼마나 깎았나 — 숏가능 필터와 펀딩비를 따로 떼어 본다."""
    panel = load_panel(full=True)
    cache = pickle.load(open(FUND, "rb"))
    perp = fetch_perp_info()
    idx, cols = panel["close"].index, panel["close"].columns
    onb = pd.DataFrame(False, index=idx, columns=cols)
    for s in cols:
        if s in perp:
            onb[s] = idx >= pd.to_datetime(perp[s], unit="ms")
    trad = panel["_tradable"]
    C = daily_funding(cache, idx, cols).cumsum()
    fac = eval_factor(SEEDS[0][1], panel)
    print(f"\n  저변동성 롱숏 — 무엇이 얼마나 깎았나 (검증구간 2025-01~, 중앙값 %)\n")
    print(f"  {'구성':<30}{'H+5':>9}{'H+20':>9}{'H+60':>9}")
    print("  " + "-" * 57)
    for label, use_onb, use_fund in [("(1) 원본(둘 다 미반영)", False, False),
                                     ("(2) +숏가능 필터만", True, False),
                                     ("(3) +펀딩비만", False, True),
                                     ("(4) 둘 다(현실)", True, True)]:
        row = f"  {label:<30}"
        for h in (5, 20, 60):
            a = forward_alpha(panel, h)
            fund = (C.shift(-h) - C) * 100 if use_fund else 0
            lo_mask = (trad & onb) if use_onb else trad
            hi_r = fac.where(trad).rank(axis=1, ascending=False) <= TOP_N
            lo_r = fac.where(lo_mask).rank(axis=1, ascending=True) <= TOP_N
            hi = (a - fund).where(hi_r).median(axis=1)
            lo = (a - fund).where(lo_r).median(axis=1)
            s, e = SPLIT["valid"]
            sp = (hi - lo)[(idx >= s) & (idx <= e)].dropna() - 2 * COST
            row += f"{sp.median():>+9.2f}"
        print(row)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "check", "deep", "decomp"])
    a = ap.parse_args()
    {"fetch": cmd_fetch, "check": cmd_check, "deep": cmd_deep, "decomp": cmd_decomp}[a.cmd](a)
