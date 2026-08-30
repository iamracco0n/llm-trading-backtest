# -*- coding: utf-8 -*-
"""실전 전환 전 점검 — **승인 직전에 이것부터 돌린다.**

토스 Open API 에는 샌드박스가 없다. 코드를 시험하는 순간이 곧 실주문이므로,
"켜기 전에 확인할 것"을 사람이 기억에 의존하지 않도록 목록으로 박아 둔다.
하나라도 빨간불이면 켜지 않는다.

점검 항목
  1. 인증 — 토큰이 실제로 나오는가
  2. 등록 IP — 지금 나가는 공인 IP 가 토스에 등록한 값과 같은가
     (토스는 IP 화이트리스트다. 바뀌면 인증이 엉뚱한 에러로 실패한다)
  3. 계좌·잔고 — 주문가능 현금이 설정 자본과 맞는가
  4. 수수료 — API 가 주는 실제 요율(가정 금지)
  5. 안전장치 — TOSS_LIVE / 1회 한도 / DryRun 이 의도대로 걸리는가
  6. 장 운영 — 오늘이 거래일인가, 지금이 장중인가
  7. 포워드 기록 — 페이퍼가 며칠 쌓였고 사전 기준까지 얼마나 남았나

사용: python3 preflight.py
"""
import datetime as dt
import json
import os

EXPECT_IP = os.environ.get("TOSS_EXPECT_IP", "103.218.162.176")
CAP = 200_000
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "cache", "kr_smallcap_state.json")

OK, BAD, WARN = "  [OK]  ", "  [!!]  ", "  [~]   "
issues = []


def check(name, ok, detail, fatal=True):
    print(f"{OK if ok else (BAD if fatal else WARN)}{name:<22}{detail}")
    if not ok and fatal:
        issues.append(name)


print("=" * 68)
print(f"  실전 전환 전 점검  {dt.datetime.now():%Y-%m-%d %H:%M}")
print("=" * 68)

# 1~5 API 계열
try:
    from toss_trade import Toss, public_ip
    t = Toss()
    check("1. 인증", True, f"토큰 발급 OK · 계좌 seq={t.seq}")

    ip = public_ip()
    check("2. 등록 IP", ip == EXPECT_IP,
          f"현재 {ip or '조회실패'} / 등록 {EXPECT_IP}"
          + ("" if ip == EXPECT_IP else "  ← 토스 설정에서 IP 갱신 필요"))

    bp = float(t.buying_power("KRW")["cashBuyingPower"])
    h = t.holdings()
    mv = h.get("marketValue", {}).get("amount", {}).get("krw")
    check("3. 잔고", bp >= CAP * 0.95,
          f"주문가능 {bp:,.0f}원 / 설정자본 {CAP:,}원 · 보유주식 {mv}원")

    c = t.commission("KR")
    check("4. 수수료", c is not None,
          f"편도 {c*100:.3f}% → 왕복+거래세 {c*2*100 + 0.20:.3f}%")

    d = t.buy("005930", 1)
    blocked = isinstance(d, dict) and d.get("blocked_by")
    check("5. 안전장치", bool(blocked),
          f"DryRun 차단 사유 {blocked}" if blocked
          else "⚠️ 차단되지 않았다 — 주문이 나갈 수 있는 상태다")
except Exception as e:
    check("1~5. API", False, f"{type(e).__name__}: {str(e)[:80]}")

# 6. 장 운영
now = dt.datetime.now()
is_weekday = now.weekday() < 5
in_session = is_weekday and dt.time(9, 0) <= now.time() <= dt.time(15, 30)
check("6. 장 운영", is_weekday,
      f"{'평일' if is_weekday else '주말/휴일'} · "
      f"{'정규장 중' if in_session else '장외'}"
      + ("" if in_session else "  ← 주문은 장중에만"), fatal=False)

# 7. 포워드 기록
if os.path.exists(STATE):
    st = json.load(open(STATE, encoding="utf-8"))
    eq = st.get("equity", [])
    cl = st.get("closed", [])
    days = len(eq)
    check("7. 포워드 기록", days >= 120 and len(cl) >= 30,
          f"{days}일 / 거래 {len(cl)}건 "
          f"(사전 기준: 120일 **그리고** 30건)", fatal=False)
    if days < 120 or len(cl) < 30:
        print(f"        └ 아직 판정 시점이 아니다. 지금 실전 전환은 "
              f"**백테스트 근거만으로** 하는 것이다.")
else:
    check("7. 포워드 기록", False, "상태파일 없음 — 페이퍼가 아직 안 돌았다",
          fatal=False)

print("\n" + "=" * 68)
if issues:
    print(f"  ❌ 치명 항목 {len(issues)}개: {', '.join(issues)}")
    print("  → 고치기 전에는 켜지 않는다.")
else:
    print("  ✅ 치명 항목 없음. 기술적으로는 켤 수 있는 상태다.")
    print("  단, 위 7번이 '판정 시점 아님'이면 그것은 **투자 판단의 문제**이지")
    print("  기술의 문제가 아니다. 켤지 말지는 사람이 정한다.")
