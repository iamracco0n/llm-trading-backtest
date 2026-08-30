# -*- coding: utf-8 -*-
"""한국 소형주 추세추종 — 포워드 페이퍼 (젯슨 배포용). **실주문 없음.**

━━━ 왜 포워드밖에 안 남았나 ━━━
백테스트로는 더 알아낼 것이 없다. 2025-01~2026-07 봉인 구간을 이미 아홉 번 넘게
열었고(v23 1회, v24 두 자본 2회, 교차검증 6회), 아홉 번 본 구간은 홀드아웃이 아니라
두 번째 IS 다. 파라미터도 v25 의 maximin 으로 IS 안에서만 골랐다.
**이 설정이 진짜인지 아닌지는 이제 앞으로 쌓이는 기록으로만 알 수 있다.**

━━━ 규칙 (v25 maximin 선정, 고정) ━━━
    유니버스  KOSPI+KOSDAQ, 20일 평균 거래대금 **30억 이상**
    진입      직전 **60봉** 고가 돌파  그리고  종가 > **MA120**
              후보는 **20일 모멘텀** 순, 슬롯 **3개**
    청산      샹들리에 트레일링 — 보유 중 최고가 − **4.0 × ATR14**
    국면      KOSPI > MA20 일 때만 신규 매수 (아니면 현금)
    비용      왕복 0.23% (수수료 0.015×2 API 실측 + 매도 거래세 0.20%)
    자본      **100,000원** (총 20만 중 한국 10만 / 미국 10만 배분). **1주 단위**이므로
              슬롯 금액(33,333원)으로 1주도 못 사는 종목은 후보에서 제외한다.

⚠️ 파라미터를 **절대 바꾸지 않는다.** 포워드 도중에 손대면 그 순간 이 기록은
   백테스트로 되돌아간다. 바꾸고 싶으면 새 태그로 따로 시작한다.

━━━ 사전 기준 (기록이 쌓이기 **전에** 고정한다) ━━━
6개월(약 120거래일) 또는 거래 30건 중 나중에 오는 시점에 판정한다:
  (a) 거래당 평균 순수익 > **0.23%** (비용을 넘는가)
  (b) 누적수익 > **같은 구간 KOSPI**
  (c) MDD > **−35%** (백테스트 −30.6% 보다 크게 나빠지지 않는가)
  (d) 거래 **30건 이상**
넷 다여야 실전 투입을 검토한다. 하나라도 미달이면 접는다.

**백테스트 기대치**(비교 기준): OOS 구간 기준 SR 1.5 내외, MDD −30% 내외,
거래당 +15% 내외, 6개월에 약 12~15거래. 포워드가 여기 근처면 진짜일 가능성이 크고,
크게 벌어지면 생존편향·슬리피지가 백테스트를 부풀렸다는 뜻이다.

━━━ 알려진 약점 (포워드가 답을 줄 것들) ━━━
· **생존편향** — 백테스트 유니버스가 '오늘 살아있는 종목'이라 상장폐지분이 없다.
  코스닥이 172종목 들어가 특히 취약하다. 포워드에는 이 편향이 없다.
· **슬리피지 0 가정** — 소형주는 호가가 넓다. 포워드는 다음날 시가로 기록하므로
  실제 체결과의 차이가 그대로 드러난다.

사용: python3 kr_smallcap_paper.py            # 하루 1회 (cron, 장 마감 후)
      python3 kr_smallcap_paper.py --report   # 현황만
"""
import argparse
import datetime as dt
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cache", "kr_smallcap_state.json")

# v25 maximin 선정 — 고정
DC_ENTRY, MA_TREND, CHAND, MOM, SLOTS, REGIME_MA = 60, 120, 4.0, 20, 3, 20
ATR_N = 14
MIN_AMT = 3e9
FETCH_DEADLINE = 180        # 초. 이 시간이 지나면 도착한 것만으로 진행
COST = 0.23
# 실제 계좌 잔고에 맞춘다. 실행할 수 없는 자본으로 페이퍼를 돌리면
# 그 기록은 실전 판단에 못 쓴다(v24 에서 자본에 따라 결과가 갈리는 것을 확인했다).
# 잔고가 크게 바뀌면 여기를 바꾸되, 바꾼 날짜를 상태파일에 남기고 그 전후를
# 한 계열로 이어 붙이지 않는다.
CAP = 100_000


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"start": dt.date.today().isoformat(), "cash": float(CAP),
            "pos": {}, "closed": [], "equity": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


UNIV_CACHE = os.path.join(HERE, "cache", "kr_smallcap_universe.json")
UNIV_MAX_AGE = 30          # 일. 유니버스는 천천히 변한다


def universe():
    """유동성 스크리닝된 유니버스. **캐시를 쓰고, 오래됐을 때만 갱신한다.**

    ⚠️ `fdr.StockListing("KRX")` 가 젯슨에서 비-JSON 응답으로 죽는다(KRX 엔드포인트가
    불안정하다 — 지수 조회가 LOGOUT 을 뱉는 것과 같은 계열). 매 실행마다 2,700종목
    목록을 새로 받을 이유도 없다. 유니버스는 한 달에 한 번 바뀔까 말까다.

    그래서: 캐시가 있고 30일 이내면 그대로 쓴다. 갱신에 실패해도 **낡은 캐시로
    계속 돈다** — 유니버스가 조금 낡는 것보다 그날 기록이 통째로 비는 게 나쁘다.
    (2026-08-28 에 장투 cron 이 정확히 그렇게 하루를 날렸다.)"""
    import time

    cached, age = None, 1e9
    if os.path.exists(UNIV_CACHE):
        try:
            j = json.load(open(UNIV_CACHE, encoding="utf-8"))
            cached = [(x[0], x[1]) for x in j["codes"]]
            age = (dt.date.today() - dt.date.fromisoformat(j["date"])).days
        except Exception:
            cached = None
    if cached and age <= UNIV_MAX_AGE:
        print(f"  유니버스 캐시 사용 ({len(cached)}종목, {age}일 전)")
        return cached

    import FinanceDataReader as fdr
    for attempt in range(3):
        try:
            df = fdr.StockListing("KRX")
            d = df[df["Market"].isin(["KOSPI", "KOSDAQ"])]
            d = d.dropna(subset=["Close", "Amount"])
            d = d[d["Amount"] >= MIN_AMT]          # 1차 유동성 스크리닝
            out = [(str(c), str(n)) for c, n in zip(d["Code"], d["Name"])]
            if out:
                os.makedirs(os.path.dirname(UNIV_CACHE), exist_ok=True)
                json.dump({"date": dt.date.today().isoformat(), "codes": out},
                          open(UNIV_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                print(f"  유니버스 갱신 {len(out)}종목")
                return out
        except Exception as e:
            print(f"  유니버스 갱신 실패({attempt+1}/3): {type(e).__name__}", flush=True)
        time.sleep(3 * (attempt + 1))

    if cached:
        print(f"  ⚠️ 갱신 실패 — 낡은 캐시로 계속 진행 ({len(cached)}종목, {age}일 전)")
        return cached
    raise RuntimeError("유니버스를 못 만들었다(캐시도 없음). 오늘은 기록하지 않는다.")


def hist(code, days=400):
    import FinanceDataReader as fdr
    end = dt.date.today()
    return fdr.DataReader(code, (end - dt.timedelta(days=days)).isoformat(),
                          end.isoformat())


def indicators(d):
    hi, lo, cl = d["High"], d["Low"], d["Close"]
    pc = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return {"close": float(cl.iloc[-1]), "high": float(hi.iloc[-1]),
            "atr": float(tr.rolling(ATR_N).mean().iloc[-1]),
            "dc": float(hi.rolling(DC_ENTRY).max().shift(1).iloc[-1]),
            "ma": float(cl.rolling(MA_TREND).mean().iloc[-1]),
            "mom": float(cl.iloc[-1] / cl.iloc[-1 - MOM] - 1) if len(cl) > MOM else np.nan,
            "amt": float((cl * d["Volume"]).rolling(20).mean().iloc[-1])}


def regime_on():
    """국면 판정용 지수. **재시도 + 대체 소스**를 둔다.

    ⚠️ KRX 지수 엔드포인트(KS11)가 `ValueError: LOGOUT` 을 뱉는 일이 잦다. 젯슨의
    2026-08-28 장투 cron 이 통째로 유실된 것도 같은 계열의 실패였다(재시도가 없었다).
    한 번 실패로 그날 기록이 날아가면 포워드의 값어치가 깎이므로:
      1) KS11 을 3회까지 재시도(2·4·6초 대기)
      2) 그래도 안 되면 **KODEX 200(069500)** 을 대체로 쓴다 — 일반 종목이라
         다른 엔드포인트를 타므로 같이 죽지 않는다.
    KOSPI 와 KOSPI200 은 MA20 상/하 판정에서 대부분 일치하지만 완전히 같지는 않다.
    그래서 **어느 소스를 썼는지 반환해 기록에 남긴다** — 나중에 결과를 볼 때
    '그날은 대체 소스였다'를 알 수 있어야 한다.
    둘 다 실패하면 **아무것도 하지 않는다** — 국면을 모르는 채 매매하느니 건너뛴다."""
    import time

    import FinanceDataReader as fdr
    since = (dt.date.today() - dt.timedelta(days=300)).isoformat()
    for attempt in range(3):
        try:
            ks = fdr.DataReader("KS11", since)["Close"].dropna()
            if len(ks) > REGIME_MA:
                return (bool(ks.iloc[-1] > ks.rolling(REGIME_MA).mean().iloc[-1]),
                        float(ks.iloc[-1]), "KS11")
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    try:
        et = fdr.DataReader("069500", since)["Close"].dropna()
        if len(et) > REGIME_MA:
            return (bool(et.iloc[-1] > et.rolling(REGIME_MA).mean().iloc[-1]),
                    float(et.iloc[-1]), "KODEX200(대체)")
    except Exception:
        pass
    raise RuntimeError("국면 판정 실패 — KS11/KODEX200 모두 조회 불가. "
                       "오늘은 기록하지 않는다.")


def main(args):
    st = load_state()
    today = dt.date.today().isoformat()
    print(f"===== 한국 소형주 추세추종 포워드  {today} (시작 {st['start']}) =====")
    print(f"  규칙 고정: DC{DC_ENTRY} MA{MA_TREND} 샹들리에{CHAND}xATR "
          f"모멘텀{MOM} 슬롯{SLOTS} 국면MA{REGIME_MA}")

    on, ks_px, src = regime_on()
    print(f"  지수({src}) {ks_px:,.1f} → 국면 "
          f"{'위험선호' if on else '위험회피(신규매수 중단)'}")

    uni = universe()
    slot = CAP / SLOTS
    # ⚠️ 순차 조회는 종목당 ~7초(대부분 네트워크 대기)라 434종목에 50분이 넘었다.
    # 매일 도는 cron 이 50분을 먹으면 안 되고, 진행 표시가 없어 멈춘 건지 도는 건지
    # 구분도 안 됐다. 스레드로 병렬 조회하고 진행을 찍는다.
    # CPU 가 아니라 I/O 대기이므로 GIL 이 문제되지 않는다.
    ind, cands = {}, []
    done_n = [0]

    def fetch(item):
        code, name = item
        try:
            d = hist(code)
            if len(d) < MA_TREND + 30:
                return None
            return code, name, indicators(d)
        except Exception:
            return None

    # ⚠️ `ex.map` 은 느린 요청 하나가 매달리면 전체가 멈춘다. 실제로 300/434 에서
    # 무한 대기했다. 매일 도는 cron 이 그러면 안 되므로 **마감시한**을 두고
    # 도착한 것만으로 진행한다 — 유니버스의 95% 만 봐도 신호는 거의 같고,
    # 그날 기록이 통째로 비는 것보다 훨씬 낫다.
    print(f"  유니버스 {len(uni)}종목 병렬 조회 (마감 {FETCH_DEADLINE}초)...", flush=True)
    t0 = time.time()
    ex = ThreadPoolExecutor(max_workers=8)
    futs = {ex.submit(fetch, it): it for it in uni}
    try:
        for fu in as_completed(futs, timeout=FETCH_DEADLINE):
            done_n[0] += 1
            if done_n[0] % 100 == 0:
                el = time.time() - t0
                print(f"    {done_n[0]}/{len(uni)}  {el:.0f}초", flush=True)
            try:
                r = fu.result(timeout=1)
            except Exception:
                continue
            if not r:
                continue
            code, name, x = r
            ind[code] = (name, x)
            if x["amt"] < MIN_AMT or np.isnan(x["mom"]) or np.isnan(x["atr"]):
                continue
            if x["close"] > x["dc"] and x["close"] > x["ma"] and x["close"] <= slot:
                cands.append((x["mom"], code, name, x["close"]))
    except TimeoutError:
        print(f"  ⚠️ 마감시한 도달 — {done_n[0]}/{len(uni)} 까지만 반영", flush=True)
    for fu in futs:
        fu.cancel()
    ex.shutdown(wait=False)
    got = len(ind)
    print(f"  조회 완료 {got}/{len(uni)}종목  {time.time()-t0:.0f}초", flush=True)
    if got < len(uni) * 0.7:
        raise RuntimeError(f"유니버스의 {100*got/len(uni):.0f}% 만 조회됐다. "
                           f"신호가 왜곡되므로 오늘은 기록하지 않는다.")

    # ── 청산 (트레일링 이탈) ─────────────────────────────
    closed_now = []
    for code in list(st["pos"]):
        if code not in ind:
            continue
        name, x = ind[code]
        p = st["pos"][code]
        p["peak"] = max(p["peak"], x["high"])
        if x["close"] <= p["peak"] - CHAND * x["atr"]:
            proceeds = p["qty"] * x["close"] * (1 - COST / 100)
            st["cash"] += proceeds
            r = (x["close"] / p["entry"] - 1) * 100 - COST
            closed_now.append({"code": code, "name": name, "ret": round(r, 2),
                               "in": p["date"], "out": today})
            print(f"  ▣ 청산 {name} {r:+.2f}%")
            del st["pos"][code]
    st["closed"] += closed_now

    # ── 진입 ────────────────────────────────────────────
    if on and not args.report:
        cands.sort(reverse=True)
        for mom, code, name, px in cands:
            if len(st["pos"]) >= SLOTS or st["cash"] < px:
                break
            if code in st["pos"]:
                continue
            qty = int(min(slot, st["cash"]) // px)
            if qty < 1:
                continue
            st["cash"] -= qty * px
            st["pos"][code] = {"qty": qty, "entry": px, "peak": px, "date": today,
                               "name": name}
            print(f"  ▶ 매수 {name} {qty}주 @{px:,.0f} (모멘텀 {mom*100:+.1f}%)")

    mv = st["cash"] + sum(p["qty"] * ind[c][1]["close"]
                          for c, p in st["pos"].items() if c in ind)
    print(f"\n  돌파 후보 {len(cands)}개 | 보유 {len(st['pos'])}/{SLOTS}")
    for c, p in st["pos"].items():
        cur = ind[c][1]["close"] if c in ind else p["entry"]
        print(f"    {p['name'][:12]:<12} {p['qty']}주 @{p['entry']:,.0f} → "
              f"{cur:,.0f} ({(cur/p['entry']-1)*100:+.1f}%)")
    print(f"  평가액 {mv:,.0f}원 ({(mv/CAP-1)*100:+.2f}%)")
    if st["closed"]:
        r = [c["ret"] for c in st["closed"]]
        print(f"  청산 {len(r)}건 | 거래당 평균 {np.mean(r):+.2f}% "
              f"중앙값 {np.median(r):+.2f}% | 승률 {100*np.mean([x>0 for x in r]):.0f}%")
        print(f"  ※ 판정에는 거래 30건 이상 필요 — 현재 {len(r)}건")

    if not args.report:
        st["equity"].append([today, round(mv, 0)])
        save_state(st)
    print("  실주문 없음(페이퍼).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    main(ap.parse_args())
