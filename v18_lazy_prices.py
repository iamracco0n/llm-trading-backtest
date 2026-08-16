# -*- coding: utf-8 -*-
"""v18 — **기각. Lazy Prices는 한국 대형주에 복제되지 않는다. 2단계(LLM)는 실행 안 함.**

━━━ 결과 먼저 (n=2,651 — 이 저장소 최대 표본) ━━━
게이트 0 **통과**: 전년대비 코사인 중앙 0.9175, **IQR 0.2530**(기준 0.01).
  한국 공시가 전부 똑같아서 못 한다는 우려는 틀렸다. 문구는 해마다 많이 바뀐다.

게이트 1 **기각**: H+60 롱숏(안 바꾼 쪽 롱 / 많이 바꾼 쪽 숏)
                        전체표본        깨끗한 부분집합
    (a) 스프레드 중앙값   −0.91%p  X      −1.28%p  X
    (b) Q5 > Q1          X (역전)        X (역전)
    (c) 비겹침 t > 2.0   −0.01    X       0.06    X
  5분위가 단조가 아니다. H+60에서 최고는 Q4(+1.29), 최저가 Q5(−0.74)다. 구조가 없다.

**분산은 있는데 정렬이 없다** — 이게 핵심이다. 바뀐 양은 크지만 그 양이 수익률과
아무 관계가 없다. 미국에서 성립한 것이 한국 대형주에서는 성립하지 않는다.

**중간에 걸러낸 함정 하나.** 코사인 최소 0.21, 문서 길이 15배 같은 값이 나와 수집
실패를 의심했는데 아니었다(5만자 미만 0건). **2022.12 사업보고서가 전 종목 일제히
4~5배로 늘어난 규제성 서식 개정**이었다. 전체 쌍의 15.6%가 여기 해당한다. 이걸
그대로 두면 '문구를 바꿨다'가 회사 사정이 아니라 개정 적용 시점을 뜻하게 된다.
제외하고 다시 돌려도 결론은 같았다(위 표 오른쪽 열).

**H+120에 반대 방향 신호가 있다(스프레드 −3.66%p, t=−2.77). 근거로 쓰지 않는다.**
  1. 사전에 "주 가설이 죽으면 부차 지표는 죽은 것"이라고 고정해 두었다.
  2. **부호가 논문과 반대**다. 복제가 아니라 새 주장이고, 호라이즌 3개를 본 뒤
     고른 것이라 다중검정 그 자체다.
  3. **단조가 아니다.** Q1만 +3.52로 튀고 Q2~Q5(−3.30/+0.14/−0.81/−0.14)는 잡음이다.
     팩터라면 기울기가 있어야 한다. 한 분위만 튀는 건 이상치다.
  4. H+120(약 6개월)은 분기 공시 간격(약 63거래일)의 두 배라 **포지션이 2겹**이다.
     시즌을 독립으로 세는 이 t는 대략 √2만큼 부풀어 있다(보정하면 ≈ −1.96).

**따라서 2단계(바뀐 문구를 LLM이 읽고 악재/서식 판정)는 실행하지 않는다.** 사전에
그렇게 정했다. 반론이 하나 있긴 하다 — 코사인은 *얼마나* 바뀌었나만 재므로,
드문 실질적 변경이 대량의 서식 잡음에 묻혔을 수 있고 그걸 가려내는 건 읽어야 아는
일이다. 다만 그 반론은 **"싼 검사가 실패했으니 비싼 검사를 하자"**는 형태이고,
이 저장소가 전략 여덟 개를 너무 오래 살려둔 논리와 같다. 라벨도 없고 표본도
2,651건뿐이라 건초더미에서 바늘을 찾는 일이 된다. 사용자가 뒤집지 않는 한 중단한다.

━━━ 한계 (결론을 좁혀 두는 것) ━━━
· 유니버스가 **현재 KOSPI 대형주 145**다. 상장폐지분이 빠져 생존편향이 남아 있고,
  원 논문의 효과는 **소형·저커버리지 종목에서 강했다.** 여기서 안 나왔다는 것이
  한국 시장 전체에서 없다는 뜻은 아니다. 코스닥 소형주로는 재볼 만하다.
· 구간이 2022-02~2026-08(시즌 18개)로 짧다.
· 전체 문서를 비교했다. 논문은 섹션별로 맞춰 비교하는데, 한국 공시는 섹션 태그가
  일정하지 않아 그렇게 못 했다.

━━━ 이하 원래 설계(기록 보존) ━━━
**문서가 무엇을 말하나가 아니라, 작년 대비 무엇이 바뀌었나.**

v17에서 막힌 지점: 반기보고서 46종목을 다 뒤졌는데 계속기업 의문 0곳, 소송 언급
7곳이었다. **상용구는 매년 똑같기 때문이다.** 그런데 뒤집으면 — **똑같다는 사실
자체가 정보**다. 상용구가 아닌 부분만 골라내는 방법이 전년 동기 대비 변화량이다.

**근거.** Cohen·Malloy·Nguyen, *Lazy Prices* (Journal of Finance, 2020):
10-K/10-Q 문구를 전년 대비 많이 바꾼 기업이 이후 수익률이 나쁘다. 메커니즘은
"회사는 나쁜 소식이 있을 때만 문구를 손댄다"이고, 시장은 문서를 안 읽으므로
반영이 느리다. 미국 데이터에서 확인된 것이고 **한국 복제는 미지수다.**

**이 저장소에서 이게 특별한 이유 — 오염이 없다.**
지금까지 모든 LLM 실험은 "컷오프(2026-05) 이후 사건만"이라는 족쇄를 찼고 그래서
표본이 65건을 못 넘었다. **유사도 계산에는 LLM이 한 글자도 안 들어간다.** 순수
정량이라 2021~2026 전 구간을 그냥 백테스트할 수 있다.

**2단계 설계 — 공짜인 것부터.**
  1단계(여기): 코사인 유사도만으로 한국에 효과가 있나. **없으면 끝. LLM 안 씀.**
  2단계(1단계 통과 시에만): 바뀐 문구를 실제로 읽고 "악재성 변경인가 서식 변경인가"
       판정. 원 논문은 단어를 셀 뿐 **무엇이 바뀌었는지는 못 본다** — 30B 대비
       프런티어 모델이 이길 여지가 있는 유일한 지점이 거기다.
       대상은 2026-08 제출분(컷오프 이후 = 오염 0).

━━━ 사전 기준 (결과 보기 전에 고정한다) ━━━
**게이트 0 — 분산.** 한국 공시는 서식이 심하게 표준화돼 있다. 전년 대비 코사인
  유사도의 **사분위 범위(IQR)가 0.01 미만**이면 전부 똑같다는 뜻이고, 그러면
  줄 세울 것이 없으므로 **수익률은 보지도 않고 기각**한다. 이걸 먼저 본다.

**게이트 1 — 주 가설.** 기본 호라이즌은 **H+60**(논문의 효과는 몇 달에 걸친 드리프트
  이지 이벤트 점프가 아니다). 매 공시 시즌마다 유사도로 5분위를 만들고
  **최상위(안 바꾼 쪽) 롱 / 최하위(많이 바꾼 쪽) 숏**. 통과하려면 셋 다:
    (a) 롱숏 스프레드의 **중앙값 > 0** (평균이 아니라 중앙값 — 이 저장소 기준)
    (b) 5분위가 **단조**에 가까울 것(최상위 > 최하위, 뒤집힘 없음)
    (c) **비겹침 표본 t > 2.0** (분기 공시 + H+60이면 겹침이 적지만 그래도 분리해 센다)
  (a)만 통과는 우연, (a)+(b)만 통과는 표본 부족이다.

**부차 지표**(다중검정을 자백해 둔다): H+20/H+120, 자카드 유사도, 시가총액 분할.
  이들은 **판정 근거로 쓰지 않는다.** 주 가설이 죽으면 여기서 뭐가 나와도 죽은 것이다.

━━━ 편향 방어 ━━━
· **룩어헤드**: 공시는 장 마감 후 접수가 흔하다. 진입은 **접수일 다음 거래일 시가**.
· **마켓뉴트럴**: 개별 수익에서 같은 구간 유니버스 평균을 뺀다. 롱숏 스프레드는
  수학적으로 시장항이 상쇄되므로 유니버스 정의에 둔감하다(v6_audit에서 확인한 성질).
· **겹침**: H+60은 분기 공시 간격(약 63거래일)과 비슷해 겹침이 작다. 그래도 t는
  시즌별로 분리해 계산한다.
· **생존편향 — 완전 해결 못 함.** 유니버스가 *현재* KOSPI 대형주 150이라 상장폐지
  종목이 빠져 있다. 롱숏이라 방향성 편향은 줄지만 0은 아니다. **한계로 명시한다.**
· **정정공시 제외**: '정정' 들어간 보고서는 버린다(같은 기간 중복).
· **숫자 제거**: 재무 수치는 매년 반드시 바뀌므로 토큰화 전에 전부 지운다. 문구만 본다.

사용: python3 v18_lazy_prices.py fetch     # 유사도 계산(종목별 스트리밍, 재개 가능)
      python3 v18_lazy_prices.py disperse  # 게이트 0
      python3 v18_lazy_prices.py test      # 게이트 1
"""
import os
import re
import json
import math
import time
import pickle
import argparse
import urllib.parse
import urllib.request
from collections import Counter

import numpy as np
import pandas as pd

from dart_data import get_corp_map, fetch_document_text, _key, BASE
from v5_oos import CACHE

PX = os.path.join(CACHE, "trend_kospi_long.pkl")
SIM = os.path.join(CACHE, "v18_sim.pkl")

BGN, END = "20210101", "20260820"
TOPS = ("사업보고서", "반기보고서", "분기보고서")

# 숫자·기호를 지운다. 재무 수치는 해마다 반드시 바뀌므로 남기면 유사도가 전부
# 떨어져 신호가 아니라 잡음이 된다. 논문도 같은 처리를 한다.
_NUM = re.compile(r"[0-9,.\-()%\s]+")
_TOK = re.compile(r"[가-힣A-Za-z]{2,}")


def tokens(txt):
    """한글·영문 2자 이상 토큰만. 숫자와 구분자는 전부 버린다."""
    return _TOK.findall(txt)


def cosine(a, b):
    """단어 빈도 벡터 코사인. 논문의 주 지표."""
    if not a or not b:
        return np.nan
    keys = set(a) | set(b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return np.nan
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    return dot / (na * nb)


def jaccard(a, b):
    """집합 자카드. 빈도를 무시하므로 '문단이 통째로 새로 생겼나'에 민감하다."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return np.nan
    return len(sa & sb) / len(sa | sb)


def _season(nm):
    """'반기보고서 (2026.06)' → ('반기', '2026.06'). 같은 계절끼리만 비교한다.

    같은 계절끼리 비교해야 하는 이유: 사업보고서는 반기보고서보다 훨씬 길고 항목도
    다르다. 계절을 섞으면 '문서 종류가 달라서 생긴 차이'를 '회사가 문구를 바꿨다'로
    잘못 읽는다."""
    if "사업보고서" in nm:
        s = "사업"
    elif "반기보고서" in nm:
        s = "반기"
    elif "분기보고서" in nm:
        s = "분기"
    else:
        return None, None
    m = re.search(r"\((\d{4})\.(\d{2})\)", nm)
    return (s, f"{m.group(1)}.{m.group(2)}") if m else (s, None)


def _list_reports(corp_code):
    p = urllib.parse.urlencode({"crtfc_key": _key(), "corp_code": corp_code,
                                "bgn_de": BGN, "end_de": END, "pblntf_ty": "A",
                                "page_no": 1, "page_count": 100})
    try:
        with urllib.request.urlopen(BASE + "/list.json?" + p, timeout=25) as r:
            j = json.loads(r.read())
    except Exception:
        return []
    out = []
    for x in j.get("list", []):
        nm = x.get("report_nm", "")
        if "정정" in nm or not any(k in nm for k in TOPS):
            continue
        s, per = _season(nm)
        if not per:
            continue
        out.append({"rn": x["rcept_no"], "dt": x["rcept_dt"], "nm": nm,
                    "season": s, "period": per})
    return out


def cmd_fetch(args):
    """종목별 스트리밍. 본문은 저장하지 않고 **유사도 숫자만** 남긴다.

    150종목 × 23건 × 17만자 = 5억 자다. 다 들고 있으면 메모리가 터진다.
    한 종목의 문서만 메모리에 올려 그 안에서 전년 대비를 다 계산하고 버린다."""
    px = pickle.load(open(PX, "rb"))
    cmap = get_corp_map()
    done = pickle.load(open(SIM, "rb")) if os.path.exists(SIM) else {}
    codes = [c for c in px if c in cmap and c not in done]
    print(f"[v18] 유사도 계산 {len(codes)}종목 (완료 {len(done)})", flush=True)

    t0 = time.time()
    for i, code in enumerate(codes):
        reps = _list_reports(cmap[code])
        if len(reps) < 2:
            done[code] = []
            continue
        vec = {}
        for r in reps:
            try:
                txt = fetch_document_text(r["rn"], max_chars=10_000_000)
            except Exception:
                continue
            if not txt or len(txt) < 5000:
                continue
            vec[(r["season"], r["period"])] = (Counter(tokens(txt)), r, len(txt))
            time.sleep(0.03)

        recs = []
        for (season, per), (cnt, r, ln) in vec.items():
            y, m = per.split(".")
            prev = (season, f"{int(y)-1}.{m}")
            if prev not in vec:
                continue
            pc, pr, pl = vec[prev]
            recs.append({"code": code, "dt": r["dt"], "season": season,
                         "period": per, "prev_dt": pr["dt"],
                         "cos": cosine(cnt, pc), "jac": jaccard(cnt, pc),
                         "len": ln, "prev_len": pl,
                         "dlen": (ln - pl) / max(pl, 1)})
        done[code] = recs
        if (i + 1) % 10 == 0:
            pickle.dump(done, open(SIM, "wb"))
            el = time.time() - t0
            print(f"  {i+1}/{len(codes)} | {el/60:.1f}분 경과, "
                  f"남은 예상 {el/(i+1)*(len(codes)-i-1)/60:.0f}분", flush=True)
    pickle.dump(done, open(SIM, "wb"))
    n = sum(len(v) for v in done.values())
    print(f"[v18] 완료 {len(done)}종목 / 전년대비 쌍 {n}건")


def _load():
    d = pickle.load(open(SIM, "rb"))
    rows = [r for v in d.values() for r in v]
    df = pd.DataFrame(rows)
    if len(df):
        df["dt"] = pd.to_datetime(df["dt"], format="%Y%m%d")
    return df


def cmd_disperse(args):
    """게이트 0 — 줄 세울 만큼 흩어져 있나. 여기서 죽으면 수익률은 보지 않는다."""
    df = _load()
    print(f"\n  전년대비 쌍 {len(df)}건 / {df['code'].nunique()}종목 "
          f"/ {df['dt'].min().date()}~{df['dt'].max().date()}\n")
    print(f"  {'지표':<10}{'중앙값':>9}{'25%':>9}{'75%':>9}{'IQR':>9}"
          f"{'최소':>9}{'최대':>9}")
    print("  " + "-" * 64)
    ok = False
    for k in ("cos", "jac", "dlen"):
        s = df[k].dropna()
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        print(f"  {k:<10}{s.median():>9.4f}{q1:>9.4f}{q3:>9.4f}{q3-q1:>9.4f}"
              f"{s.min():>9.4f}{s.max():>9.4f}")
        if k == "cos" and (q3 - q1) >= 0.01:
            ok = True
    print(f"\n  ── 계절별 코사인 IQR ──")
    for s, g in df.groupby("season"):
        c = g["cos"].dropna()
        print(f"  {s:<6} n={len(c):<5} 중앙 {c.median():.4f} "
              f"IQR {c.quantile(.75)-c.quantile(.25):.4f}")
    print(f"\n  사전 기준: 코사인 IQR ≥ 0.01 → {'★통과' if ok else '기각(전부 똑같다)'}")


def _prices():
    px = pickle.load(open(PX, "rb"))
    cl = pd.DataFrame({c: v["df"]["Close"] for c, v in px.items()}).sort_index()
    op = pd.DataFrame({c: v["df"]["Open"] for c, v in px.items()}).sort_index()
    return op, cl


def cmd_test(args):
    """게이트 1 — 주 가설. 진입은 접수일 **다음 거래일 시가**(마감후 접수 방어).

    `--clean`: 전년 대비 문서 길이가 1.5배 넘게 변한 쌍을 버린다.
    **이 필터는 게이트 0 단계에서(수익률을 보기 전에) 의심해 둔 것이다** — 코사인
    최소 0.21, 길이 15배 같은 값이 나왔기 때문이다. 실제로 파보니 수집 실패는
    아니었고(5만자 미만 0건) **2022.12 사업보고서가 전 종목 일제히 4~5배로 늘어난
    규제성 변경**이었다. 그런 해에는 '문구를 바꿨다'가 회사 사정이 아니라 서식
    개정을 뜻하므로 신호가 아니라 잡음이다.
    ⚠️ 기각된 뒤에 돌리는 변형은 다중검정이다. **사전 기준 3개는 그대로 적용**하고,
    통과하더라도 '결과'가 아니라 **새 표본이 필요한 가설**로만 취급한다."""
    df = _load().dropna(subset=["cos"])
    if args.clean:
        r = df["len"] / df["prev_len"]
        keep = (r <= 1.5) & (r >= 1 / 1.5)
        print(f"  [clean] 길이 1.5배 초과 변동 {int((~keep).sum())}건 제외 "
              f"({100*(~keep).mean():.1f}%)")
        df = df[keep]
    op, cl = _prices()
    idx = cl.index

    for H in (20, 60, 120):
        rows = []
        for _, r in df.iterrows():
            pos = idx.searchsorted(r["dt"], side="right")   # 접수일 다음 거래일
            if pos + H >= len(idx) or r["code"] not in cl.columns:
                continue
            e = op.iloc[pos].get(r["code"], np.nan)
            x = cl.iloc[pos + H].get(r["code"], np.nan)
            if not (e > 0) or not (x > 0):
                continue
            # 같은 구간 유니버스 평균 = 시장항. 개별에서 빼 마켓뉴트럴로 만든다.
            mkt = (cl.iloc[pos + H] / op.iloc[pos] - 1).replace(
                [np.inf, -np.inf], np.nan).median()
            rows.append({"dt": r["dt"], "season": r["season"], "code": r["code"],
                         "cos": r["cos"], "jac": r["jac"],
                         "ret": (x / e - 1) * 100 - mkt * 100})
        R = pd.DataFrame(rows)
        if len(R) < 50:
            print(f"\n  H+{H}: 표본 {len(R)}건 — 부족")
            continue

        # 공시 시즌(접수 월 기준)마다 독립적으로 5분위를 만든다
        R["ss"] = R["dt"].dt.to_period("M").astype(str)
        R["q"] = R.groupby("ss")["cos"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=False)
            if s.nunique() >= 5 else np.nan)
        R = R.dropna(subset=["q"])
        tag = "★주 가설" if H == 60 else "부차"
        print(f"\n  ══ H+{H} ({tag}) | 표본 {len(R)}건, 시즌 {R['ss'].nunique()}개 ══")
        print(f"  {'분위':<22}{'중앙 초과%':>11}{'평균%':>9}{'n':>7}")
        print("  " + "-" * 50)
        med = {}
        for q, g in R.groupby("q"):
            lab = {0: "Q1 많이 바꿈(숏)", 4: "Q5 안 바꿈(롱)"}.get(int(q), f"Q{int(q)+1}")
            med[int(q)] = g["ret"].median()
            print(f"  {lab:<22}{g['ret'].median():>+11.2f}"
                  f"{g['ret'].mean():>+9.2f}{len(g):>7}")

        # 시즌별 스프레드 → 비겹침에 가까운 표본으로 t를 낸다
        sp = []
        for ss, g in R.groupby("ss"):
            hi, lo = g[g["q"] == 4]["ret"], g[g["q"] == 0]["ret"]
            if len(hi) >= 3 and len(lo) >= 3:
                sp.append(hi.median() - lo.median())
        sp = np.array(sp)
        spread = med.get(4, np.nan) - med.get(0, np.nan)
        t = sp.mean() / (sp.std(ddof=1) / math.sqrt(len(sp))) if len(sp) > 2 else np.nan
        mono = med.get(4, -9) > med.get(0, 9)
        print(f"  롱숏 스프레드(중앙) {spread:+.2f}%p | 시즌 {len(sp)}개 t={t:.2f}")
        if H == 60:
            print(f"  사전 기준 (a)중앙>0 {'O' if spread>0 else 'X'} "
                  f"(b)Q5>Q1 {'O' if mono else 'X'} "
                  f"(c)t>2.0 {'O' if t>2.0 else 'X'}"
                  f"  → {'★통과' if (spread>0 and mono and t>2.0) else '기각'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "disperse", "test"])
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "disperse": cmd_disperse, "test": cmd_test}[a.cmd](a)
