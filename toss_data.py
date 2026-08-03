# -*- coding: utf-8 -*-
"""토스증권 Open API 어댑터 — 국내주식 일봉을 받아 기존 백테스트 스키마로 변환.

크립토(pyupbit)의 data.load_candles를 대체. 반환 형식은 동일:
  {symbol: {"m5": 일봉df, "m4h": 주봉df}}   ← 지표코드가 fast/slow 두 틀만 보므로 그대로 재사용
  (주식엔 5분/4시간 대신 '일봉=빠른틀 / 주봉=느린틀'을 매핑)

API (openapi.tossinvest.com):
  토큰   POST /oauth2/token   (form: grant_type=client_credentials, client_id, client_secret)
  캔들   GET  /api/v1/candles?symbol=005930&interval=1d&count=200&before=<ISO8601>&adjusted=true
  필드   timestamp / openPrice / highPrice / lowPrice / closePrice / volume
키는 .env(TOSS_CLIENT_ID/TOSS_CLIENT_SECRET) — gitignore됨. 채팅/커밋 금지.
"""
import os
import time
import json
import pickle
import urllib.parse
import urllib.request

import pandas as pd

BASE = "https://openapi.tossinvest.com"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    """.env에서 키 로드(있으면). 이미 환경변수에 있으면 그걸 우선."""
    cid = os.environ.get("TOSS_CLIENT_ID")
    sec = os.environ.get("TOSS_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    path = os.path.join(_HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return os.environ.get("TOSS_CLIENT_ID"), os.environ.get("TOSS_CLIENT_SECRET")


_token = {"value": None, "exp": 0.0}


def _get_token():
    """client_credentials 토큰 발급(+만료 60초 전까지 캐시)."""
    now = time.time()
    if _token["value"] and now < _token["exp"] - 60:
        return _token["value"]
    cid, sec = _load_env()
    if not cid or not sec:
        raise RuntimeError(
            "토스 API 키 없음 — .env에 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 넣어줘 "
            "(cp .env.example .env)")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid, "client_secret": sec,
    }).encode()
    req = urllib.request.Request(
        BASE + "/oauth2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    _token["value"] = j["access_token"]
    _token["exp"] = now + float(j.get("expires_in", 1800))
    return _token["value"]


def _get(path, params):
    token = _get_token()
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_candles(symbol, interval="1d", total=400):
    """count 최대 200 → before=로 과거 페이지네이션해 total개 확보."""
    frames = []
    before = None
    remaining = total
    while remaining > 0:
        n = min(200, remaining)
        params = {"symbol": symbol, "interval": interval, "count": n, "adjusted": "true"}
        if before:
            params["before"] = before
        j = _get("/api/v1/candles", params)
        rows = j.get("candles", j) if isinstance(j, dict) else j
        if not rows:
            break
        df = pd.DataFrame([{
            "time": pd.to_datetime(c["timestamp"]),
            "open": float(c["openPrice"]), "high": float(c["highPrice"]),
            "low": float(c["lowPrice"]), "close": float(c["closePrice"]),
            "volume": float(c["volume"]),
        } for c in rows]).set_index("time").sort_index()
        frames.append(df)
        before = df.index[0].isoformat()          # 다음 페이지 = 가장 오래된 것 이전
        remaining -= len(df)
        time.sleep(0.2)
        if len(df) < n:
            break
    if not frames:
        return None
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    out.index = out.index.tz_localize(None)        # 지표 슬라이싱 편하게 tz 제거
    return out


def _weekly(daily):
    """일봉 → 주봉 리샘플(주말 라벨). 지표의 '느린틀' 역할.
    라벨이 주말이라, 장중/주중 asof에선 진행중 주봉이 index>asof로 자동 제외 → look-ahead 없음."""
    w = daily.resample("W").agg({"open": "first", "high": "max", "low": "min",
                                 "close": "last", "volume": "sum"}).dropna()
    return w


def load_stocks(symbols, total=400, use_cache=True):
    """{symbol: {"m5": 일봉, "m4h": 주봉}} — 기존 백테스트 루프에 그대로 투입."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"kr_{len(symbols)}sym_{total}d.pkl")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            print(f"[toss] 캐시 사용: {cache_path}")
            return pickle.load(f)
    out = {}
    for i, s in enumerate(symbols):
        print(f"[toss] ({i+1}/{len(symbols)}) {s} 수집중...")
        d = fetch_candles(s, "1d", total)
        if d is None or len(d) < 150:
            print(f"[toss]   {s} 데이터 부족 → 제외")
            continue
        out[s] = {"m5": d, "m4h": _weekly(d)}
        time.sleep(0.2)
    with open(cache_path, "wb") as f:
        pickle.dump(out, f)
    print(f"[toss] 저장: {cache_path}  (종목 {len(out)}개)")
    return out


if __name__ == "__main__":
    # 키 있으면 삼성전자 5봉만 찍어보는 스모크 테스트
    df = fetch_candles("005930", "1d", 5)
    print(df)
