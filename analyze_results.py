# -*- coding: utf-8 -*-
import json, os
from collections import Counter
R = os.path.join(os.path.dirname(__file__), "results")

for name in ["rule", "llm"]:
    d = json.load(open(os.path.join(R, f"trades_{name}_7d.json")))
    sells = [t for t in d if t["side"] == "SELL"]
    buys = [t for t in d if t["side"] == "BUY"]
    tot = sum(t.get("profit_pct", 0) for t in sells)
    rc = Counter(str(t.get("reason", "")).split(":")[0] for t in sells)
    print(f"===== {name.upper()}봇: 매수 {len(buys)} / 매도 {len(sells)} | 손익합 {tot:+.1f}%p =====")
    print("  청산사유:", dict(rc))
    for t in sells:
        tk = t["ticker"]; pp = t.get("profit_pct", 0); rs = str(t.get("reason", ""))[:38]
        print(f"    {tk:11} {pp:+6.2f}%  {rs}")
    print()

# LLM 판단 샘플 (매수 결정 이유 몇 개)
dec = json.load(open(os.path.join(R, "llm_decisions_7d.json")))
print("===== LLM 매수판단 이유 샘플 =====")
cnt = 0
for cyc in dec:
    for x in cyc["decisions"]:
        if isinstance(x, dict) and x.get("action") == "buy":
            print(f"  [{cyc['ts'][5:16]}] {x.get('ticker'):10} {x.get('reason','')[:50]}")
            cnt += 1
            if cnt >= 12:
                break
    if cnt >= 12:
        break
