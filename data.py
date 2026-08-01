# -*- coding: utf-8 -*-
"""과거 캔들 수집 + 디스크 캐시. 두 봇이 완전히 동일한 데이터로 싸우게 한다."""
import os
import time
import pickle
import pyupbit
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


def _fetch_paginated(ticker, interval, total):
    """count>200 이면 to= 로 과거로 페이지네이션해서 이어붙인다."""
    frames = []
    to = None
    remaining = total
    while remaining > 0:
        n = min(200, remaining)
        df = pyupbit.get_ohlcv(ticker, interval=interval, count=n, to=to)
        if df is None or len(df) == 0:
            break
        frames.append(df)
        # 다음 페이지는 이번에 받은 가장 오래된 시각 이전으로
        to = df.index[0].strftime("%Y-%m-%d %H:%M:%S")
        remaining -= len(df)
        time.sleep(0.15)  # 레이트리밋 보호
        if len(df) < n:
            break
    if not frames:
        return None
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def load_candles(tickers, days, use_cache=True):
    """각 티커의 5분봉/4시간봉을 받아 {ticker: {"m5": df, "m4h": df}} 반환."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"candles_{days}d.pkl")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            print(f"[data] 캐시 사용: {cache_path}")
            return pickle.load(f)

    n5 = days * 288 + 100          # 5분봉: 하루 288개 + 워밍업 여유
    n4h = max(200, days * 6 + 60)  # 4시간봉: 하루 6개 + ma20 여유
    out = {}
    for i, t in enumerate(tickers):
        print(f"[data] ({i+1}/{len(tickers)}) {t} 수집중...")
        m5 = _fetch_paginated(t, "minute5", n5)
        time.sleep(0.15)
        m4h = _fetch_paginated(t, "minute240", n4h)
        if m5 is None or m4h is None or len(m5) < 100:
            print(f"[data]   {t} 데이터 부족 → 제외")
            continue
        out[t] = {"m5": m5, "m4h": m4h}
        time.sleep(0.2)

    with open(cache_path, "wb") as f:
        pickle.dump(out, f)
    print(f"[data] 저장: {cache_path}  (종목 {len(out)}개)")
    return out
