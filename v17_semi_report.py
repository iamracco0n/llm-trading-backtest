# -*- coding: utf-8 -*-
"""v17 — **기각. 모델이 아니라 전제가 틀렸다.**

━━━ 결론 먼저 ━━━
반기보고서를 읽혀 판정을 개선하려 했으나 **판정할 서술이 애초에 없다.** 46종목 실측:

    계속기업 의문·중요한 불확실성 …  0/46
    소송 청구금액 언급 ………………  7/46
    과징금·시정명령·행정처분 ………  5/46
    "계류중인 소송 없음" 상용구 ……  5/46

원문은 종목당 14만~26만 자인데 **대부분 재무제표와 주석 표**다. 태그를 벗기면
숫자 나열이 된다. 이유 셋:
  1. **규정상 MD&A가 없다.** 본문에 명시돼 있다 — "분/반기 보고서에는 이사의
     경영진단 및 분석의견을 기재하지 않습니다." 기대한 경영진 서술이 안 들어간다.
  2. 반기보고서는 사실상 **재무제표 패키지**다.
  3. 대상이 중견·대형 상장사라 **계속기업 의문이 0곳**이다. 그 신호가 뜨는 회사는
     실적공시 유니버스에 잘 들어오지 않는다.

**이건 모델의 실패가 아니라 문서 선택의 실패다.** 동시에 v8에서 Opus와 gemma4:31b가
84.6% 일치한 이유도 설명한다 — **한국 공시 체계 자체가 정형·수치 중심**이라 어떤
문서를 골라도 30B가 포화된 영역이 된다. "입력 형태를 바꿔도 안 된다"에 네 번째
사례(장문 문서)가 붙되, **이번 실패 원인은 데이터에 있다.**

MD&A가 있는 것은 **사업보고서(연간, 3월 제출)**인데 FY2025분은 2026-03 제출이라
**컷오프(2026-05) 이전 = 오염**이다. 그래서 이 경로로는 되살릴 수 없다.

→ 후속: `v18_lazy_prices.py`. "무엇이 쓰여 있나"가 아니라 **"작년 대비 무엇이
   바뀌었나"**를 본다. 바뀐 부분은 상용구가 아니고, 유사도 계산에는 LLM이 필요
   없으므로 **오염 없이 백테스트할 수 있다.**

━━━ 이하 원래 설계(기록 보존) ━━━
**반기보고서 본문**을 읽고 판정한다. 프런티어 모델이 실제로 필요한 첫 과제.

**지금까지 준 것은 표 한 장이었다.** v8(공시 본문)·v9(본문+수치)·v10~v12(숫자 스냅샷)
전부 정형·수치 입력이라 30B가 이미 포화된 영역이었고, 실제로 Opus와 gemma4:31b의
판정 일치율이 **84.6%**였다. **저를 못 쓴 게 아니라 안 써도 되는 문제만 준 것이다.**

**반기보고서는 다르다.** 종목당 **14만~26만 자**의 비정형 문서이고, 표에 절대 없는
것들이 서술형으로 들어 있다:
  · 우발부채·소송·제재 — 진행 중인 소송의 청구금액과 회사의 방어 논리
  · 계속기업 관련 중요한 불확실성 — 감사인이 명시하는 존속 위험
  · 특수관계자 거래 — 자금 대여·지급보증의 규모와 상대
  · 담보·차입 — 자산이 얼마나 묶여 있나

**설계 — 변수는 '입력 문서' 하나**
  · 대상: v8과 **같은 46종목**(2026-08 제출 반기보고서, 컷오프 이후 = 오염 0)
  · 대조군: v8 텍스트 전용 판정(이미 봉인됨)
  · 실험군: 같은 판정 + **반기보고서 리스크 섹션**을 보고 조정
  · 전체를 다 넣을 수 없으므로(46종목 870만 자) **키워드 창으로 섹션만 추출**한다.

**사전 기준(결과 보기 전 고정)**: 실험군이 대조군을 **H+20·H+40 둘 다에서 이겨야**
"비정형 장문을 읽으면 나아진다"가 성립한다. 못 넘으면 **입력 형태를 바꿔도 안 된다**는
결론이 하나 더 붙는다(수치만·텍스트만·텍스트+수치·장문 = 넷 다 실패).

사용: python3 v17_semi_report.py extract    # 리스크 섹션 추출(캐시)
      python3 v17_semi_report.py show
      python3 v17_semi_report.py save --file j.json
"""
import os
import re
import json
import pickle
import argparse
import datetime as dt

from dart_data import fetch_document_text
from v5_oos import CACHE
from v8_forward_claude import EV, JG

SEMI = os.path.join(CACHE, "v17_semi.pkl")
SEC = os.path.join(CACHE, "v17_sections.pkl")
OUT = os.path.join(CACHE, "v17_judgments.json")

# 표에는 없고 본문에만 있는 것들. 각 키워드 주변 창을 떠낸다.
# ⚠️ 1차 추출은 거의 숫자 표만 잡았다. 그리고 본문에서 결정적인 것을 발견했다 —
# **"분/반기 보고서에는 이사의 경영진단 및 분석의견을 기재하지 않습니다"**
# 즉 **반기보고서에는 MD&A가 규정상 빠진다.** 전제의 큰 축이 틀렸다.
# 남은 서술형은 소송·제재·우발부채 주석뿐이므로 그것만 정확히 겨냥하고,
# **숫자 밀도가 높은 창은 버린다**(표를 태그 제거하면 숫자 나열이 된다).
KEYS = [
    ("소송·분쟁", ["계류 중인 소송", "계류중인 소송", "소송사건", "손해배상청구",
                 "피고로", "원고로"]),
    ("제재·위반", ["제재현황", "행정처분", "과징금", "시정명령", "고발"]),
    ("우발부채·보증", ["우발부채", "지급보증", "채무보증", "견질"]),
    ("계속기업 의문", ["계속기업으로서의 존속능력", "중요한 불확실성"]),
]


def _numeric_ratio(t):
    """숫자·구분자 비율. 표를 평문화하면 0.5를 훌쩍 넘는다."""
    if not t:
        return 1.0
    n = sum(ch.isdigit() or ch in ",.()- " for ch in t)
    return n / len(t)
WIN = 700          # 키워드 앞뒤로 떠낼 글자수
CAP = 3200         # 종목당 상한


def cmd_extract(args):
    semi = pickle.load(open(SEMI, "rb"))
    sec = pickle.load(open(SEC, "rb")) if os.path.exists(SEC) else {}
    todo = [c for c in semi if c not in sec]
    print(f"[v17] 리스크 섹션 추출 {len(todo)}종목 (캐시 {len(sec)})")
    for i, code in enumerate(todo):
        rn, nm = semi[code]
        try:
            txt = fetch_document_text(rn, max_chars=10_000_000)
        except Exception:
            continue
        if not txt:
            continue
        parts, used = [], 0
        for label, kws in KEYS:
            found = []
            for kw in kws:
                for m in re.finditer(re.escape(kw), txt):
                    s = max(0, m.start() - WIN // 3)
                    w = txt[s:s + WIN]
                    if _numeric_ratio(w) > 0.55:   # 숫자 표는 버린다
                        continue
                    found.append(w)
                    break                      # 키워드당 첫 등장만
            if found:
                blob = " … ".join(found)[:CAP // len(KEYS)]
                parts.append(f"[{label}] {blob}")
                used += len(blob)
        sec[code] = {"rn": rn, "len": len(txt), "text": "\n".join(parts)[:CAP]}
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(todo)}", flush=True)
            pickle.dump(sec, open(SEC, "wb"))
    pickle.dump(sec, open(SEC, "wb"))
    avg = sum(len(v["text"]) for v in sec.values()) / max(len(sec), 1)
    print(f"[v17] 완료 {len(sec)}종목 | 원문 평균 "
          f"{sum(v['len'] for v in sec.values())//max(len(sec),1):,}자 → "
          f"추출 평균 {avg:,.0f}자")


def cmd_show(args):
    sec = pickle.load(open(SEC, "rb"))
    ev = pickle.load(open(EV, "rb"))
    A = json.load(open(JG, encoding="utf-8"))
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    codes = [c for c in sec if c not in done]
    print(f"### 남은 {len(codes)}종목 중 {min(args.n, len(codes))}\n")
    for code in codes[:args.n]:
        evs = ev.get(code, [])
        prev = [f"{A[rn]['verdict']}({A[rn]['score']})" for _, rn, _ in evs if rn in A]
        print(f"===== {code} | 반기보고서 원문 {sec[code]['len']:,}자")
        print(f"  [기존 공시 판정] {', '.join(prev) if prev else '없음'}")
        print(sec[code]["text"])
        print()


def cmd_save(args):
    new = json.load(open(args.file, encoding="utf-8"))
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    add = 0
    for k, v in new.items():
        if k in done:
            continue
        v["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        done[k] = v
        add += 1
    json.dump(done, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[v17] 신규 {add}건, 누적 {len(done)}건")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "show", "save"])
    ap.add_argument("-n", type=int, default=15)
    ap.add_argument("--file")
    a = ap.parse_args()
    {"extract": cmd_extract, "show": cmd_show, "save": cmd_save}[a.cmd](a)
