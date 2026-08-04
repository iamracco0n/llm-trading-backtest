# -*- coding: utf-8 -*-
"""v6-크립토 — 한국에서 못 먹은 알파를 '숏이 되는 시장'에서 회수할 수 있나.

**왜 크립토인가.** 한국 실험의 최종 진단은 "엣지가 없다"가 아니라
**"엣지는 있는데 개인이 수확할 수단(공매도)이 없다"** 였다. 근거:

    저변동성 팩터 H+20   롱온리:  마이닝 +0.27 → 검증 −14.12 (붕괴)
                        롱숏  :  마이닝 +2.55 → 검증  +2.63 (재현, t=5.1→5.3)

같은 팩터가 롱온리에선 죽고 롱숏에선 살아난다. 차이는 시장 베타다 — 폭등장에서 상위
바구니가 지수를 못 따라갔지만 **하위 바구니는 더 못 따라갔다.** 하위를 팔 수 있으면
알파가 수확된다. 한국 개인은 개별종목 공매도가 불가하고, 인버스 ETF로는 안 된다
(우리 알파는 이미 지수를 뺀 값이라 시장 헤지로는 상위 바구니의 부진이 안 없어진다).

크립토를 먼저 보는 이유:
  1) **비용이 제일 싸다** — 거래세 0%, 수수료 0.02~0.04%. 한국은 거래세만 0.18%였고
     그 문턱 때문에 단타가 0/69로 죽었다.
  2) **미완의 실마리** — v4에서 "대박은 하락장 숏에서 나왔는데 업비트 현물이라 못 씀"으로
     끝났다. 숏이 되는 곳이면 그걸 회수할 수 있다.
  3) 크립토 트랙은 v1~v4에서 'LLM=판사'만 해봤고 **팩터 마이닝은 안 해봤다.**

**시장 간 이전(zero-shot) 검증을 같이 한다.** 한국에서 검증된 팩터를 손대지 않고 그대로
크립토에 넣어본다. 시장이 바뀌어도 부호·크기가 유지되면 그게 진짜 알파라는 제일 강한 증거다
(QuantaAlpha가 CSI300 팩터를 S&P500에 옮겨 검증한 방식).

⚠️ 정직하게: 크립토는 자산군 자체가 훨씬 위험하고, 저변동성 팩터가 여기서도 통한다는
보장은 없다(변동성 구조가 다르다). 실제 숏에는 펀딩비도 붙는다 — 아래 비용엔 미반영.

사용: python3 v6_crypto.py               (데이터 수집 + 시드 zero-shot 검증)
      python3 v6_crypto.py --expr "..."  (표현식 직접 평가)
"""
import os
import json
import time
import math
import pickle
import argparse
import urllib.request

import numpy as np
import pandas as pd

from v6_factor_lab import eval_factor, CACHE, TOP_N

PX = os.path.join(CACHE, "v6_crypto_prices.pkl")
BASE = "https://api.binance.com"

COST = 0.12          # 왕복 %p (taker 0.04×2 + 슬리피지) — 펀딩비 미반영
HORIZONS = [1, 3, 5, 20, 60]
SPLIT = {"mine": ("2022-01-01", "2024-12-31"),
         "valid": ("2025-01-01", "2026-08-31")}
N_UNIVERSE = 120

# ⚠️ 생존편향 + 룩어헤드 방어. '오늘 거래량 상위 120개'는 (a) 그사이 죽은 코인이 빠지고
# (b) 오늘 큰 코인을 과거에 아는 것이다. 바이낸스가 상장폐지 심볼의 과거 봉도 주므로
# (LUNA는 2024-10, UST는 2022-05-13 붕괴일에 끊김) 죽은 코인을 되살려 넣고,
# 유니버스는 '전체 USDT 페어'로 넓힌 뒤 시점별 유동성으로 거른다.
DEAD = ["LUNAUSDT", "USTUSDT", "SRMUSDT", "ANCUSDT", "MIRUSDT", "FTTUSDT", "WAVESUSDT",
        "CVCUSDT", "BTTUSDT", "TORNUSDT", "KEEPUSDT", "AIONUSDT", "MITHUSDT", "DREPUSDT",
        "PERLUSDT", "VITEUSDT", "NEBLUSDT", "RGTUSDT", "TRIBEUSDT", "BETAUSDT",
        "OOKIUSDT", "REEFUSDT", "SCUSDT", "STPTUSDT", "CTKUSDT", "MDXUSDT", "BONDUSDT",
        "IDEXUSDT", "GLMRUSDT", "KLAYUSDT", "MOBUSDT", "RENUSDT", "AGIXUSDT", "OCEANUSDT",
        "SNTUSDT", "UNFIUSDT", "AKROUSDT", "BADGERUSDT", "MDTUSDT", "ALPACAUSDT"]
STABLE = ("USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USDP", "EUR", "GBP", "AEUR", "USD1")


def _get(url, tries=3):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=30).read())
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def universe(full=False):
    """USDT 현물. full=True면 전체 페어(+상폐 코인)로 넓혀 생존편향·룩어헤드를 줄인다."""
    info = _get(f"{BASE}/api/v3/exchangeInfo")
    live = {s["symbol"] for s in info["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
            and not any(k in s["baseAsset"] for k in STABLE)
            and not any(k in s["symbol"] for k in ("UP", "DOWN", "BULL", "BEAR"))}
    if full:
        return sorted(live | set(DEAD))
    tick = _get(f"{BASE}/api/v3/ticker/24hr")
    rows = [(float(t["quoteVolume"]), t["symbol"]) for t in tick if t["symbol"] in live]
    rows.sort(reverse=True)
    return [s for _, s in rows[:N_UNIVERSE]]


def klines(sym, start_ms):
    out, cur = [], start_ms
    while True:
        r = _get(f"{BASE}/api/v3/klines?symbol={sym}&interval=1d&startTime={cur}&limit=1000")
        if not r:
            break
        out += r
        if len(r) < 1000:
            break
        cur = r[-1][0] + 86400000
        time.sleep(0.05)
    if not out:
        return None
    df = pd.DataFrame(out, columns=["ot", "Open", "High", "Low", "Close", "Volume",
                                    "ct", "qv", "n", "tb", "tq", "ig"])
    df.index = pd.to_datetime(df["ot"], unit="ms")
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def load_panel(refresh=False, full=False):
    global PX
    if full:
        PX = PX.replace(".pkl", "_full.pkl")
    if os.path.exists(PX) and not refresh:
        data = pickle.load(open(PX, "rb"))
        print(f"[panel] 캐시 사용 {len(data)}종목")
    else:
        syms = universe(full)
        print(f"[panel] 바이낸스 USDT 상위 {len(syms)}종목 수집...")
        start = int(pd.Timestamp("2021-11-01").timestamp() * 1000)
        data, fail = {}, 0
        for i, s in enumerate(syms):
            df = klines(s, start)
            if df is None or len(df) < 200:
                fail += 1
                continue
            data[s] = df
            if (i + 1) % 30 == 0:
                print(f"[panel]   {i+1}/{len(syms)} (수집 {len(data)}, 실패 {fail})", flush=True)
        pickle.dump(data, open(PX, "wb"))
        print(f"[panel] 저장 {len(data)}종목 (실패 {fail})")

    fields = ["Open", "High", "Low", "Close", "Volume"]
    panel = {f.lower(): pd.DataFrame({c: d[f] for c, d in data.items()}).sort_index()
             for f in fields}
    panel["vwap"] = (panel["high"] + panel["low"] + panel["close"]) / 3
    amt20 = (panel["close"] * panel["volume"]).rolling(20).mean()
    moved = panel["close"].rolling(20).std() > 0
    panel["_tradable"] = ((panel["close"] > 0) & (panel["volume"] > 0)
                          & (amt20 >= 1e6) & moved)          # 20일 평균 거래대금 $1M+
    print(f"[panel] 거래가능 종목/일 평균 {panel['_tradable'].sum(axis=1).mean():.0f}")
    return panel


_FA = {}


def forward_alpha(panel, h):
    """h일 후까지 수익 − 같은 구간 '시장'(유니버스 동일가중 평균) 수익.

    크립토엔 코스피 같은 대표지수가 없고 BTC를 쓰면 BTC 편향이 생긴다.
    거래가능 종목의 동일가중 평균을 시장으로 본다."""
    if h in _FA:
        return _FA[h]
    op, cl = panel["open"], panel["close"]
    entry, exit_ = op.shift(-1), cl.shift(-h)
    stock = exit_ / entry.where(entry > 0) - 1
    mkt = stock.where(panel["_tradable"]).mean(axis=1)        # 동일가중 시장
    out = stock.sub(mkt, axis=0) * 100
    _FA[h] = out.replace([np.inf, -np.inf], np.nan)
    return _FA[h]


def _ic(f, a):
    fr, ar = f.rank(axis=1), a.rank(axis=1)
    v = fr.notna() & ar.notna()
    fr, ar = fr.where(v), ar.where(v)
    fd = fr.sub(fr.mean(axis=1), axis=0)
    ad = ar.sub(ar.mean(axis=1), axis=0)
    den = np.sqrt((fd ** 2).sum(axis=1) * (ad ** 2).sum(axis=1))
    return ((fd * ad).sum(axis=1) / den.replace(0, np.nan)).where(v.sum(axis=1) >= 20)


def score(fac, panel, period):
    s, e = SPLIT[period]
    f_all = fac.where(panel["_tradable"].reindex(fac.index))
    m = (f_all.index >= s) & (f_all.index <= e)
    out = {}
    for h in HORIZONS:
        a = forward_alpha(panel, h).reindex(f_all.index)
        f, aa = f_all[m], a[m]
        both = f.notna() & aa.notna()
        f, aa = f.where(both), aa.where(both)
        ics = _ic(f, aa).dropna()
        hi = aa.where(f.rank(axis=1, ascending=False) <= TOP_N).median(axis=1)
        lo = aa.where(f.rank(axis=1, ascending=True) <= TOP_N).median(axis=1)
        sp = (hi - lo).dropna()
        hi = hi.dropna()
        if len(ics) < 20 or len(sp) < 20:
            continue
        out[h] = {
            "ic": float(ics.mean()),
            "t_ic": float(ics.mean()) / (float(ics.std()) + 1e-12) * math.sqrt(len(ics)),
            "long_net": float(hi.median()) - COST,
            "long_win": 100 * float((hi > 0).mean()),
            "ls": float(sp.median()), "ls_net": float(sp.median()) - 2 * COST,
            "ls_win": 100 * float((sp > 0).mean()),
            "t_ls": float(sp.mean()) / (float(sp.std()) + 1e-12) * math.sqrt(len(sp)),
        }
    return out


# 한국에서 검증된 팩터를 손대지 않고 그대로 — zero-shot 시장 이전 검증
SEEDS = [
    ("저변동성(한국 검증 팩터)", "-ts_std(ts_return(close,1),20)"),
    ("변동성조정 단기모멘텀(LLM 발굴)",
     "sub(ts_mean(ts_return(close,1),5),ts_std(ts_return(close,1),5))"),
    ("단기반전(5일)", "-ts_return(close,5)"),
    ("거래량급증(음)", "-div(volume,ts_mean(volume,20))"),
]


def report(name, expr, panel):
    print(f"\n  ▸ {name}   `{expr}`")
    fac = eval_factor(expr, panel)
    for period in ("mine", "valid"):
        sc = score(fac, panel, period)
        tag = "마이닝" if period == "mine" else "검증  "
        for h in HORIZONS:
            if h not in sc:
                continue
            r = sc[h]
            ok = "  ✅" if (r["ls_net"] > 0 and r["ls_win"] >= 50) else ""
            print(f"    {tag} H+{h:<3} IC {r['ic']:>+6.3f}(t{r['t_ic']:>+5.1f})  "
                  f"롱온리 {r['long_net']:>+6.2f}  롱숏 {r['ls']:>+6.2f}"
                  f"(t{r['t_ls']:>+5.1f},승{r['ls_win']:.0f}%) 비용후 {r['ls_net']:>+6.2f}{ok}")
        print()


def run(args):
    panel = load_panel(args.refresh, args.full)
    print(f"\n{'='*100}")
    print(f"  v6-크립토 — 한국 검증 팩터의 zero-shot 이전 + 롱숏 알파  (왕복비용 {COST}%p, 펀딩비 미반영)")
    print(f"  마이닝 {SPLIT['mine'][0]}~{SPLIT['mine'][1]}   검증 {SPLIT['valid'][0]}~{SPLIT['valid'][1]}")
    print("=" * 100)
    items = [(args.name or "사용자식", args.expr)] if args.expr else SEEDS
    for name, expr in items:
        try:
            report(name, expr, panel)
        except Exception as ex:
            print(f"    실패: {type(ex).__name__}: {ex}")
    print("=" * 100)
    print("  판정: 롱숏이 마이닝·검증 양쪽에서 비용후 + 이고 승률 ≥50%면 '시장 이전 성공'")
    print("=" * 100)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--full", action="store_true", help="전체 USDT 페어+상폐코인(생존편향 방어)")
    ap.add_argument("--expr")
    ap.add_argument("--name")
    run(ap.parse_args())
