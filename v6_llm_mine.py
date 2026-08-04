# -*- coding: utf-8 -*-
"""v6 2단계 — LLM이 알파 팩터 수식을 생성하고, 채점은 백테스트가 한다.

**역할 전환.** v1~v5의 LLM은 텍스트를 읽고 매수/등급을 정하는 *판사*였고, 그 천장을
실측했다(우리 30b +1.6%p / StockBench 최고 +2.5%p). 여기서 LLM은 **가설 생성기**다 —
DSL로 팩터 수식을 뱉을 뿐이고, 좋고 나쁨은 데이터가 정한다.

**목적함수는 IC가 아니라 '롱온리 비용후 순알파'다.** 1단계 엔진 검증에서 결정적인 게
나왔다 — 단기반전은 IC t=4.44로 강한데 롱온리 상위10 비용후는 −0.51%다. IC는 하위
종목을 공매도해야 수익이 되는 롱숏 지표인데, **개인 국내주식은 공매도가 안 된다.**
IC로 최적화하면 우리가 못 먹는 팩터를 대량 생산하게 된다.

**다중검정 방어가 이 파일의 절반이다.** 오늘 140칸 스캔이 t=4.32짜리 유령(자사주)을
만들고 홀드아웃에서 t=0.22로 무너지는 걸 봤다. 팩터 마이닝은 그 규모가 수백 배다:
  - 생성·평가한 팩터를 **전부 기록**하고 최종 보고에 개수를 명시한다
  - 마이닝 구간(2022~2024)에서만 탐색하고, **검증 구간(2025~2026)은 끝까지 안 본다**
  - 최종 후보의 t값에 **본페로니 보정**을 적용해 보고한다
  - 진화 탐색은 버그를 파고드는 데 능하다 → 거래가능 필터 등 엔진 방어가 선행돼야 한다

사용: python3 v6_llm_mine.py --market kospi --rounds 5 --per-round 12
"""
import os
import re
import json
import time
import math
import pickle
import argparse
import urllib.request

from v6_factor_lab import (load_panel, eval_factor, score, DSL, SPLIT,
                           HORIZONS, TOP_N, COST, CACHE)

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11435")
MODEL = os.environ.get("LLM_MODEL", "qwen3:30b")
LOG = os.path.join(CACHE, "v6_factor_log_{market}.json")

SHORT_H = [1, 3, 5]        # 단타 지평 — 사용자가 요구한 범위

SYSTEM = """너는 퀀트 알파 팩터를 설계한다. 아래 DSL로만 표현식을 만든다.

[데이터] open, high, low, close, volume, vwap  (각각 날짜×종목 행렬)
[시계열] ts_mean(x,d) ts_std(x,d) ts_max(x,d) ts_min(x,d) ts_sum(x,d) ts_rank(x,d)
         delay(x,d) delta(x,d) ts_return(x,d) ts_argmax(x,d) corr(x,y,d)
[횡단면] rank(x)  zscore(x)
[수학]   log(x) abs(x) sign(x) sqrt(x) mul(x,y) div(x,y) add(x,y) sub(x,y)  (+ - * / 도 가능)

[규칙]
- 표현식 하나가 팩터다. 값이 클수록 '더 살 만한 종목'이어야 한다.
- 위 이름 외에는 절대 쓰지 마라(다른 함수/상수/파이썬 문법 금지). 숫자 리터럴은 허용.
- 공매도가 불가능하다. 따라서 **상위 종목만 사서 돈이 되는가**가 유일한 기준이다.
  하위 종목을 파는 걸 전제로 한 팩터(IC만 높은 것)는 쓸모없다.
- 왕복 거래비용이 있다. 짧은 보유기간일수록 알파가 그 비용을 넘어야 한다.
- 서로 다른 아이디어를 내라. 같은 개념의 파라미터만 바꾼 변형은 가치가 낮다.

JSON만 출력: {"factors":[{"expr":"...","idea":"한 줄 근거"}, ...]}"""


def ask(prompt, n_expected, timeout=600):
    body = json.dumps({
        "model": MODEL, "stream": False, "think": False,
        "options": {"temperature": 0.9, "num_predict": 1800},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "format": {"type": "object", "properties": {"factors": {"type": "array", "items": {
            "type": "object",
            "properties": {"expr": {"type": "string"}, "idea": {"type": "string"}},
            "required": ["expr"]}}}, "required": ["factors"]},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    try:
        return json.loads(out["message"]["content"]).get("factors", [])[:n_expected]
    except Exception:
        return []


def best_short(sc):
    """단타 지평 중 비용후 순알파가 가장 큰 것 — 마이닝 목적함수."""
    cand = [(sc[h]["long_net"], h) for h in SHORT_H if h in sc]
    return max(cand) if cand else (-99, None)


def fmt(sc, hs=HORIZONS):
    return " / ".join(f"H+{h}:{sc[h]['long_net']:+.2f}({sc[h]['win']:.0f}%)"
                      for h in hs if h in sc)


def run(args):
    panel = load_panel(args.market)
    seen, results = set(), []
    log_path = LOG.format(market=args.market)

    seeds = [("-ts_return(close,5)", "단기반전"), ("-ts_std(ts_return(close,1),20)", "저변동성"),
             ("div(volume, ts_mean(volume,20))", "거래량급증")]
    hist = []
    for expr, name in seeds:
        try:
            sc = score(eval_factor(expr, panel), panel, args.market, "mine", log=False)
            hist.append(f"{expr}  → 단타 비용후 {fmt(sc, SHORT_H)}  [{name}]")
        except Exception:
            pass

    print(f"\n{'='*88}\n  v6 LLM 팩터 마이닝 — {args.market.upper()}  "
          f"마이닝구간 {SPLIT['mine'][0]}~{SPLIT['mine'][1]}\n{'='*88}")
    print(f"  목적함수: 단타(H+1/3/5) 롱온리 상위{TOP_N} 비용후 순알파 (왕복 {COST[args.market]}%p)")
    print(f"  ⚠️ 검증구간 {SPLIT['valid'][0]}~{SPLIT['valid'][1]}은 마이닝이 끝날 때까지 열지 않는다\n")

    for rd in range(1, args.rounds + 1):
        top = sorted(results, key=lambda r: -r["obj"])[:6]
        fb = "\n".join(f"  {r['expr']}  → {r['obj']:+.2f}" for r in top) or "(아직 없음)"
        prompt = (f"[참고: 알려진 팩터의 이 시장 실측 성적 — 단타 비용후 순알파]\n"
                  + "\n".join(hist)
                  + f"\n\n[지금까지 네가 낸 것 중 상위]\n{fb}\n\n"
                  f"라운드 {rd}. 새로운 팩터 {args.per_round}개를 내라. "
                  f"위에 이미 나온 표현식은 반복하지 마라. "
                  f"단기(1~5거래일) 보유로 비용 {COST[args.market]}%p를 넘길 아이디어에 집중하라.")
        got = ask(prompt, args.per_round)
        n_new = 0
        for item in got:
            expr = re.sub(r"\s+", "", str(item.get("expr", "")))
            if not expr or expr in seen:
                continue
            seen.add(expr)
            try:
                fac = eval_factor(expr, panel)
                sc = score(fac, panel, args.market, "mine", log=False)
            except Exception as ex:
                results.append({"expr": expr, "obj": -99, "err": f"{type(ex).__name__}"})
                continue
            if not sc:
                continue
            obj, h = best_short(sc)
            results.append({"expr": expr, "idea": str(item.get("idea", ""))[:70],
                            "obj": obj, "best_h": h,
                            "sc": {k: {kk: round(vv, 4) for kk, vv in v.items()}
                                   for k, v in sc.items()}})
            n_new += 1
        ok = [r for r in results if r["obj"] > -99]
        bst = max((r["obj"] for r in ok), default=-99)
        print(f"  라운드 {rd}: 신규 {n_new}개 (누적 평가 {len(ok)}개)  최고 단타 순알파 {bst:+.2f}")
        json.dump(results, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ok = [r for r in results if r["obj"] > -99]
    n_tested = len(ok)
    print(f"\n{'-'*88}\n  마이닝 종료 — 평가한 팩터 {n_tested}개 (실패 {len(results)-n_tested}개)")
    print(f"  ⚠️ 다중검정: {n_tested}개를 뒤졌으므로 본페로니 임계 t ≈ "
          f"{_bonf_t(n_tested):.2f} (일반 1.96 아님)\n")
    print("  ── 마이닝 구간 상위 8 (단타 비용후 순알파) ──")
    for r in sorted(ok, key=lambda x: -x["obj"])[:8]:
        h = r["best_h"]
        t = r["sc"][h]["t_long"] if h in r["sc"] else 0
        print(f"    {r['obj']:>+6.2f}  H+{h:<2} t={t:>+5.2f}  {r['expr'][:58]}")
        if r.get("idea"):
            print(f"            └ {r['idea']}")
    json.dump(results, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n  전체 로그: {os.path.basename(log_path)}")
    print(f"  다음: 상위 후보만 검증구간에서 확인(`--validate`). 그 전엔 검증구간을 보지 않는다.")
    print("=" * 88)


def _bonf_t(n):
    """본페로니 보정 t 임계치 근사(양측 0.05/n)."""
    from math import sqrt, log
    if n <= 1:
        return 1.96
    p = 0.05 / n
    # 정규분포 분위수 근사(Beasley-Springer-Moro 대용: 간이식)
    t = sqrt(2 * log(1 / p)) - (log(log(1 / p)) + log(4 * math.pi)) / (2 * sqrt(2 * log(1 / p)))
    return t


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["kospi", "kosdaq"], default="kospi")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--per-round", type=int, default=12)
    run(ap.parse_args())
