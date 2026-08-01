# -*- coding: utf-8 -*-
"""대결 공통 설정 — 규칙봇/LLM봇이 똑같은 조건에서 싸우도록."""

# 종목 유니버스 (젯슨 coins.json 그대로)
COINS = [
    "KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE",
    "KRW-SUI", "KRW-SEI", "KRW-ONDO", "KRW-HBAR", "KRW-LINK",
    "KRW-AVAX", "KRW-APT", "KRW-FET", "KRW-TAO", "KRW-RENDER",
    "KRW-WIF", "KRW-BONK", "KRW-PEPE", "KRW-FLOKI", "KRW-NEAR",
]

# 백테스트 기간 (5분봉 기준). 스모크 테스트는 짧게, 본실행은 길게.
BACKTEST_DAYS = 7

# 판단 주기: 5분봉 12개 = 1시간 (젯슨 규칙봇의 3600초 루프와 동일)
DECISION_INTERVAL_BARS = 12

# ===== 공통 매매 조건 (두 봇 동일) =====
START_KRW = 1_000_000       # 시작 자본
BUY_AMOUNT = 50_000         # 1종목당 매수액 (젯슨과 동일)
MAX_POSITION = 3            # 최대 동시 보유
FEE = 0.0005               # 업비트 수수료 0.05% (매수·매도 각각)

# ===== 규칙봇 기준치 (젯슨 trade_manager.py 그대로) =====
TAKE_PROFIT = 0.03          # +3% 익절
STOP_LOSS = -0.04           # -4% 손절
MAX_HOLD_HOURS = 72         # 최대 보유
MAX_HOLD_MIN_PROFIT = 0.0025  # 시간만료 시 이 이상이면 매도
TREND_BREAK_LIMIT = 5       # "하락" N회 연속이면 추세붕괴 매도
SCORE_MIN = 80              # 매수 점수 하한
VOL_MIN = 0.8               # 거래량비율 하한
RSI_MAX = 70               # RSI 상한(과열 컷)

# ===== LLM =====
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
LLM_MODEL = "qwen3:14b"
LLM_TEMPERATURE = 0.3

# CPU 강제용: 0 = GPU 아예 안 씀(wedge 위험 0). None = ollama 자동(GPU 사용)
NUM_GPU = None

# LLM 호출 타임아웃(초). CPU 추론은 느려서 넉넉히. (32b는 300초로 전멸했었음)
LLM_TIMEOUT = 600

# ===== 과매매 억제(v2) =====
# LLM봇 최소 보유시간(시간). 이보다 어린 포지션은 매도 금지 —
# 단 손실이 EMERGENCY_STOP 이하면 예외적으로 손절 허용.
MIN_HOLD_HOURS_LLM = 6
EMERGENCY_STOP = -0.04

# 워밍업: 지표 계산에 필요한 최소 5분봉 수 (ma60 + 여유)
WARMUP_BARS = 70

# 밤에도 GPU 안 죽게: LLM 호출 사이 쉬는 시간(초). 지속부하→띄엄띄엄 부하로.
THROTTLE_SEC = 0
