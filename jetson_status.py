# -*- coding: utf-8 -*-
"""젯슨에서 돌아가는 페이퍼 투자 전부의 현황. **경로를 반드시 같이 본다.**

━━━ 왜 이 스크립트가 따로 있나 ━━━
2026-08-29에 코인봇을 "14일 내내 현금, 거래 0건, 수익 0.00%"라고 잘못 보고했다.
자산곡선의 **처음과 끝만** 봤는데 하필 둘 다 150,000원이었기 때문이다. 실제로는
8/22에 175,396원(+16.93%)까지 갔다가 되돌린 것이었고, 거래도 23건 있었다.

  8/16  150,000   ← 시작
  8/22  175,396   ← 최고점 (+16.93%)   ‥‥ 여기를 못 봤다
  8/29  150,000   ← 끝. 시작과 같아서 "아무 일도 없었다"로 읽혔다

바로 전날 v19에서 "MDD는 실현된 경로이고 양끝 수익률로는 안 보인다"를 정리해놓고
같은 실수를 했다. 그래서 **양끝만 찍는 것이 애초에 불가능하도록** 만든다 —
자산곡선을 다루는 함수는 최고점·최저점·고점대비·MDD를 항상 함께 반환한다.

━━━ 무엇을 더 보나 ━━━
· **기록의 구멍**: 2026-08-28에 세 cron 이 전부 데이터 수집에 실패해 하루가 통째로
  날아갔다(재시도 로직이 없다). 영업일 기준으로 빠진 날을 세어 경고한다.
· **거래 로그와 자산곡선을 따로 본다**: 코인봇은 `_record_equity` 가 고장나 있어
  8/16 이전 거래가 자산곡선에 없다. 둘을 한 숫자로 뭉뚱그리면 그 사실이 가려진다.

사용: python3 jetson_status.py        (젯슨에서 실행)
"""
import datetime as dt
import json
import os

B = "/home/user/llm-trading-backtest"
X = "/home/user/xavier_nx_ai"


def _load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
            return json.loads(t) if t else d
    except Exception:
        return d


def path_stats(pairs, pct_points=False):
    """자산곡선 → **경로 통계**. 시작/끝만 주는 반환값은 만들지 않는다.

    pairs: [(날짜문자열, 값), ...] 시간순.
    이 함수가 이 파일의 존재 이유다 — 호출부가 양끝만 보고 싶어도 못 보게,
    최고점·최저점·고점대비·MDD를 항상 같이 돌려준다.

    ⚠️ `pct_points=True` 는 값이 **잔고가 아니라 누적 %p** 인 계열용이다
    (`ls_paper_state.json` 이 그렇다). 이걸 안 주고 비율로 나누면 터무니없는 값이
    나온다 — 실제로 이 스크립트 첫 실행에서 크립토 롱숏이 **+338%** 로 찍혔다
    (4.21 ÷ 0.96 − 1). 시작값이 0 근처인 계열을 비율로 다루면 항상 이렇게 된다.
    %p 계열은 `1 + v/100` 로 지수화해서 다룬다(`portfolio_live.py` 와 같은 방식)."""
    if not pairs or len(pairs) < 1:
        return None
    ds = [p[0] for p in pairs]
    vs = [float(p[1]) for p in pairs]
    if pct_points:
        vs = [1.0 + v / 100.0 for v in vs]
    base = vs[0] if vs[0] else 1.0
    peak_i = max(range(len(vs)), key=lambda i: vs[i])
    trough_i = min(range(len(vs)), key=lambda i: vs[i])
    run, mdd, mdd_at = vs[0], 0.0, ds[0]
    for d, v in zip(ds, vs):
        run = max(run, v)
        dd = (v / run - 1) * 100 if run else 0.0
        if dd < mdd:
            mdd, mdd_at = dd, d
    return {
        "n": len(vs), "first": ds[0], "last": ds[-1],
        "ret": (vs[-1] / base - 1) * 100,
        "peak": vs[peak_i], "peak_at": ds[peak_i],
        "peak_ret": (vs[peak_i] / base - 1) * 100,
        "trough": vs[trough_i], "trough_at": ds[trough_i],
        "trough_ret": (vs[trough_i] / base - 1) * 100,
        "from_peak": (vs[-1] / vs[peak_i] - 1) * 100 if vs[peak_i] else 0.0,
        "mdd": mdd, "mdd_at": mdd_at,
    }


def show_path(s, indent="    "):
    if not s:
        print(indent + "기록 없음")
        return
    print(f"{indent}{s['first']} ~ {s['last']} ({s['n']}일)  현재 {s['ret']:+.2f}%")
    print(f"{indent}최고 {s['peak_ret']:+.2f}% ({s['peak_at']})  "
          f"최저 {s['trough_ret']:+.2f}% ({s['trough_at']})")
    print(f"{indent}고점대비 {s['from_peak']:+.2f}%   MDD {s['mdd']:.2f}% ({s['mdd_at']})")
    if abs(s["ret"]) < 0.01 and s["peak_ret"] > 0.5:
        print(f"{indent}⚠️ 시작=끝이지만 중간에 {s['peak_ret']:+.2f}%까지 갔다. "
              f"'아무 일 없었다'가 아니다.")


def gaps(dates, weekdays_only):
    """빠진 날. **마지막 기록 이후 오늘까지도 본다.**

    첫 판에서 기록 사이의 구멍만 셌더니 정작 잡아야 했던 2026-08-28 유실을
    못 잡았다 — 그날이 계열의 **끝**이라 '사이'가 아니었기 때문이다.
    포워드 기록이 죽는 전형적 형태가 바로 '어느 날부터 그냥 안 쌓임'이므로
    후행 구멍이 오히려 더 중요하다. 그래서 오늘까지 훑는다.

    ⚠️ 한국 공휴일은 모른다. 광복절 대체휴일(2026-08-17) 같은 날이 '유실'로
    잡힐 수 있으므로, 사이 구멍은 **확인 대상**으로만 보고 단정하지 않는다.
    후행 구멍(마지막 기록 이후)은 휴일이어도 '며칠째 안 쌓임'이라 의미가 있다."""
    if not dates:
        return [], 0
    ds = [dt.date.fromisoformat(x) for x in dates]
    have = set(ds)
    inner, cur = [], ds[0]
    while cur <= ds[-1]:
        if (not weekdays_only or cur.weekday() < 5) and cur not in have:
            inner.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    stale = 0
    cur = ds[-1] + dt.timedelta(days=1)
    today = dt.date.today()
    while cur <= today:
        if not weekdays_only or cur.weekday() < 5:
            stale += 1
        cur += dt.timedelta(days=1)
    return inner, stale


def trade_stats(trades):
    if not trades:
        return None
    p = [float(t.get("profit", 0)) for t in trades]
    w = [x for x in p if x > 0]
    l = [x for x in p if x <= 0]
    sp = sorted(p)
    return {
        "n": len(p), "win": len(w),
        "wr": 100 * len(w) / len(p),
        "avg": sum(p) / len(p),
        "med": sp[len(sp) // 2],
        "aw": sum(w) / len(w) if w else 0.0,
        "al": sum(l) / len(l) if l else 0.0,
        "pf": (sum(w) / len(w)) / abs(sum(l) / len(l)) if w and l and sum(l) else float("inf"),
        "best": max(p), "worst": min(p),
        "hold": sum(float(t.get("hold_hours", 0)) for t in trades) / len(p),
    }


def section(title, sched):
    print(f"\n[{title}  {sched}")


def equity_block(state, weekdays_only, pct_points=False):
    eq = (state or {}).get("equity", [])
    s = path_stats(eq, pct_points=pct_points)
    show_path(s)
    if eq:
        report_gaps([e[0] for e in eq], weekdays_only)
    return s


def report_gaps(dates, weekdays_only):
    inner, stale = gaps(dates, weekdays_only)
    if stale:
        print(f"    ⚠️ 마지막 기록 이후 {stale}일째 안 쌓임 — cron 실패 의심. "
              f"로그를 볼 것(2026-08-28에 실제로 하루 유실됐다).")
    if inner:
        print(f"    · 사이 빠진 날 {len(inner)}일: {', '.join(inner[:6])}"
              f"{' …' if len(inner) > 6 else ''}  (공휴일일 수 있음 — 확인 대상)")


def main():
    print("=" * 72)
    print("  젯슨 페이퍼 투자 현황  (%s)  ※ 전부 페이퍼, 실주문 없음"
          % dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 72)

    section("1] 장투(KR 추세추종)", "forward_paper.py — cron 평일 16:10")
    st = _load(f"{B}/cache/paper_state.json", {})
    equity_block(st, True)
    pos = st.get("positions", st.get("holdings", {})) or {}
    print(f"    보유 {len(pos)}종목: {', '.join(list(pos)[:10])}")

    section("2] 전략B(급등+공시촉매)", "forward_paper_b.py — cron 평일 16:20")
    print("    ⚠️ 백테스트 t=1.57로 판정 불가. 결합 포트폴리오에서 제외돼 있다.")
    stb = _load(f"{B}/cache/paper_b_state.json", {})
    equity_block(stb, True)
    posb = stb.get("positions", stb.get("holdings", {})) or {}
    print(f"    보유 {len(posb)}종목")

    section("3] 크립토 저변동 롱숏", "crypto_ls_paper.py — cron 매일 09:30")
    sl = _load(f"{B}/cache/ls_paper_state.json", {})
    if sl:
        print(f"    열린 코호트 {len(sl.get('cohorts', []))} | "
              f"청산완료 {len(sl.get('closed', []))}"
              f"{'  ← 실현이 0이면 아래 수익은 전부 평가손익이다' if not sl.get('closed') else ''}")
        if sl.get("guard_from"):
            print(f"    v15 청산가드 적용 {sl['guard_from']}")
        equity_block(sl, False, pct_points=True)   # 이 계열은 누적 %p 다
        cl = sl.get("closed", [])
        if cl:
            r = sorted(c["ret"] for c in cl)
            print(f"    실현 중앙값 {r[len(r)//2]:+.2f}% | "
                  f"승률 {100*sum(1 for x in r if x>0)/len(r):.0f}% | {len(r)}코호트")
            print(f"    ※ 판정에는 20코호트 이상 필요 — 현재 {len(r)}개")

    section("4] 코인봇(HTF 1시간봉 추세추종)", "crypto_bot.service — 상시")
    eq = _load(f"{X}/crypto/equity_htf.json", {}) or {}
    s = path_stats([(k, eq[k]) for k in sorted(eq)])
    show_path(s)
    if eq:
        report_gaps(sorted(eq), False)
    pos = _load(f"{X}/crypto/position_htf.json", {}) or {}
    print(f"    현재 보유 {len(pos)}종목: {', '.join(list(pos)) if pos else '(전액 현금)'}")

    tl = _load(f"{X}/crypto/trade_log_htf.json", []) or []
    ts = trade_stats(tl if isinstance(tl, list) else list(tl.values()))
    if ts:
        print(f"    ── 거래 로그 {ts['n']}건 (자산곡선과 별개로 본다) ──")
        print(f"       승률 {ts['wr']:.0f}% ({ts['win']}승 {ts['n']-ts['win']}패) | "
              f"평균 {ts['avg']:+.2f}% | 중앙값 {ts['med']:+.2f}%")
        print(f"       평균이익 {ts['aw']:+.2f}% / 평균손실 {ts['al']:+.2f}% "
              f"→ 손익비 {ts['pf']:.2f}")
        print(f"       최고 {ts['best']:+.2f}% | 최악 {ts['worst']:+.2f}% | "
              f"평균보유 {ts['hold']:.1f}시간")
        if s and ts["n"] > s["n"]:
            print(f"       ⚠️ 거래 {ts['n']}건인데 자산기록은 {s['n']}일뿐이다 — "
                  f"`_record_equity` 가 2026-08-16까지 고장나 있었다(import 누락). "
                  f"그 이전 손익은 자산곡선에 없다.")

    print("\n" + "=" * 72)
    print("  ※ 자산곡선은 **항상 최고점·고점대비·MDD와 함께** 읽는다. 양끝만 보면")
    print("     시작=끝인 구간에서 '아무 일 없었다'로 잘못 읽는다(2026-08-29 실제 사례).")


if __name__ == "__main__":
    main()
