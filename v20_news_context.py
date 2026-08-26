# -*- coding: utf-8 -*-
"""v20 — 공시 본문 + **그 종목의 직전 공시 이력(뉴스)**. v8/v9와 짝을 맞춘 세 번째 팔.

**왜 이 형태인가.** 사용자가 "차트도 주고 뉴스도 주고 여러 케이스 다 해보자"고 했다.
차트는 v9가 이미 하고 있다. 뉴스는 `v11_news_sim.py`가 있지만 **그것은 운용
시뮬레이션**(스냅샷 → 주문 JSON → 체결)이라 v8/v9의 건별 판정과 **비교가 안 된다.**
한쪽은 "이 공시가 얼마나 좋은가"를 묻고 다른 쪽은 "무엇을 살까"를 묻는다. 섞으면
모델 차이인지 과제 차이인지 못 가린다.

그래서 뉴스도 **같은 판정 설계**로 맞춘다. 세 팔이 정확히 한 변수만 다르다:

    v8   [공시 본문]                     ← 대조군(이미 봉인됨)
    v9   [차트/수치] + [공시 본문]
    v20  [직전 공시 이력] + [공시 본문]   ← 여기

판정 함수·SYSTEM·SCHEMA·등급 기준은 **`llm_earnings.judge_earnings` 그대로**다.
바뀌는 것은 body_text 앞에 붙는 블록 하나뿐이다.

**룩어헤드 0.** 공시 이력은 **판정 대상 공시의 접수일 전날까지**만 모은다(`end = date-1`).
당일 공시는 넣지 않는다 — 같은 날 다른 공시에 실적 내용이 새어 있을 수 있다.
DART는 접수일자가 정확히 박혀 있어 날짜로 자르면 미래가 안 샌다. 웹 뉴스 검색을
안 쓰는 이유가 이것이다(이벤트 **이후** 기사가 섞여 들어온다).

**루틴 공시는 뺀다.** 화이트리스트/블랙리스트는 `v11_news_sim.py`의 것을 그대로
재사용한다 — 거기서 이미 "증권발행실적보고서가 피드의 절반"이라는 것을 겪고 정제했다.

**사전 기준(결과 보기 전 고정)**: v20이 v8(텍스트 전용)을 **전 지평에서 이기고**
H+40이 로컬 최고보다 높아야 "뉴스를 더 주면 나아진다"가 성립한다. v9와 같은 잣대다.
**기대는 낮다** — 이 저장소는 정보량을 늘리는 방향으로 이미 여러 번 기각됐다.

━━━ ⚠️ 처치가 약하다. 돌리기 **전에** 적어 둔다 ━━━
v17에서 배운 것 — 결과를 본 뒤에 "사실 데이터가 부실했다"고 말하면 변명이 된다.
실측(필터 후): **65종목 중 뉴스가 있는 것은 33개(51%)뿐이고 종목당 평균 1.0건**이다.
즉 **절반은 빈 블록을 받는다.** 최대로 잡아도 표본의 절반에서만 효과가 날 수 있다.
따라서 이 팔이 실패해도 결론은 **"뉴스가 도움이 안 된다"가 아니라 "이 밀도의
공시 피드로는 도움이 안 된다"**까지다. 그 이상으로 일반화하지 않는다.
(v9의 차트 팔은 65건 **전부**에 수치가 차 있어 처치가 훨씬 강하다. 두 팔의 결과를
나란히 놓을 때 이 비대칭을 반드시 같이 읽어야 한다.)

사용: python3 v20_news_context.py build
      LLM_MODEL=muse-glimmer:30b python3 v20_news_context.py judge --tag glimmer
      python3 v20_news_context.py show -n 33     # 프런티어 모델 판정용
      python3 v20_news_context.py save --file j.json
      python3 v20_news_context.py compare
"""
import os
import json
import time
import pickle
import argparse
import datetime as dt

import pandas as pd

from dart_data import fetch_document_text, get_disclosures, get_corp_map
from v5_oos import CACHE
from v8_forward_claude import JG
from v9_rich_context import CTX
from v11_news_sim import KEEP, DROP

NEWS = os.path.join(CACHE, "v20_news.pkl")
OWN = os.path.join(CACHE, "v20_judgments_claude.json")

WIN_DAYS = 60      # 직전 60일. 분기 실적 사이클(약 90일)보다 짧게 잡아
                   # "지난 분기 이후 무슨 일이 있었나"만 담는다.
MAX_ITEMS = 12     # 종목당 최대 표시 건수(너무 길면 본문을 밀어낸다)

# v11의 DROP에 더해 여기서만 빼는 것.
# `결산실적공시예고`는 **"곧 실적을 발표하겠다"는 예고**일 뿐 내용이 없다. 1차
# 수집에서 두 번째로 흔했는데(14건), 하필 **지금 판정 중인 바로 그 공시**를 가리킨다.
# 모델에게 "실적 발표가 임박했다"고 알려주는 셈인데 그건 이미 아는 사실이라
# 정보가 0이고, 피드 길이만 늘려 진짜 사건을 밀어낸다.
DROP_EXTRA = ("결산실적공시예고", "실적공시예고")


def dst(tag):
    return os.path.join(CACHE, f"v20_judgments_{tag}.json")


def cmd_build(args):
    """각 사건 종목의 **직전 60일 공시 이력**을 모은다(당일 제외)."""
    ctx = pickle.load(open(CTX, "rb"))
    cmap = get_corp_map()
    cache = pickle.load(open(NEWS, "rb")) if os.path.exists(NEWS) else {}
    todo = [rn for rn in ctx if rn not in cache]
    print(f"[v20] 공시 이력 수집 {len(todo)}건 (캐시 {len(cache)})", flush=True)
    for i, rn in enumerate(todo):
        x = ctx[rn]
        cc = cmap.get(x["code"])
        if not cc:
            cache[rn] = []
            continue
        d = dt.datetime.strptime(x["date"], "%Y%m%d").date()
        bgn = (d - dt.timedelta(days=WIN_DAYS)).strftime("%Y%m%d")
        end = (d - dt.timedelta(days=1)).strftime("%Y%m%d")   # ⚠️ 당일 제외
        try:
            rows = get_disclosures(cc, bgn, end)
        except Exception:
            rows = []
        keep = [(dtx, nm) for dtx, nm in rows
                if any(k in nm for k in KEEP)
                and not any(k in nm for k in DROP)
                and not any(k in nm for k in DROP_EXTRA)]
        keep.sort(reverse=True)
        cache[rn] = keep[:MAX_ITEMS]
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(todo)}", flush=True)
            pickle.dump(cache, open(NEWS, "wb"))
        time.sleep(0.05)
    pickle.dump(cache, open(NEWS, "wb"))
    n = [len(v) for v in cache.values()]
    print(f"[v20] 완료 {len(cache)}종목 | 공시 있는 종목 "
          f"{sum(1 for x in n if x)}개 | 종목당 평균 {sum(n)/max(len(n),1):.1f}건")


def block(rn, cache, ctx):
    """뉴스 블록. 없으면 '없음'이라고 **명시한다** — 빈칸으로 두면 모델이
    블록 자체를 못 본 것인지 사건이 없었던 것인지 구분 못 한다."""
    items = cache.get(rn, [])
    x = ctx[rn]
    d = dt.datetime.strptime(x["date"], "%Y%m%d").date()
    head = (f"[직전 {WIN_DAYS}일 공시 이력] "
            f"({(d - dt.timedelta(days=WIN_DAYS))} ~ {d - dt.timedelta(days=1)}, "
            f"판정 대상 공시일 전날까지)")
    if not items:
        return head + "\n  (해당 기간 유의미한 공시 없음)"
    return head + "\n" + "\n".join(f"  {a[:4]}-{a[4:6]}-{a[6:]}  {b}"
                                   for a, b in items)


def cmd_judge(args):
    from llm_earnings import judge_earnings
    ctx = pickle.load(open(CTX, "rb"))
    cache = pickle.load(open(NEWS, "rb"))
    out = dst(args.tag)
    done = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    todo = [rn for rn in ctx if rn not in done]
    print(f"[v20] {len(todo)}건 판정 (캐시 {len(done)}) | "
          f"model={os.environ.get('LLM_MODEL','?')} | "
          f"{'GPU' if os.environ.get('LLM_NUM_GPU','0') != '0' else 'CPU'}", flush=True)
    t0, fail = time.time(), 0
    for i, rn in enumerate(todo):
        x = ctx[rn]
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            fail += 1
            continue
        rich = f"{block(rn, cache, ctx)}\n\n[공시 본문]\n{body.strip()[:1500]}"
        r = judge_earnings(x["name"], rich, timeout=900)
        if r is None:
            fail += 1
            print(f"  실패 {rn} — 미저장 ({fail}건째)", flush=True)
            # 연속 실패 = 모델이 안 올라온 것. 65번 헛돌지 말고 일찍 멈춘다
            # (2026-08-27 aurora RAM 31GB 부족으로 전량 실패한 적 있다).
            if fail >= 3 and len(done) == 0:
                print("  !! 연속 실패 — 모델 로드 실패로 보고 중단. "
                      "`ollama ps; free -g` 확인 요망", flush=True)
                return
            continue
        r["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[rn] = r
        json.dump(done, open(out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        el = time.time() - t0
        print(f"  {i+1}/{len(todo)} {x['name'][:12]:<12} {r['verdict']}({r['score']}) "
              f"| {el/(i+1):.0f}초/건 남은 {(len(todo)-i-1)*el/(i+1)/60:.0f}분",
              flush=True)
    print(f"[v20] 완료 {len(done)}건 (실패 {fail})")


def cmd_show(args):
    ctx = pickle.load(open(CTX, "rb"))
    cache = pickle.load(open(NEWS, "rb"))
    done = json.load(open(OWN, encoding="utf-8")) if os.path.exists(OWN) else {}
    todo = [rn for rn in ctx if rn not in done]
    print(f"### 남은 {len(todo)}건 중 {min(args.n, len(todo))}건 (완료 {len(done)})\n")
    for rn in todo[:args.n]:
        x = ctx[rn]
        try:
            body = fetch_document_text(rn)
        except Exception:
            body = ""
        if not body:
            continue
        print(f"===== {rn} | {x['code']} | {x['date']} | {x['name']}")
        print(block(rn, cache, ctx))
        print(f"[공시 본문]\n{body.strip()[:1500]}")
        print()


def cmd_save(args):
    new = json.load(open(args.file, encoding="utf-8"))
    done = json.load(open(OWN, encoding="utf-8")) if os.path.exists(OWN) else {}
    add = 0
    for rn, v in new.items():
        if rn in done:                 # 봉인 — 기존 판정은 절대 덮지 않는다
            continue
        v["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[rn] = v
        add += 1
    json.dump(done, open(OWN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[v20] 신규 {add}건, 누적 {len(done)}건 (기존 불변)")


def cmd_compare(args):
    import collections
    A = json.load(open(JG, encoding="utf-8"))            # v8 텍스트 전용(대조군)
    src = dst(args.tag) if args.tag else OWN
    B = json.load(open(src, encoding="utf-8"))
    common = set(A) & set(B)
    if not common:
        print("  공통 표본 없음 — 대조군과 태그를 확인할 것")
        return
    chg = sum(1 for k in common if A[k]["verdict"] != B[k]["verdict"])
    print(f"\n  공통 {len(common)}건 | **판정이 바뀐 비율 {100*chg/len(common):.1f}%**")
    for name, J in (("A 텍스트 전용", A), (f"C 본문+뉴스({args.tag or 'claude'})", B)):
        c = collections.Counter(J[k]["verdict"] for k in common)
        print(f"  {name:<22}" + "  ".join(f"{x} {c.get(x,0)}" for x in
              ("강한호재", "약한호재", "중립", "악재")))
    print("\n  ⚠️ 판정 분포가 바뀐 것과 **수익이 나아진 것은 다르다.** 알파 비교는")
    print("     H+40이 차는 10월부터. v5_ab_numbers 가 정확히 이 함정에 빠졌다 —")
    print("     판정은 31% 바뀌었는데 OOS 수익은 −1.21%였다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "judge", "show", "save", "compare"])
    ap.add_argument("-n", type=int, default=33)
    ap.add_argument("--file")
    ap.add_argument("--tag")
    a = ap.parse_args()
    {"build": cmd_build, "judge": cmd_judge, "show": cmd_show,
     "save": cmd_save, "compare": cmd_compare}[a.cmd](a)
