# -*- coding: utf-8 -*-
"""DART 공시 데이터 레이어 — 급등 신호에 '진짜 촉매' 필터를 붙이기 위한 것.

- get_corp_map(): 종목코드(6자리) → DART 고유번호(corp_code) 매핑 (corpCode.xml, 캐시)
- get_disclosures(corp_code, bgn, end): 기간 내 공시 목록 (list.json, 페이지네이션)
- build_catalyst_dates(stock_codes, bgn, end): {종목코드: {촉매공시 있었던 날짜(date) 집합}}

촉매 = 급등을 정당화할 만한 공시(공급계약/수주/실적/무상증자/최대주주변경/자사주/특허·임상 등).
키는 .env(DART_API_KEY). 읽기전용 공시조회 — 주문권한 없음.
"""
import os
import io
import time
import json
import zipfile
import pickle
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
_HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://opendart.fss.or.kr/api"

# 급등 촉매로 볼 공시 키워드(report_nm 부분일치)
CATALYST_KW = ["공급계약", "수주", "실적", "매출액또는손익", "무상증자",
               "최대주주", "자기주식취득", "타법인", "특허", "임상", "품목허가",
               "신규시설투자", "유상증자"]


def _key():
    k = os.environ.get("DART_API_KEY")
    if k:
        return k
    path = os.path.join(_HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("DART_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("DART_API_KEY 없음 — .env에 넣어줘")


def get_corp_map(use_cache=True):
    """{stock_code(6자리): corp_code(8자리)}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = os.path.join(CACHE_DIR, "dart_corpmap.pkl")
    if use_cache and os.path.exists(cp):
        with open(cp, "rb") as f:
            return pickle.load(f)
    url = f"{BASE}/corpCode.xml?crtfc_key={_key()}"
    with urllib.request.urlopen(url, timeout=30) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    xml = z.read(z.namelist()[0])
    root = ET.fromstring(xml)
    m = {}
    for e in root.iter("list"):
        sc = (e.findtext("stock_code") or "").strip()
        cc = (e.findtext("corp_code") or "").strip()
        if sc and cc:
            m[sc] = cc
    with open(cp, "wb") as f:
        pickle.dump(m, f)
    print(f"[dart] corp_map {len(m)}개 상장사")
    return m


def get_disclosures(corp_code, bgn, end):
    """corp_code의 [bgn,end] 공시 목록 → [(rcept_dt 'YYYYMMDD', report_nm), ...]."""
    out = []
    page = 1
    while True:
        p = urllib.parse.urlencode({
            "crtfc_key": _key(), "corp_code": corp_code,
            "bgn_de": bgn, "end_de": end,
            "page_no": page, "page_count": 100})
        with urllib.request.urlopen(f"{BASE}/list.json?" + p, timeout=15) as r:
            j = json.loads(r.read())
        if j.get("status") != "000":
            break
        for it in j.get("list", []):
            out.append((it["rcept_dt"], it["report_nm"]))
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.05)
    return out


def get_catalyst_events(corp_code, bgn, end):
    """촉매 공시만 [(rcept_dt, rcept_no, report_nm), ...] (본문 판정용 rcept_no 포함)."""
    out = []
    page = 1
    while True:
        p = urllib.parse.urlencode({
            "crtfc_key": _key(), "corp_code": corp_code,
            "bgn_de": bgn, "end_de": end, "page_no": page, "page_count": 100})
        with urllib.request.urlopen(f"{BASE}/list.json?" + p, timeout=15) as r:
            j = json.loads(r.read())
        if j.get("status") != "000":
            break
        for it in j.get("list", []):
            if any(k in it["report_nm"] for k in CATALYST_KW):
                out.append((it["rcept_dt"], it["rcept_no"], it["report_nm"].strip()))
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.05)
    return out


def fetch_document_text(rcept_no, max_chars=3500):
    """공시 원본(document.xml zip) → 태그 제거 평문(앞 max_chars). 핵심 사실이 앞에 몰림."""
    import io as _io
    import re as _re
    url = f"{BASE}/document.xml?crtfc_key={_key()}&rcept_no={rcept_no}"
    raw = urllib.request.urlopen(url, timeout=30).read()
    try:
        z = zipfile.ZipFile(_io.BytesIO(raw))
        body = z.read(z.namelist()[0])
    except zipfile.BadZipFile:
        return ""
    txt = None
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            txt = body.decode(enc); break
        except UnicodeDecodeError:
            continue
    if txt is None:
        return ""
    # head/style/script 및 남은 CSS 규칙 제거(공시 앞부분 CSS가 본문 밀어냄)
    txt = _re.sub(r"(?is)<head.*?</head>", " ", txt)
    txt = _re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", txt)
    txt = _re.sub(r"<[^>]+>", " ", txt)
    txt = _re.sub(r"(?s)\.[A-Za-z_][\w-]*\s*\{[^}]*\}", " ", txt)  # 인라인 CSS 규칙
    txt = _re.sub(r"\s+", " ", txt).strip()
    return txt[:max_chars]


def build_catalyst_dates(stock_codes, bgn, end, use_cache=True):
    """{stock_code: set('YYYYMMDD' 촉매공시 날짜)}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = os.path.join(CACHE_DIR, f"dart_catalyst_{bgn}_{end}.pkl")
    if use_cache and os.path.exists(cp):
        with open(cp, "rb") as f:
            print("[dart] 촉매 캐시 사용")
            return pickle.load(f)
    cmap = get_corp_map()
    res = {}
    miss = 0
    codes = [c for c in stock_codes]
    for i, sc in enumerate(codes):
        cc = cmap.get(sc)
        if not cc:
            miss += 1
            continue
        try:
            disc = get_disclosures(cc, bgn, end)
        except Exception:
            continue
        dates = {d for d, nm in disc if any(k in nm for k in CATALYST_KW)}
        if dates:
            res[sc] = dates
        if (i + 1) % 40 == 0:
            print(f"[dart]   {i+1}/{len(codes)}")
        time.sleep(0.05)
    with open(cp, "wb") as f:
        pickle.dump(res, f)
    print(f"[dart] 촉매 종목 {len(res)}개 (corp_code 매칭실패 {miss})")
    return res


if __name__ == "__main__":
    m = get_corp_map()
    # 삼성중공업(010140) 최근 공시 확인
    cc = m.get("010140")
    print("삼성중공업 corp_code:", cc)
    for d, nm in get_disclosures(cc, "20260720", "20260803")[:8]:
        print(" ", d, nm)
