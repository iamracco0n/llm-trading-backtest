# -*- coding: utf-8 -*-
"""v11 — v10과 같은 운용 시뮬레이션 + **뉴스(공시) 피드**.

**뉴스 오염 문제의 해법.** 웹에서 종목 뉴스를 검색하면 이벤트 **이후** 기사가 섞여
들어와("실적 발표 후 주가 급등") 미래를 보고 사게 된다. 그래서 v9에서는 뉴스를 뺐다.

**DART 공시는 접수일자가 정확히 박혀 있다.** 유상증자·수주·최대주주변경·자사주·소송·
투자판단관련 주요경영사항이 전부 공시이고, 날짜로 자르면 **룩어헤드가 0**이다.
"한화증권 유상증자" 같은 것이 바로 이 피드에 뜬다.

**v10과 다른 것은 뉴스 피드 하나뿐이다.** 유니버스·기간·자본·비용·결정 주기·판정자가
전부 같다. v10 결과(−14.23%, KOSPI 대비 +6.49%p)가 **대조군**이고, 여기서 나아지는지가
"뉴스를 보면 잘한다"의 답이다.

**루틴 공시는 뺀다** — 대량보유상황보고서·임원소유상황보고서 등은 매일 수십 건씩
쏟아지는 형식 공시라 신호가 없다. 실제로 주가에 영향을 주는 유형만 남긴다.

사용: python3 v11_news_sim.py news                # 공시 수집(캐시)
      python3 v11_news_sim.py show                # 스냅샷 + 공시 피드
      python3 v11_news_sim.py trade --file o.json
      python3 v11_news_sim.py report
"""
import os
import json
import time
import pickle
import argparse
import urllib.parse
import urllib.request

import pandas as pd

import v10_agent_sim as V
from dart_data import get_corp_map, _key, BASE

NEWS = os.path.join(V.CACHE, "v11_news%s.pkl" % os.environ.get("SIM_TAG", ""))
V.ST = os.path.join(V.CACHE, "v11_state%s.json" % os.environ.get("SIM_TAG", ""))

# **화이트리스트.** 블랙리스트로 걸렀더니 주당 300~500건이 남았다 — 형식 공시가
# 너무 많아 다 뺄 수 없다. 주가에 실질적으로 영향을 주는 유형만 남긴다.
# ("한화증권 유상증자" 같은 것이 여기 걸린다.)
KEEP = ("유상증자", "무상증자", "전환사채", "신주인수권", "교환사채", "유상감자", "무상감자",
        "자기주식", "자사주", "공급계약", "수주", "최대주주", "경영권", "타법인",
        "영업양수", "영업양도", "합병", "분할", "소송", "횡령", "배임", "영업정지",
        "상장폐지", "관리종목", "불성실공시", "현금·현물배당", "주식배당", "액면분할",
        "유형자산", "신규시설투자", "임상", "품목허가", "특허", "실적", "전망")

# 화이트리스트에 걸리지만 신호가 없는 루틴 — 증권사 ELS 발행(증권발행실적보고서)이
# 피드의 절반을 차지했고, 최대주주 '소유주식변동신고서'는 지분 소수 변동 신고다.
DROP = ("증권발행실적보고서", "소유주식변동신고서", "합병등종료보고서")


def fetch_news(bgn, end):
    """기간 내 전체 공시를 시장 단위로 받아온다(종목별 호출보다 훨씬 적다)."""
    out, page = [], 1
    while True:
        p = urllib.parse.urlencode({"crtfc_key": _key(), "bgn_de": bgn, "end_de": end,
                                    "page_no": page, "page_count": 100,
                                    "corp_cls": "Y"})     # Y=유가증권(KOSPI)
        try:
            with urllib.request.urlopen(f"{BASE}/list.json?" + p, timeout=20) as r:
                j = json.loads(r.read())
        except Exception:
            break
        if j.get("status") != "000":
            break
        out += j.get("list", [])
        if page >= int(j.get("total_page", 1)) or page >= 30:
            break
        page += 1
        time.sleep(0.05)
    return out


def cmd_news(args):
    data = V.load_px()
    dates = V.decision_dates(data)
    cmap = get_corp_map()
    rev = {v: k for k, v in cmap.items()}          # corp_code → stock_code
    cache = pickle.load(open(NEWS, "rb")) if os.path.exists(NEWS) else {}
    for ts in dates:
        key = str(ts.date())
        if key in cache:
            continue
        win = int(os.environ.get("SIM_NEWS_WIN", "7"))   # 단타는 2일이면 충분
        bgn = (ts - pd.Timedelta(days=win)).strftime("%Y%m%d")
        end = ts.strftime("%Y%m%d")
        rows = fetch_news(bgn, end)
        keep = []
        for x in rows:
            code = rev.get(x.get("corp_code"))
            nm = x.get("report_nm", "").strip()
            if not code or code not in data:
                continue
            if not any(k in nm for k in KEEP) or any(k in nm for k in DROP):
                continue
            keep.append((x.get("rcept_dt"), code, data[code]["name"], nm))
        cache[key] = keep
        print(f"[v11] {key}: 전체 {len(rows)}건 → 유니버스·유의미 {len(keep)}건", flush=True)
        pickle.dump(cache, open(NEWS, "wb"))
    pickle.dump(cache, open(NEWS, "wb"))
    print(f"[v11] 완료 {len(cache)}개 시점")


def cmd_show(args):
    data = V.load_px()
    st = V.load_state()
    dates = V.decision_dates(data)
    if st["step"] >= len(dates):
        print("종료. report 실행."); return
    ts = dates[st["step"]]
    V.cmd_show(args)
    cache = pickle.load(open(NEWS, "rb"))
    items = cache.get(str(ts.date()), [])
    win = os.environ.get("SIM_NEWS_WIN", "7")
    print(f"\n### 직전 {win}일 공시 {len(items)}건 (접수일 기준, 미래 차단)")
    for d, code, name, nm in items[:args.news]:
        print(f"  {d} {code} {name[:9]:<10} {nm[:52]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["news", "show", "trade", "report"])
    ap.add_argument("--file")
    ap.add_argument("--top", type=int, default=200)
    ap.add_argument("--news", type=int, default=60)
    a = ap.parse_args()
    if a.cmd == "news":
        cmd_news(a)
    elif a.cmd == "show":
        cmd_show(a)
    elif a.cmd == "trade":
        V.cmd_trade(a)
    else:
        V.cmd_report(a)
