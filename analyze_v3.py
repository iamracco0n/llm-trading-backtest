# -*- coding: utf-8 -*-
import json, os
from collections import Counter
R = "/home/user/coinbot_battle/results"

def load(name):
    try:
        return json.load(open(os.path.join(R, name)))
    except Exception:
        return []

# LLM v3 체결
llm = load("trades_llm_v3_cpu30b.json")
buys = [t for t in llm if t["side"] == "BUY"]
sells = [t for t in llm if t["side"] == "SELL"]
tot = sum(t.get("profit_pct", 0) for t in sells)
wins = [t for t in sells if t.get("profit_pct", 0) > 0]
print("===== LLM v3 체결 =====")
print("매수 %d / 매도 %d | 손익합(수수료전) %+.1f%%p | 승률 %.1f%%" % (
    len(buys), len(sells), tot, 100*len(wins)/len(sells) if sells else 0))
rc = Counter(str(t.get("reason", "")).split(":")[0] for t in sells)
print("청산사유:", dict(rc))
for t in sells[:15]:
    print("  %-11s %+6.2f%%  %s" % (t["ticker"], t.get("profit_pct", 0), str(t.get("reason", ""))[:36]))

# 결정 분포
dec = load("llm_decisions_v3_cpu30b.json")
c = Counter()
for cyc in dec:
    for x in cyc.get("decisions", []):
        if isinstance(x, dict):
            c[x.get("action")] += 1
print("\n결정분포(전체):", dict(c))

# 규칙봇
rule = load("trades_rule_v3_cpu30b.json")
rs = [t for t in rule if t["side"] == "SELL"]
print("\n===== 규칙봇 =====")
print("매수 %d / 매도 %d" % (len([t for t in rule if t["side"]=="BUY"]), len(rs)))
