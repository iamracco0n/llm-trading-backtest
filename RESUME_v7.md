# 밤에 이어서 하기 — v7 비평 실험 재개 안내

2026-08-10 오전 중단. **캐시는 전부 보존**되어 있고, 각 스크립트는 캐시에 없는 건만 이어서 처리한다.

| 단계 | 진행 | 상태 |
|---|---|---|
| ① 자기비평 qwen3.6:35b | 697/697 | **완료 — 기각**(RESULTS_KR.md 참조) |
| ② 교차비평 gemma4:12b | 360/697 (337 남음) | 중단, 재개 필요 |
| ③ gemma4:31b 모델비교 | 210/697 (487 남음) | 중단, 재개 필요 |

## 재개 명령 (작업 디렉터리에서)

SSH 터널이 살아 있어야 한다(`localhost:11435` → ollama 호스트). 끊겼으면 먼저 다시 연결.

### ② 교차비평 — CPU 7시간 / **GPU 21분**

```bash
# CPU (기본, 안전)
LLM_MODEL=gemma4:12b LLM_NUM_GPU=0  python3 v7_critique.py judge --tag cross
# GPU — 에어컨 켜져 있을 때만. 12b=7.6GB라 3080 10GB에 통째로 올라감(실측 3.6초/건)
LLM_MODEL=gemma4:12b LLM_NUM_GPU=99 python3 v7_critique.py judge --tag cross

python3 v7_critique.py compare --tag cross     # 판정(사전 기준은 스크립트에 고정)
```

### ③ gemma4:31b — CPU 29시간 / GPU 부분오프로드 ~12시간

```bash
LLM_MODEL=gemma4:31b LLM_NUM_GPU=0 python3 v5_oos.py judge --tag gemma4
python3 v5_oos.py modelcmp --tag gemma4
```

> ⚠️ 31b는 19.9GB인데 3080은 10GB라 **GPU를 켜도 절반만 올라간다.** 2~2.5배 빨라질 뿐이라 GPU를 반나절 물고 있어야 하고, 가성비가 나쁘다. GPU를 쓴다면 ②에만 쓰는 게 낫다.

## ② 중간 관찰 (360건 시점)

교차비평도 **등급을 올리는 쪽으로만 움직인다** — 상향 30 : 하향 3. 강한호재 107 → 133(+24%)로 ①(+11%)보다 심하다. 즉 상향 편향은 자기비평 고유의 앵커링이 아니라 **비평 구조 자체의 성질**로 보인다. ①이 +11% 희석만으로 전 지평 열위였으므로 ②도 기각 가능성이 높다 — 다만 이는 예측이고, 697건을 다 채운 뒤 고정된 기준으로 한 번만 판정한다.

## 프로세스 관리 주의

`pkill -f` / `pgrep -f` 는 **자기 자신·SSH 셸까지 매치해서 죽인다**(이 프로젝트에서 3번 사고). 반드시 `ps` 로 PID를 확인해 `kill <pid>` 로 끊을 것.
