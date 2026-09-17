#!/bin/bash
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
LOG_DIR="scripts/_rag_prepare_logs"
mkdir -p "$LOG_DIR"
# 사용자가 선택한 "C안" - 품질(신뢰도 tier) 우선, 그다음 차등 저장. 신뢰도가
# "매우 높음"/"중간"인 데이터셋(asan, snuh-clinical-qa)은 전량, "낮음"인
# 데이터셋(health-search-qa, genmed-gpt)은 전량이되 상대적으로 작아서 문제 없음,
# komed-instruct만 8,000행으로 제한한다 - 원본 자체가 "추가 필터링 없음/환각 위험"을
# 경고하는 가장 신뢰도 낮은 데이터셋인데 동시에 전체 청크의 79%를 차지해서
# Neon 무료 티어 저장량을 지배하는 요인이었다(자세한 계산은 대화 기록 참고).
declare -A LIMITS=(
  [asan]=""
  [snuh-clinical-qa]=""
  [health-search-qa]=""
  [genmed-gpt]=""
  [komed-instruct]="--limit 8000 --shuffle-seed 42"
)

# 원격 임베딩 서버(Cloudflare 터널 뒤 Vast.ai GPU)가 대량 처리 도중 몇 분 정도
# 일시적으로 응답 불능 상태(502/530 등)에 빠지는 게 실제로 여러 번 관찰됐다 -
# RemoteEmbeddingProvider 자체 재시도(최대 몇 초)로 못 버티는 더 긴 정지에 대비해,
# 데이터셋 단위로도 재시도한다. `set -e`를 안 쓰는 이유도 이것 - 한 데이터셋이
# 재시도를 다 써도 실패하면 그 데이터셋만 실패로 기록하고 나머지는 계속 진행한다.
MAX_DATASET_RETRIES=3
RETRY_SLEEP_SECONDS=60

# 신뢰도 tier가 높은 순서로 처리한다 - 데이터셋 간 중복(dedup.py의 cross-dataset
# 처리, load_hash_index/save_hash_index)이 발견되면 "먼저 처리된 쪽이 원본으로
# 남고 나중 쪽이 스킵"되는 방식이라, 순서가 곧 우선순위다. asan(매우 높음) ->
# snuh-clinical-qa(중간) -> health-search-qa/genmed-gpt(낮음) -> komed-instruct
# (낮음, 자체 결함 경고 + 8,000행 캡).
FAILED_DATASETS=()
for src in asan snuh-clinical-qa health-search-qa genmed-gpt komed-instruct; do
  attempt=1
  success=0
  while [ "$attempt" -le "$MAX_DATASET_RETRIES" ]; do
    echo "===== START $src (attempt $attempt/$MAX_DATASET_RETRIES) $(date) ====="
    backend/.venv/Scripts/python.exe -B scripts/rag_prepare_dataset.py --source "$src" ${LIMITS[$src]} --out-dir "$(pwd)/data" > "$LOG_DIR/$src.log" 2>&1
    if [ $? -eq 0 ]; then
      success=1
      echo "===== DONE $src $(date) ====="
      tail -n 12 "$LOG_DIR/$src.log"
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
  echo "ALL DATASETS COMPLETE $(date)"
else
  echo "일부 데이터셋 실패: ${FAILED_DATASETS[*]} $(date)"
  exit 1
fi
