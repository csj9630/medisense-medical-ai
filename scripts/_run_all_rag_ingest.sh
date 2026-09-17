#!/bin/bash
# 실제 Neon 저장 - scripts/rag_ingest.py를 신뢰도 tier 순으로 돌린다.
# scripts/_run_all_rag_prepare.sh(로컬 파일만 만드는 버전)와 정책은 동일하고
# 실행 대상 스크립트만 다르다.
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
LOG_DIR="scripts/_rag_ingest_logs"
mkdir -p "$LOG_DIR"

# komed-instruct만 --shuffle-seed를 같이 쓴다 - "앞에서부터 8,000건"이 아니라
# 전체 52,000행에서 고르게 뽑은 8,000건이 되게 하기 위함(실제 확인 결과 이
# 데이터셋 원본 순서에 주제 쏠림은 없었지만, 위치 편향 걱정 자체를 없애는 게
# 더 안전한 기본값). seed 고정이라 재실행해도 같은 8,000건이 뽑혀 idempotency가
# 깨지지 않는다.
declare -A LIMITS=(
  [asan]=""
  [snuh-clinical-qa]=""
  [health-search-qa]=""
  [genmed-gpt]=""
  [komed-instruct]="--limit 8000 --shuffle-seed 42"
)

MAX_DATASET_RETRIES=3
RETRY_SLEEP_SECONDS=60

FAILED_DATASETS=()
for src in asan snuh-clinical-qa health-search-qa genmed-gpt komed-instruct; do
  attempt=1
  success=0
  while [ "$attempt" -le "$MAX_DATASET_RETRIES" ]; do
    echo "===== START $src (attempt $attempt/$MAX_DATASET_RETRIES) $(date) ====="
    backend/.venv/Scripts/python.exe -B scripts/rag_ingest.py --source "$src" ${LIMITS[$src]} --data-dir "$(pwd)/data" > "$LOG_DIR/$src.log" 2>&1
    if [ $? -eq 0 ]; then
      success=1
      echo "===== DONE $src $(date) ====="
      tail -n 15 "$LOG_DIR/$src.log"
      break
    fi
    echo "===== FAILED $src (attempt $attempt/$MAX_DATASET_RETRIES) $(date) - ${RETRY_SLEEP_SECONDS}초 후 재시도 ====="
    tail -n 20 "$LOG_DIR/$src.log"
    sleep "$RETRY_SLEEP_SECONDS"
    attempt=$((attempt + 1))
  done
  if [ "$success" -ne 1 ]; then
    echo "===== GIVE UP $src - ${MAX_DATASET_RETRIES}번 모두 실패 ====="
    FAILED_DATASETS+=("$src")
  fi
done

if [ "${#FAILED_DATASETS[@]}" -eq 0 ]; then
  echo "ALL DATASETS INGESTED $(date)"
else
  echo "일부 데이터셋 실패: ${FAILED_DATASETS[*]} $(date)"
  exit 1
fi
