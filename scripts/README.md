# scripts/ — 학습·평가 스크립트 (주로 Colab)

`ai/`(OCR/RAG/LLM 등 공용 로직)를 재사용해서 학습·평가를 돌리는 곳. 실제 서비스 코드는
`backend/`, 재사용 로직은 `ai/`에 있고, 여기는 그걸 불러다 쓰는 "실행 스크립트"만 둔다.

## vastai_medical_llm_server.ipynb

Vast.ai의 2× Tesla V100 32GB에 Gemma, MedGemma 최종·데이터셋, Qwen, Llama의
5개 의료 LoRA/QLoRA 모델을 로드하고 Backend가 호출할 Bearer 인증 FastAPI를 실행한다.
모델은 프로젝트의 `models/`에 저장한다. 작은 모델을 GPU 사이에 분할하지 않고 GPU 0에는
Gemma/Qwen/Llama를 FP16으로, GPU 1에는 MedGemma 공유 base를 FP32로 배치해 서로 다른
GPU의 요청을 동시에 처리한다. MedGemma 두 카드는 같은 4B base를 공유하고 adapter만 전환한다.

V100에서는 이 크기의 모델을 `fp16`으로 올리는 구성이 보통 4bit bitsandbytes 추론보다 빠르다.
VRAM이 부족한 커스텀 입력 길이를 사용할 때만 Notebook의 `MODEL_PRECISION`을 `4bit`로
바꾼다. 컨테이너 포트 8000은 Vast.ai의 공개 포트로 매핑하고 Uvicorn worker는 반드시
1개만 사용한다.

## train_medgemma_lora.ipynb

`google/medgemma-4b-it`를 Colab 무료 티어(T4 GPU)에서 QLoRA로 파인튜닝하는 노트북.
**로컬에서 실행하는 파일이 아니라, Colab 브라우저에 올려서 셀을 순서대로 실행하는 파일이다.**
Colab은 무료 GPU를 브라우저 UI로만 내주기 때문에 VS Code에서는 실행할 수 없다 — 코드는
여기서(VS Code) 짜고 커밋한 뒤, 실행만 브라우저로 가서 하면 된다.

아래는 처음 Colab/Hugging Face를 쓰는 걸 기준으로 한 절차다.

### 1. Hugging Face 계정 + 모델 접근 승인

1. [huggingface.co](https://huggingface.co)에서 회원가입.
2. [huggingface.co/google/medgemma-4b-it](https://huggingface.co/google/medgemma-4b-it) 접속 →
   페이지 상단의 라이선스(Health AI Developer Foundations) 동의 후 **"Request access"** 클릭.
   보통 몇 분~즉시 승인된다. 승인 전엔 모델을 다운로드할 수 없다.
3. 승인 확인: 오른쪽 위 프로필 → **Settings → Access Tokens → Create new token**
   - Token type: **Write** (나중에 학습된 어댑터를 Hub에 올릴 때 필요. Read로 만들면 업로드 셀에서 막힌다)
   - 이름은 아무거나(`colab-medgemma` 등), 생성된 토큰 문자열을 복사해둔다. **한 번만 보여주니 잃어버리면 재발급.**

### 2. (private repo인 경우) GitHub 토큰

리포가 private이면 Colab에서 `git clone`할 때 토큰이 필요하다.
GitHub → Settings → Developer settings → **Fine-grained tokens** → New token
- Repository access: 이 리포 하나만 선택
- Permissions: **Contents: Read-only**만 있으면 충분

Public repo면 이 단계는 건너뛰어도 된다.

### 3. Colab 노트북 열기 + GPU 설정

1. [colab.research.google.com](https://colab.research.google.com) → **업로드** 탭에서
   `scripts/train_medgemma_lora.ipynb`를 올리거나, Colab에서 GitHub 탭으로 리포를 직접 열어도 된다.
2. 상단 메뉴 `런타임 > 런타임 유형 변경` → 하드웨어 가속기 **T4 GPU** 선택 → 저장.
   - 무료 티어는 GPU가 항상 보장되지 않는다. "리소스 사용 제한" 메시지가 뜨면 시간을 두고 재시도.

### 4. Secrets에 토큰 등록

Colab 왼쪽 사이드바의 **열쇠 아이콘(🔑, Secrets)** 클릭 →
- `HF_TOKEN` = 1번에서 만든 Hugging Face Write 토큰
- `GH_TOKEN` = (private repo인 경우) 2번에서 만든 GitHub 토큰

이름 옆의 "노트북 액세스" 토글을 켜야 이 노트북에서 실제로 읽을 수 있다.
**절대 코드 셀에 토큰 문자열을 직접 쓰지 않는다** — 노트북을 실수로 공유/커밋해도 토큰이
노출되지 않게 하기 위함.

### 5. 노트북 셀 순서대로 실행

`train_medgemma_lora.ipynb`는 GPU 확인부터 Hub 업로드까지 0~38번으로 세분화된 셀 + 마크다운
설명으로 이뤄져 있고, 맨 위 개요 셀에 전체 실행 순서 체크리스트가 있다. **1번(패키지 설치) 셀을
실행한 직후엔 꼭 `런타임 > 런타임 다시 시작`을 하고 나서 이어서 실행할 것** — 안 그러면 이미
메모리에 올라간 옛날 numpy 때문에 `numpy.dtype size changed` 에러가 난다. 재시작 후엔 "3. 환경
확인"/"4. 핵심 패키지 Import 테스트" 셀로 numpy가 실제로 바뀌었는지 먼저 확인할 수 있다.
7번(저장소 클론)은 지금은 건너뛰어도 되게 만들어뒀다. 나머지는 TODO만 남아있는 33번 셀
(`ADAPTER_REPO`, HF Hub에 올릴 이름)만 채우면 된다.

- **데이터셋**: 기본값으로 [sean0042/KorMedMCQA](https://huggingface.co/datasets/sean0042/KorMedMCQA)
  (2012~2024년 한국 의사/간호사/약사/치과의사 자격시험 문제 7,469개, `doctor` config 사용)가
  Hugging Face에서 자동으로 로드되도록 wiring 해뒀다 — 파일을 따로 업로드할 필요 없다.
  **라이선스가 CC-BY-NC-2.0(비영리)** 이라 나중에 상업 서비스로 갈 때 재검토가 필요하다.
  또한 `train` split엔 해설(`cot`)이 없어서(직종당 5개뿐인 `fewshot` split에만 있음) 이 데이터만
  학습하면 "정답 맞히기"는 배우지만 설명형 답변은 잘 못 배운다 — 노트북 "8. 데이터셋 로드" 셀
  설명 참고. 다른 데이터로 바꾸려면 그 셀의 `load_dataset(...)` 한 줄만 바꾸면 된다 (이 경우
  "11. 데이터셋 포맷팅" 셀의 `format_example`도 컬럼명에 맞게 같이 고쳐야 한다).
- **체크포인트**: Google Drive에 저장되도록 이미 설정돼 있다 (`/content/drive/MyDrive/medgemma-lora-ckpt`,
  학습이 끝나면 별도로 `/content/drive/MyDrive/medgemma-lora-final`에도 최종본을 저장).
  세션이 끊겨도 이 폴더에 마지막 저장 지점이 남는다.
- **T4라서 fp16**: T4는 Turing 아키텍처라 bf16 텐서코어 가속이 없어서(Ampere 이상부터 지원),
  4bit 양자화 compute dtype과 학습 정밀도 모두 `float16`을 쓴다(`bf16=False`). 나중에 A100 등
  다른 GPU로 옮기면 `bfloat16`이 더 안정적일 수 있다.
- **numpy는 건드리지 않는다**: 한때 `numpy==1.26.4`로 강제 고정했었는데, 지금 Colab 기본
  이미지는 `opencv`/`jax`/`cupy`/`shap`/`cudf` 등 수십 개 패키지가 전부 `numpy>=2`를 요구하도록
  이미 맞춰져 있어서, numpy를 2.0 밑으로 내리면 오히려 그 패키지들과 충돌해서 같은 종류의
  ABI 에러가 재발한다. 그래서 지금은 numpy 버전을 아예 지정하지 않고 Colab 기본값을 그대로 쓴다.

### 6. 세션이 끊겼을 때

무료 티어는 유휴 ~90분, 최대 세션 ~12시간이면 예고 없이 끊긴다. 끊기면:
1. 노트북을 다시 열고 위쪽 셀들(설치 → 재시작 → HF 로그인 → 데이터셋 로드/포맷팅 → 모델 로드 → LoRA 설정 → Drive 마운트 → Trainer 생성)을 **다시 실행** (7번 저장소 클론은 여전히 건너뛰어도 됨)
2. "30. 세션이 끊긴 경우 체크포인트에서 재개" 셀 — 마지막 체크포인트를 자동으로 찾아서 `trainer.train(resume_from_checkpoint=...)`로 이어서 학습

### 7. 학습 끝나면

34번 셀에서 `model.push_to_hub(...)`로 LoRA 어댑터(수십~수백 MB)를 Hugging Face Hub의
private repo로 올린다. 이 repo 이름을 기록해두면, 이후 `ai/llm`(현재 빈 패키지) 쪽에
서빙 코드를 붙이는 건 저장소 쪽 작업이니 이어서 진행하면 된다.

### 자주 나는 에러

| 증상 | 원인/조치 |
|---|---|
| `401 / gated repo` | medgemma 접근 승인 전이거나, `HF_TOKEN`이 Secrets에 등록/활성화 안 됨. `from_pretrained(..., token=HF_TOKEN)`처럼 토큰을 명시적으로 넘기고 있는지도 확인 |
| `403` (push_to_hub) | 토큰이 Read 권한으로 발급됨 — Write 토큰으로 재발급 |
| `numpy.dtype size changed, may indicate binary incompatibility` | numpy 버전을 임의로 낮췄을 때 Colab 기본 이미지(numpy>=2를 요구하는 패키지 다수)와 충돌해서 남. **numpy 버전을 따로 지정/고정하지 말 것** — 지금 노트북 1번 셀은 numpy를 안 건드림. 한번 잘못된 numpy가 실제로 디스크에 깔린 상태라면 **"런타임 다시 시작"으론 안 고쳐지고 "런타임 연결 해제 및 삭제"로 VM 자체를 새로 받아야 함** |
| `RuntimeError: operator torchvision::nms does not exist` → `ModuleNotFoundError: ... 'Gemma3ForConditionalGeneration'` | Colab 기본 이미지에 torch/torchvision 버전이 서로 안 맞게 깔려있는 경우가 있음(우리가 만든 문제 아님). MedGemma는 멀티모달 모델 클래스라 로드 시 torchvision을 건드리다가 막힘 — 텍스트 전용 파인튜닝엔 torchvision이 필요 없어서 1번 셀에서 아예 제거함(`pip uninstall -y torchvision`) |
| `NotImplementedError: "_amp_foreach_non_finite_check_and_unscale_cuda" not implemented for 'BFloat16'` | `fp16=True`로 학습하면 트레이너가 GradScaler를 켜는데, Gemma 계열은 LoRA 레이어 일부가 bfloat16으로 생성돼서 GradScaler가 그 텐서를 처리 못 함. T4는 bf16 가속도 안 되니 아예 `fp16=False, bf16=False`로 AMP를 끄고 기본 정밀도로 학습 (24번 셀에 반영됨) |
| `SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'` / `SFTTrainer.__init__() got an unexpected keyword argument 'max_seq_length'` | trl 버전에 따라 이 인자 이름이 자주 바뀐다. 지금 노트북은 최신 trl 기준 `max_length`로 맞춰뒀음 — trl을 오래된 버전으로 따로 고정하지 말 것(아래 항목과 충돌 생김) |
| `Trainer.__init__() got an unexpected keyword argument 'tokenizer'` | trl과 transformers 버전이 서로 안 맞을 때(예: trl만 옛날 버전으로 고정) 발생. 1번 셀처럼 `transformers`와 `trl`을 **같은 시점에 같이 설치**해야 함(버전 고정 안 함) |
| `OutOfMemoryError` | `per_device_train_batch_size`를 이미 1로 최소화한 상태라면, `max_length`를 줄이거나 `gradient_accumulation_steps`를 늘려서 실효 배치는 유지하며 메모리만 줄이기. `gradient_checkpointing=True`와 `model.config.use_cache = False`가 같이 켜져 있는지도 확인(20번 셀) |
| 런타임이 자꾸 끊김 | 무료 티어의 기본 특성 — "6. 세션이 끊겼을 때" 절차로 이어서 진행 |
| GPU가 안 잡힘 ("리소스 한도 초과") | 시간을 두고 재시도, 또는 그날의 무료 GPU 쿼터 소진 — 다음날 재시도 |
| 학습 중 wandb API key 입력 프롬프트로 멈춤 | `SFTConfig(report_to="none", ...)`로 이미 막아뒀음 — 그래도 뜨면 이 옵션이 빠졌는지 확인 |

## requirements-train.txt

노트북이 Colab 셀에서 직접 `!pip install`로 설치하므로 실행에 필요하진 않다. 로컬에서
버전을 참고하거나, 나중에 다른 환경(Colab이 아닌 GPU 서버 등)에서 재현할 때 쓰는 참고용 목록.
