# -*- coding: utf-8 -*-
"""v19 — **통과. 결합 이득은 상관이 0.6까지 올라가도 살아남는다.**

━━━ 결과 (756일, 2023-06~2026-08, 경로 400개) ━━━
**사전 기준 통과**: ρ=0.30에서 결합 Sharpe **1.55** > 개별 최고 **1.31**.

  시나리오        Sharpe    MDD%   CVaR5%   실현ρ
  실측(현재)        1.87   −16.0    −2.19   −0.00
  ρ = 0.15         1.61   −16.7    −2.46    0.13
  ρ = 0.30 ★       1.55   −19.3    −2.74    0.27
  ρ = 0.50         1.38   −22.3    −3.10    0.45
  ρ = 0.70         1.22   −24.5    −3.45    0.63

**두 이득이 서로 다른 속도로 죽는다.** 이게 핵심이다.
  · **Sharpe 이득**은 개별 최고(1.31)를 **ρ≈0.6**에서야 깬다. 꽤 견고하다.
  · **MDD 이득**은 훨씬 먼저 죽는다. 개별 최고 MDD는 코인봇 −20.3%인데,
    결합은 **ρ≈0.4에서 이미 그보다 나빠진다**(ρ=0.5에서 −22.3%).
  즉 위기가 오면 **"덜 흔들린다"는 말은 먼저 거짓이 되고, "위험 대비 낫다"는 말은
  더 오래 참는다.** 배포 문서에 MDD −16.0%를 무조건적 기대치로 쓰면 안 된다.

**공통인자는 없다.** 상관행렬 고유값 PC1 34.7% / PC2 33.1% / PC3 32.1%.
완전 무상관이면 각 33.3%다. 장투와 코인봇이 둘 다 추세추종이라 숨은 공통인자를
의심했는데 **실측상 없다.** 자산군(KR 주식 vs 크립토)이 정말로 갈라놓고 있다.

**CVaR이 새로 알려준 것.** 지금까지 위험을 MDD로만 봤는데 꼬리를 직접 보니
크립토 롱숏이 **CVaR −6.91%/일, MDD −59.1%, 변동성 51%**로 압도적으로 위험하다.
Sharpe 0.68만 보고 있어서는 안 보이던 크기다. 역변동성 비중이 여기에 20%만 준 것은
결과적으로 옳았다. 결합 CVaR(−2.19%)은 **세 전략 개별(−3.01/−6.91/−3.68)보다 전부
낫다** — 분산 효과가 꼬리에서도 작동한다.

━━━ 이 결과를 믿을 때의 한계 (반드시 같이 읽을 것) ━━━
· **시뮬 MDD는 낙관적이다.** ρ=0 시뮬이 −14.1%인데 실측은 −16.0%다. iid 부트스트랩이라
  **변동성 군집(나쁜 날이 몰려 오는 성질)이 파괴**되기 때문이다. 약 12% 과소평가이므로
  ρ=0.70의 −24.5%도 실제로는 −27~28%로 봐야 한다. Sharpe는 경로 의존이 아니라 영향 적음.
· 코퓰러 층에 ρ를 넣으면 변환 후 실현 상관은 목표보다 조금 낮다(0.70→0.63). 표에
  실현치를 같이 찍어 두었다.
· **상관을 균일하게 올린다**고 가정했다. 실제 위기는 특정 쌍만 붙는 경우가 흔하다.
· 756일에는 **2022년 같은 본격 하락장이 없다.** 주변분포를 실측에서 뽑으므로,
  겪어보지 않은 크기의 사건은 시뮬에도 안 나온다.

**부수 관찰 — `portfolio_mix.py`의 MDD 기준이 약하다.** 거기 통과 조건이 "결합 MDD <
개별 **최악**"인데 최악이 크립토 롱숏 −59.1%라 사실상 자동 통과다. 의미 있는 비교는
**개별 최고(−20.3%)** 상대다. 판정을 뒤집을 정도는 아니라 그대로 두되, 여기 적어 둔다.

━━━ 이하 원래 설계 ━━━
**결합의 근거가 상관 추정 하나에 얼마나 매달려 있나.**

**착상은 gs-quant에서 왔다.** 라이브러리 자체는 안 쓴다(설치해서 실측해보니 인증 없이
되는 함수는 pandas 3~5줄짜리이고, `backtests`·`risk`의 알맹이는 Marquee 세션을 요구한다.
`information_ratio`·`drawdown_length`·`sharpe_ratio`가 `MqUninitialisedError`로 죽는다).
가져올 것은 코드가 아니라 **설계 철학**이다 — "과거 수익률이 얼마였나"가 아니라
**"이 시나리오에서 내 북이 어떻게 되나"**. 이 저장소에 정확히 그게 없었다.

**무엇이 걸려 있나.** 젯슨에 배포된 결합 포트폴리오는 세 전략을 47/20/33으로 섞는다.
그 근거가 `portfolio_mix.py`의 **Sharpe 1.31 → 1.87, MDD −20.3% → −16.0%**이고,
그 숫자는 **756일에서 잰 |ρ| ≤ 0.03**에서 나왔다. 상관이 그대로일 때만 참인 이야기다.
**위기에는 상관이 올라간다**는 것이 분산투자의 오래된 배신이고, 우리는 그 경우를
한 번도 재보지 않았다.

⚠️ 먼저 짚을 것: **역변동성 비중은 상관을 쓰지 않는다**(`iv = 1/std`). 즉 상관이
틀려도 **비중 자체는 안 흔들린다.** 흔들리는 것은 **"셋을 굴릴 이유"**다. 결합
이득이 사라지면 전략 하나만 굴리는 것과 다를 게 없어진다. 그것을 재는 것이다.

━━━ 사전 기준 (결과 보기 전에 고정한다) ━━━
**주 가설**: 결합의 근거가 견고하려면 **ρ = 0.3**(위기에 흔한 수준)에서도
  **결합 Sharpe > 개별 최고 Sharpe** 여야 한다.
  · 통과 → 결합은 상관 추정에 견고하다. 그대로 간다.
  · 실패 → 결합 이득은 **저상관 국면 한정**이다. 배포 문서에 그렇게 못박고,
    "Sharpe 1.87"을 무조건적 기대치로 쓰던 문구를 고친다.
**부차**(판정 근거 아님): ρ=0.5/0.7에서의 감쇠 곡선, CVaR, 공통인자 지분.

━━━ 세 가지 측정 ━━━
① **상관 스트레스.** 각 전략의 **주변분포는 실측 그대로 두고**(팻테일·왜도 보존)
   가우시안 코퓰러로 상관만 ρ로 갈아끼운다. Sharpe는 해석적으로도 정확히 나오지만
   (평균은 상관과 무관, 분산은 w'Σw), **MDD는 경로 의존이라 시뮬레이션이 필요**하다.
   경로 한 개는 잡음이라 다수 경로의 중앙값을 쓴다.
   ⚠️ 코퓰러 층에 ρ를 넣으면 변환 후 실현 상관은 ρ보다 살짝 낮다. **실현치를 같이
   찍어** 속이지 않는다.
② **CVaR 5%.** 지금까지 위험을 전부 MDD로 봤는데 MDD는 **실현된 경로 하나**다.
   포지션당 −100%가 나오는 강제청산이 있는 북에서는 꼬리를 직접 보는 게 맞다.
   v15 가드로 청산율을 5.30→3.22%로 낮췄지만 **남은 3.22%가 얼마나 아픈지**는 안 쟀다.
③ **공통인자 지분.** 상관행렬 고유값. 1주성분이 분산의 몇 %를 먹나. 장투와 코인봇은
   둘 다 추세추종이라 자산군이 달라도 숨은 공통인자가 있을 수 있다.

사용: python3 v19_stress.py            # 전부
      python3 v19_stress.py --paths 2000
"""
import os
import pickle
import argparse

import numpy as np
import pandas as pd

from v5_oos import CACHE

SER = os.path.join(CACHE, "v19_series.pkl")
RHOS = (0.0, 0.15, 0.30, 0.50, 0.70)
ANN = 252

try:                                   # 표준정규 CDF. scipy 있으면 그걸 쓴다.
    from scipy.special import ndtr as _ndtr
except Exception:                      # 없으면 erf 로 직접(의존성 추가 안 함)
    from math import erf, sqrt
    _verf = np.vectorize(erf)

    def _ndtr(x):
        return 0.5 * (1.0 + _verf(np.asarray(x, dtype=float) / sqrt(2.0)))


def load_series(rebuild=False):
    """세 전략의 일별 수익률. `portfolio_mix.py`와 **같은 함수를 그대로 쓴다** —
    여기서 따로 만들면 배포본과 다른 것을 재게 된다."""
    if os.path.exists(SER) and not rebuild:
        return pickle.load(open(SER, "rb"))
    import portfolio_mix as M
    print("[v19] 일별 수익률 생성(최초 1회, 몇 분 걸린다)...", flush=True)
    S = {}
    S["장투(KR)"] = M.series_trend()
    print("  장투 완료", flush=True)
    S["크립토 롱숏"] = M.series_crypto_ls()
    print("  크립토 롱숏 완료", flush=True)
    S["코인봇"] = M.series_coinbot()
    print("  코인봇 완료", flush=True)
    df = pd.DataFrame(S).dropna()
    pickle.dump(df, open(SER, "wb"))
    return df


def stats(r):
    eq = (1 + r).cumprod()
    mdd = float((eq / eq.cummax() - 1).min()) * 100
    mu, sd = float(r.mean()) * ANN, float(r.std()) * np.sqrt(ANN)
    return {"ann": mu * 100, "vol": sd * 100,
            "sharpe": mu / sd if sd else 0.0, "mdd": mdd}


def cvar(r, q=0.05):
    """하위 q 구간의 **평균** 일수익률(%). VaR는 문턱이고 CVaR는 그 너머의 평균이다."""
    n = max(int(len(r) * q), 1)
    return float(np.sort(np.asarray(r))[:n].mean()) * 100


def impose_rho(df, rho, paths, rng):
    """주변분포는 실측 그대로, 상관만 rho로 바꾼 경로들을 만든다.

    가우시안 코퓰러: 목표 상관의 다변량 정규를 뽑고 → 각 열을 그 전략의 **실측
    분위수**로 되돌린다. 이러면 팻테일·왜도는 원본 그대로이면서 의존구조만 바뀐다."""
    n, k = df.shape
    R = np.full((k, k), rho)
    np.fill_diagonal(R, 1.0)
    L = np.linalg.cholesky(R)
    # ⚠️ `np.quantile(emp, u)` 로 되돌리면 보간 때문에 **꼬리가 압축된다**(실측:
    # 표준편차 0.01633 → 0.01506, 8% 축소). 스트레스 테스트가 낙관적으로 나온다.
    # 그래서 보간 없이 **실제 관측값을 그대로 뽑는다**(경험분포 부트스트랩).
    # 인덱스 floor(u·n)은 각 관측값을 정확히 1/n 확률로 뽑으므로 주변분포가 보존된다.
    emp = [np.sort(df.iloc[:, j].values) for j in range(k)]
    out = []
    for _ in range(paths):
        z = rng.standard_normal((n, k)) @ L.T
        cols = []
        for j in range(k):
            u = _ndtr(z[:, j])
            i = np.clip((u * n).astype(int), 0, n - 1)
            cols.append(emp[j][i])
        out.append(np.column_stack(cols))
    return out


def main(args):
    df = load_series(args.rebuild)
    cols = list(df.columns)
    print(f"\n  공통 구간 {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)")

    iv = 1 / df.std()
    w = (iv / iv.sum()).values
    print(f"  역변동성 비중 " + " / ".join(f"{c} {x:.0%}" for c, x in zip(cols, w)))
    print("  ※ 이 비중은 상관을 쓰지 않는다. 상관이 틀려도 비중은 안 흔들린다.")

    print("\n  ── 개별 전략 ──")
    print(f"  {'전략':<14}{'연율%':>9}{'변동성%':>9}{'Sharpe':>9}{'MDD%':>9}{'CVaR5%':>9}")
    print("  " + "-" * 60)
    indiv = {}
    for c in cols:
        s = stats(df[c])
        indiv[c] = s
        print(f"  {c:<14}{s['ann']:>9.1f}{s['vol']:>9.1f}{s['sharpe']:>9.2f}"
              f"{s['mdd']:>9.1f}{cvar(df[c]):>9.2f}")
    best_sh = max(v["sharpe"] for v in indiv.values())
    worst_mdd = min(v["mdd"] for v in indiv.values())

    obs = df.corr()
    print("\n  ── 실측 상관 ──")
    print("  " + "".join(f"{x:>14}" for x in cols))
    for i in cols:
        print(f"  {i:<14}" + "".join(f"{obs.loc[i,j]:>14.2f}" for j in cols))

    # ① 상관 스트레스
    rng = np.random.default_rng(20260816)
    real = (df * w).sum(axis=1)
    base = stats(real)
    print(f"\n  ── ① 상관 스트레스 (경로 {args.paths}개, 주변분포 보존) ──")
    print(f"  {'시나리오':<20}{'Sharpe':>9}{'MDD%':>9}{'CVaR5%':>9}{'실현ρ':>9}")
    print("  " + "-" * 58)
    print(f"  {'실측(현재)':<20}{base['sharpe']:>9.2f}{base['mdd']:>9.1f}"
          f"{cvar(real):>9.2f}{obs.values[np.triu_indices(3,1)].mean():>9.2f}")
    res = {}
    for rho in RHOS:
        sims = impose_rho(df, rho, args.paths, rng)
        sh, md, cv, rr = [], [], [], []
        for m in sims:
            r = pd.Series(m @ w)
            s = stats(r)
            sh.append(s["sharpe"]); md.append(s["mdd"]); cv.append(cvar(r))
            c = np.corrcoef(m.T)
            rr.append(c[np.triu_indices(3, 1)].mean())
        res[rho] = (float(np.median(sh)), float(np.median(md)))
        print(f"  {'ρ = %.2f' % rho:<20}{np.median(sh):>9.2f}{np.median(md):>9.1f}"
              f"{np.median(cv):>9.2f}{np.mean(rr):>9.2f}")

    # ③ 공통인자
    ev = np.linalg.eigvalsh(obs.values)[::-1]
    print(f"\n  ── ③ 공통인자 지분 (상관행렬 고유값) ──")
    print("  " + "  ".join(f"PC{i+1} {100*e/ev.sum():.1f}%" for i, e in enumerate(ev)))
    print(f"  완전 무상관이면 각 33.3%. PC1이 클수록 숨은 공통인자가 크다.")

    # 판정
    sh30 = res[0.30][0]
    ok = sh30 > best_sh
    print(f"\n  ── 사전 기준 판정 ──")
    print(f"  ρ=0.30 결합 Sharpe {sh30:.2f}  vs  개별 최고 {best_sh:.2f}"
          f"  → {'★통과' if ok else '실패'}")
    if ok:
        print("  결합은 상관 추정에 견고하다. 배포 비중 그대로 간다.")
    else:
        print("  결합 이득은 **저상관 국면 한정**이다. 'Sharpe 1.87'을 무조건적")
        print("  기대치로 쓰던 문구를 고쳐야 한다(portfolio_live.py 하단 주석).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=400)
    ap.add_argument("--rebuild", action="store_true")
    main(ap.parse_args())
