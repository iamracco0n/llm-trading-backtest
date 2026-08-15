# -*- coding: utf-8 -*-
"""v9 — 공시 본문 + **차트/수치 컨텍스트**를 같이 주면 달라지나 (프런티어 모델).

**왜 또 하나.** `v5_ab_numbers.py`가 같은 질문을 로컬 모델로 시험해 기각했다
(판정은 31% 바뀌었지만 IS +6.64% → OOS −1.21%). 프런티어 모델로는 안 해봤다.
사용자 요청으로 진행하며, **기대는 낮다는 것을 미리 적어둔다** — 이미 세 갈래로
기각된 방향이다(텍스트+수치 A/B, Alpha Arena 실거래, 뉴스헤드라인 논문).

**설계 — 변수는 '정보량' 하나**
  · 이벤트: v8과 **완전히 같은 65건**(컷오프 이후, 오염 없음)
  · 대조군: v8에서 **이미 봉인된 텍스트 전용 판정**(`v8_judgments.json`)
  · 실험군: 같은 본문 + 아래 차트/수치 컨텍스트
  · 판정자·프롬프트·등급 기준 동일. 바뀌는 것은 주어지는 정보뿐.

**룩어헤드 0.** 컨텍스트는 **공시일 직전 거래일까지의 데이터만** 쓴다. 공시 당일
종가조차 쓰지 않는다(공시가 장중에 나올 수 있어 당일 종가에는 공시 반응이 섞인다).

**차트가 보여주는 것이 곧 수치다.** MA 위치·52주 고저 대비·추세·거래량 급증은
차트를 읽어 얻는 정보와 같고, 숫자로 주면 손실 없이 전달된다(차트 이미지는
같은 숫자의 손실 압축이다).

**사전 기준(결과 보기 전 고정)**: 실험군이 대조군(텍스트 전용)을 **전 지평에서
이기고** H+40이 로컬 최고보다 높아야 "정보를 더 주면 나아진다"가 성립한다.

사용: python3 v9_rich_context.py build     # 컨텍스트 생성(캐시)
      python3 v9_rich_context.py show -n 33  # 판정용 출력
      python3 v9_rich_context.py save --file j.json
      python3 v9_rich_context.py compare
"""
import os
import json
import pickle
import argparse
import datetime as dt

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

from dart_data import fetch_document_text
from v5_oos import CACHE
from v8_forward_claude import EV, JG, CUTOFF

CTX = os.path.join(CACHE, "v9_context.pkl")
RICH = os.path.join(CACHE, "v9_judgments_rich.json")


def cmd_build(args):
    """공시일 **직전 거래일까지**의 차트/수치 컨텍스트."""
    events = pickle.load(open(EV, "rb"))
    ctx = pickle.load(open(CTX, "rb")) if os.path.exists(CTX) else {}
    ks = fdr.DataReader("KS11", "2025-06-01")
    todo = [(c, d, rn, nm) for c, evs in events.items() for d, rn, nm in evs
            if rn not in ctx]
    print(f"[v9] 컨텍스트 생성 {len(todo)}건")
    for code, d, rn, nm in todo:
        try:
            px = fdr.DataReader(code, "2025-06-01")
        except Exception:
            continue
        ts = pd.Timestamp(d)
        hist = px[px.index < ts]                 # ⚠️ 공시 당일 제외 = 룩어헤드 0
        if len(hist) < 60:
            continue
        c = hist["Close"]
        v = hist["Volume"]
        kh = ks[ks.index < ts]["Close"]
        n = min(len(c), len(kh))
        rel20 = ((c.iloc[-1] / c.iloc[-21] - 1) - (kh.iloc[-1] / kh.iloc[-21] - 1)) * 100 \
            if n > 21 else float("nan")
        ctx[rn] = {
            "code": code, "date": d, "name": nm,
            "close": float(c.iloc[-1]),
            "r20": float(c.iloc[-1] / c.iloc[-21] - 1) * 100 if len(c) > 21 else np.nan,
            "r60": float(c.iloc[-1] / c.iloc[-61] - 1) * 100 if len(c) > 61 else np.nan,
            "vol20": float(c.pct_change().tail(20).std() * 100),
            "ma20": float(c.iloc[-1] / c.tail(20).mean() - 1) * 100,
            "ma60": float(c.iloc[-1] / c.tail(60).mean() - 1) * 100,
            "hi52": float(c.iloc[-1] / c.tail(250).max() - 1) * 100,
            "lo52": float(c.iloc[-1] / c.tail(250).min() - 1) * 100,
            "vratio": float(v.iloc[-1] / v.tail(20).mean()) if v.tail(20).mean() else np.nan,
            "rel20": float(rel20),
        }
    pickle.dump(ctx, open(CTX, "wb"))
    print(f"[v9] 완료 {len(ctx)}건")


def block(x):
    def f(v, s="%+.1f"):
        return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else s % v
    return (f"[공시 직전 거래일까지의 시장 데이터 — 공시 당일은 제외]\n"
            f"  종가 {x['close']:,.0f}원 | 20일 수익률 {f(x['r20'])}% "
            f"| 60일 {f(x['r60'])}% | KOSPI 대비 20일 {f(x['rel20'])}%p\n"
            f"  20일 변동성 {f(x['vol20'], '%.1f')}%/일 "
            f"| MA20 대비 {f(x['ma20'])}% | MA60 대비 {f(x['ma60'])}%\n"
            f"  52주 고점 대비 {f(x['hi52'])}% | 저점 대비 {f(x['lo52'])}% "
            f"| 직전일 거래량/20일평균 {f(x['vratio'], '%.2f')}배")


def cmd_show(args):
    ctx = pickle.load(open(CTX, "rb"))
    done = json.load(open(RICH, encoding="utf-8")) if os.path.exists(RICH) else {}
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
        print(block(x))
        print(f"[공시 본문]\n{body.strip()[:1500]}")
        print()


def cmd_save(args):
    new = json.load(open(args.file, encoding="utf-8"))
    done = json.load(open(RICH, encoding="utf-8")) if os.path.exists(RICH) else {}
    add = 0
    for rn, v in new.items():
        if rn in done:
            continue
        v["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[rn] = v
        add += 1
    json.dump(done, open(RICH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[v9] 신규 {add}건, 누적 {len(done)}건 (기존 불변)")


def cmd_compare(args):
    import collections
    A = json.load(open(JG, encoding="utf-8"))          # 텍스트 전용(대조군)
    B = json.load(open(RICH, encoding="utf-8"))        # 본문+수치(실험군)
    common = set(A) & set(B)
    chg = sum(1 for k in common if A[k]["verdict"] != B[k]["verdict"])
    print(f"\n  공통 {len(common)}건 | **판정이 바뀐 비율 {100*chg/len(common):.1f}%**")
    for name, J in (("A 텍스트 전용", A), ("B 본문+수치", B)):
        c = collections.Counter(J[k]["verdict"] for k in common)
        n95 = sum(1 for k in common if J[k].get("score", 0) >= 95)
        print(f"  {name:<14}" + "  ".join(f"{x} {c.get(x,0)}" for x in
              ("강한호재", "약한호재", "중립", "악재")) + f"  | 95+ {n95}")
    print("\n  ⚠️ 알파 비교는 H+40이 차는 10월부터. `v8_local.py compare` 와 함께 본다.")
    print("  사전 기준: B가 A를 전 지평에서 이기고 H+40이 로컬 최고보다 높아야 통과")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "show", "save", "compare"])
    ap.add_argument("-n", type=int, default=33)
    ap.add_argument("--file")
    a = ap.parse_args()
    {"build": cmd_build, "show": cmd_show,
     "save": cmd_save, "compare": cmd_compare}[a.cmd](a)
