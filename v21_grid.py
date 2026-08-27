# -*- coding: utf-8 -*-
"""v21 — **입력 3종 × 모델 4종** 격자 분석. 판정이 무엇에 더 좌우되나.

━━━ 무엇을 물었나 ━━━
같은 65건(컷오프 이후, 오염 0)을 세 가지 입력으로 판정했다. SYSTEM·SCHEMA·등급기준은
전부 `llm_earnings.judge_earnings` 그대로이고 **본문 앞에 붙는 블록 하나만 바뀐다**:

    v8   [공시 본문]
    v9   [차트/수치] + [공시 본문]
    v20  [직전 60일 공시 이력] + [공시 본문]

모델은 Opus 5 / gemma4:31b / qwen3.6:35b / muse-glimmer:30b. 로컬 셋은 aurora CPU
전용(num_gpu=0). 12칸 중 11칸을 채웠다(Opus × 뉴스만 미실행).

━━━ 결과 1. 입력 민감도는 **모델마다 4배 차이가 난다** ━━━
기준선(본문만) 대비 판정이 바뀐 비율:

    모델                차트 추가    뉴스 추가
    Opus 5                6.2%       (미실행)
    gemma4:31b            9.2%        4.6%
    muse-glimmer:30b     12.3%        9.2%
    qwen3.6:35b          24.6%       20.0%

**gemma4:31b 는 거의 안 흔들린다** — 강한호재가 세 팔 모두 정확히 32건, 95점 이상도
모두 12건이다. 분포 자체가 본문에 못박혀 있다. 반대로 qwen3.6:35b 는 차트를 주면
1/4이 바뀌고 평균 점수가 52 → 65로 뛴다. **"정보를 더 주면 판정이 바뀌나"의 답이
모델에 따라 정반대**이므로, 한 모델에서 재고 일반화하면 안 된다.

━━━ 결과 2. ⚠️ 앞서 내놓은 해석을 **철회한다** ━━━
muse-glimmer 만 보고 이렇게 말했었다 — "차트 팔과 뉴스 팔이 서로(18.5%) 기준선과의
거리(12.3%, 9.2%)보다 더 멀다. 둘 다 진짜 정보라면 같은 정답으로 수렴해야 하는데
발산하니, 추가 맥락은 정보가 아니라 교란이다."

**나머지 두 모델에서 재현되지 않았다.** 기준선 대비 변화량 a, b 로부터 차트↔뉴스
차이가 놓일 수 있는 구간 [|a−b|, min(a+b, n)] 을 잡고 관측값의 위치를 0~1 로
정규화한 발산지수:

    gemma4:31b        0.33     ← 같은 건을 같은 방향으로 바꿈(정보 쪽)
    qwen3.6:35b       0.23     ← 정보 쪽
    muse-glimmer:30b  0.83     ← 교란 쪽 (혼자 예외)

3분의 2가 반대다. **모델 하나에서 본 인상적인 패턴을 성질로 착각한 것**이고,
이 저장소가 v18 에서 "가장 높은 쌍 하나만 보고 일반화했다"고 자책한 것과 같은 실수를
바로 다음 실험에서 되풀이했다. 남겨두는 이유가 그것이다.

━━━ 결과 3. 점수 척도가 모델 간에 이식되지 않는다 ━━━
같은 65건·같은 채점 기준인데 평균 점수(본문만): Opus 64 / gemma4 57 / qwen3.6 52 /
**muse-glimmer 27**. glimmer 는 95점 이상이 65건 중 1건뿐이다.
→ **"score ≥ 80 이면 매수" 같은 문턱값은 모델을 갈면 반드시 다시 교정해야 한다.**
   같은 규칙을 그대로 옮기면 glimmer 는 아무것도 안 사고 gemma4 는 12건을 산다.
   모델 교체는 파라미터 교체가 아니라 **전략 교체**다.

━━━ 결과 4. 모델간 일치율은 입력을 늘려도 나아지지 않는다 ━━━
로컬 3종끼리 평균 일치율: 본문 69.2% → 차트 67.7% → 뉴스 69.7%. 사실상 평평하다.
(4모델 평균 73.6% → 70.5% 는 뉴스 팔에 Opus 가 없어 비교가 어긋난다. 같은 3모델로
맞춰 다시 계산한 것이 위 숫자다.)
Opus 와 로컬의 평균 일치율만 **77.9% → 73.3%** 로 떨어진다. 차트를 주면 Opus 가
로컬들과 더 갈린다 — 수치를 다르게 쓴다는 뜻이지, 더 맞힌다는 뜻은 아니다.

━━━ ⚠️ 여기까지는 전부 '판정이 어떻게 갈리나'이지 '무엇이 돈을 버나'가 아니다 ━━━
판정 분포가 크게 갈려도 수익은 안 갈릴 수 있다. `v5_ab_numbers` 가 정확히 그랬다 —
판정이 31% 바뀌었는데 OOS 수익은 −1.21% 였다. 알파 비교는 H+20 이 9월 중순,
H+40 이 **10월 중순**에 차므로 그때 `v8_local.py compare` 를 다시 돌려야 한다.

사용: python3 v21_grid.py            # 전부
      python3 v21_grid.py --only arms|xmodel|overlap|grid
"""
import argparse
import collections
import itertools
import json
import os

from v5_oos import CACHE

# Opus 판정 파일만 명명 규칙이 다르다(태그 없음 / _rich)
SPECIAL = {("v9_judgments", "claude"): "v9_judgments_rich",
           ("v8_judgments", "claude"): "v8_judgments"}
ARMS = [("본문만", "v8_judgments"), ("차트+본문", "v9_judgments"),
        ("뉴스+본문", "v20_judgments")]
MODELS = [("Opus 5", "claude"), ("gemma4:31b", "gemma31"),
          ("qwen3.6:35b", "qwen36"), ("muse-glimmer:30b", "glimmer")]
ORDER = ["강한호재", "약한호재", "중립", "악재"]


def load(stem, tag):
    base = SPECIAL.get((stem, tag), f"{stem}_{tag}")
    p = os.path.join(CACHE, base + ".json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def show_grid():
    print("\n  ══ 격자 채움 현황 ══")
    print(f"  {'':<14}" + "".join(f"{m:>18}" for m, _ in MODELS))
    for label, stem in ARMS:
        row = f"  {label:<14}"
        for _, tag in MODELS:
            J = load(stem, tag)
            row += f"{('%d건' % len(J)) if J else '—':>18}"
        print(row)


def show_arms():
    """모델을 고정하고 입력만 바꾼다 — 모델 차이가 안 섞인다."""
    for tag, label in [(t, l) for l, t in MODELS]:
        J = {n: load(s, tag) for n, s in ARMS}
        J = {k: v for k, v in J.items() if v}
        if len(J) < 2:
            continue
        common = set.intersection(*[set(v) for v in J.values()])
        print(f"\n  ══ {label} — 입력만 바꿨을 때 (공통 {len(common)}건) ══")
        print(f"  {'입력':<12}" + "".join(f"{x:>9}" for x in ORDER) +
              f"{'평균점':>9}{'95+':>6}")
        for n, v in J.items():
            c = collections.Counter(v[k]["verdict"] for k in common)
            sc = [v[k].get("score", 0) for k in common]
            print(f"  {n:<12}" + "".join(f"{c.get(x,0):>9}" for x in ORDER) +
                  f"{sum(sc)/len(sc):>9.1f}{sum(1 for x in sc if x>=95):>6}")
        for a, b in itertools.combinations(J, 2):
            chg = sum(1 for k in common if J[a][k]["verdict"] != J[b][k]["verdict"])
            print(f"    {a} vs {b:<14} 판정 바뀜 {100*chg/len(common):.1f}%")


def show_overlap():
    """차트와 뉴스가 **같은 건을 같은 방향으로** 바꾸는가(정보) 아니면 제각각인가(교란).

    a=차트 변화, b=뉴스 변화 일 때 차트↔뉴스 차이는 [|a−b|, min(a+b,n)] 사이에
    놓인다. 하한=완전히 겹침(같은 건을 같게), 상한=완전히 어긋남. 위치를 0~1 로.
    ⚠️ 이 지표 하나로 glimmer 만 보고 '교란'이라 결론냈다가 철회했다 — 표 전체를 볼 것."""
    print("\n  ══ 차트 팔 ↔ 뉴스 팔 발산지수 ══")
    print(f"  {'모델':<20}{'차트변화':>9}{'뉴스변화':>9}{'차트↔뉴스':>11}"
          f"{'하한':>7}{'상한':>7}{'발산지수':>9}")
    for tag, label in [(t, l) for l, t in MODELS]:
        B, Ch, Nw = (load("v8_judgments", tag), load("v9_judgments", tag),
                     load("v20_judgments", tag))
        if not all((B, Ch, Nw)):
            continue
        k = set(B) & set(Ch) & set(Nw)
        n = len(k)
        a = sum(1 for x in k if B[x]["verdict"] != Ch[x]["verdict"])
        b = sum(1 for x in k if B[x]["verdict"] != Nw[x]["verdict"])
        d = sum(1 for x in k if Ch[x]["verdict"] != Nw[x]["verdict"])
        lo, hi = abs(a - b), min(a + b, n)
        idx = (d - lo) / (hi - lo) if hi > lo else float("nan")
        print(f"  {label:<20}{100*a/n:>8.1f}%{100*b/n:>8.1f}%{100*d/n:>10.1f}%"
              f"{100*lo/n:>6.1f}%{100*hi/n:>6.1f}%{idx:>9.2f}")
    print("  0=같은 건을 같은 방향으로(정보)   1=제각각 흔듦(교란)")


def show_xmodel():
    """팔을 고정하고 모델만 바꾼다.

    ⚠️ 팔마다 모델 수가 다르면(뉴스 팔엔 Opus 가 없다) 평균끼리 비교하면 안 된다.
    그래서 **모든 팔에 공통으로 있는 모델**로만 맞춰 한 번 더 낸다."""
    have_all = [(l, t) for l, t in MODELS
                if all(load(s, t) for _, s in ARMS)]
    for arm, stem in ARMS:
        J = {l: load(stem, t) for l, t in MODELS}
        J = {k: v for k, v in J.items() if v}
        if len(J) < 2:
            continue
        common = set.intersection(*[set(v) for v in J.values()])
        ag = {(a, b): 100 * sum(1 for k in common
                                if J[a][k]["verdict"] == J[b][k]["verdict"]) / len(common)
              for a, b in itertools.combinations(J, 2)}
        print(f"\n  ══ [{arm}] 모델만 바꿨을 때 (모델 {len(J)}개, {len(common)}건) ══")
        for (a, b), r in sorted(ag.items(), key=lambda x: -x[1]):
            print(f"    {a} vs {b:<20} {r:5.1f}%")
        print(f"    평균 {sum(ag.values())/len(ag):.1f}%")
        # 모든 팔에 있는 모델로만 맞춘 값 — 팔 사이 비교는 이것으로만 한다
        sub = [l for l, _ in have_all if l in J]
        if len(sub) >= 2 and len(sub) < len(J):
            s = [ag[(a, b)] for a, b in itertools.combinations(J, 2)
                 if a in sub and b in sub]
            print(f"    공통모델({len(sub)}개)만: {sum(s)/len(s):.1f}%  ← 팔 사이 비교는 이 값으로")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["grid", "arms", "overlap", "xmodel"])
    a = ap.parse_args()
    fns = {"grid": show_grid, "arms": show_arms,
           "overlap": show_overlap, "xmodel": show_xmodel}
    for k, f in fns.items():
        if a.only in (None, k):
            f()
