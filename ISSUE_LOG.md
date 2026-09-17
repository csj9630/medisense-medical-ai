# 이슈 트래킹

이번 작업 세션(2026-08-17 ~ 08-18)에서 있었던 문제와 해결 과정 기록. 크게 세 갈래로 진행됨:
관리자 페이지(프론트), 로컬 AI 파이프라인 랩 페이지, MedGemma Colab 파인튜닝 노트북.

## 1. 관리자 페이지 (`frontend/src/features/admin`)

| # | 문제/결정 | 원인 | 조치 | 상태 |
|---|---|---|---|---|
| 1-1 | 첨부 이미지대로 관리자 페이지 프론트 UI 필요 | 신규 요청 | OCR 업로드 패널 + OCR/LLM 탭 패널로 정적 목업 구현 (`OcrUploadPanel.tsx`, `LlmComparePanel.tsx`). 백엔드 API 없어서 버튼은 비활성 상태 | ✅ 완료 |
| 1-2 | 라이트/다크 토글 옆에 "관리자 페이지 이동" 버튼 필요, admin 계정만 노출 | 신규 요청 | `AdminLinkButton.tsx` 추가, `MainLayout.tsx`의 `ThemeToggle` 옆에 배치. 처음엔 `user.is_admin`으로 게이팅 | ✅ 완료 |
| 1-3 | `is_admin` 게이팅이 항상 `false`로 나옴 | DB에서 `is_admin` 컬럼이 이미 삭제된 상태였음 (backend는 `getattr(user, "is_admin", False)`로 방어돼 있어 에러는 안 나고 조용히 항상 `false` 반환) | `user.email === 'admin@admin.com'` 하드코딩 비교로 전환 | ✅ 해결 (다만 백엔드 스키마/서비스에 죽은 `is_admin` 필드가 남아있음 — 정리는 보류) |

## 2. 로컬 AI 파이프라인 랩 페이지 (`backend/local_lab/page.html`)

| # | 문제/결정 | 원인 | 조치 | 상태 |
|---|---|---|---|---|
| 2-1 | 기존 UI를 더 보기 편하게 개선 요청 | 신규 요청 | 스텝퍼(OCR→청킹→임베딩→검색), 카드형 레이아웃, OCR 신뢰도 색상 바(초록/주황/빨강), 로딩/에러 상태 표시로 재설계 | ✅ 완료 (Playwright로 빈 상태/목데이터 채운 상태 렌더링 검증) |

## 3. MedGemma-4B QLoRA Colab 파인튜닝 노트북 (`scripts/train_medgemma_lora.ipynb`)

가장 이슈가 많았던 부분. 시간순으로 정리.

| # | 문제 | 원인 | 조치 | 상태 |
|---|---|---|---|---|
| 3-1 | Colab/HF 처음 써봄, 가이드 필요 | 신규 요청 | `scripts/train_medgemma_lora.ipynb` + `scripts/README.md` 최초 작성 (HF 토큰, Colab Secrets, QLoRA 뼈대) | ✅ |
| 3-2 | `401 gated repo` 에러 (medgemma 접근 불가) | 진단 결과 접근 승인 자체는 돼 있었음 — `login()` 세션이 `from_pretrained` 호출에 실제로 안 먹힌 것으로 추정 | 모델/토크나이저 로드 시 `token=HF_TOKEN` 명시적으로 전달하도록 수정 | ✅ |
| 3-3 | Google Drive 마운트 실패 (`ValueError: mount failed`) | 브라우저 팝업 차단/서드파티 쿠키 차단 등 환경 문제 | 팝업 허용, 쿠키 허용, `force_remount` 등 가이드 | ✅ |
| 3-4 | `SFTConfig.__init__() got an unexpected keyword argument 'max_seq_length'` | trl 버전마다 이 인자 이름이 바뀜 | (1차 조치, 아래 3-5로 다시 뒤집힘) trl을 `0.9.6`으로 다운그레이드해서 회피 | ⚠️ 임시 조치였음 |
| 3-5 | `Trainer.__init__() got an unexpected keyword argument 'tokenizer'` | 3-4에서 trl을 구버전(0.9.6)으로 고정한 게 원인 — 구버전 trl의 `SFTTrainer`가 최신 `transformers`의 `Trainer`(인자명이 `tokenizer`→`processing_class`로 변경됨)와 안 맞음 | trl 버전 고정 해제(최신으로 통일), `SFTConfig`는 `max_seq_length` 대신 실제 최신 필드명인 **`max_length`**로 수정 (trl 소스 직접 확인) | ✅ |
| 3-6 | 학습 데이터셋 선정 | — | ClinicalQA(설명 있음, 1,045개) → KorMedMCQA(설명 거의 없음, 7,469개, CC-BY-NC-2.0) → 두 데이터셋 합치기 시도 → 최종적으로 **KorMedMCQA(`doctor` config) 단독**으로 재확정 | ✅ 결정 완료 |
| 3-7 | `git clone` 셀에서 `계정: No such file or directory` | 저장소 경로 placeholder(`<계정>/<repo>`)를 실제 값으로 안 바꾸고 실행 — bash가 `<`, `>`를 리다이렉션으로 해석 | 실제 저장소 URL/브랜치(`ThedaolOCR3/thegpt-project`, `kbg`)로 채워넣고, 이 클론 단계 자체가 지금 단계에선 불필요하다고 명시(스킵 가능) | ✅ |
| 3-8 | 로컬(VS Code) 수정이 Colab에 반영 안 됨 | 로컬 파일과 Colab에 열린 사본은 애초에 서로 다른 파일 — 자동 동기화 없음 | GitHub에 push 후 Colab에서 `colab.research.google.com/github/.../blob/kbg/...` URL로 여는 방식으로 전환 (private repo라 최초 1회 GitHub 인증 필요) | ✅ |
| 3-9 | 노트북 구조 정리 요청 | 여러 차례 패치가 누적되며 셀 간 불일치 우려 | 27개 셀로 노트북 전체 재작성 (numpy<2 고정, trl 언핀, `max_length` 등 그동안의 수정 통합) | ✅ (이후 3-10에서 numpy 판단이 다시 뒤집힘) |
| 3-10 | 사용자가 훨씬 상세한 스펙(0~38번 섹션, 70개 셀) 제공 | 신규 요청 | 해당 스펙대로 노트북 전체 재작성. T4는 bf16 텐서코어 미지원 → fp16 사용, `gradient_checkpointing=True`+`use_cache=False` 페어링, `report_to="none"`(wandb 프롬프트 방지), `numpy==1.26.4` 강제 고정 등 반영 | ✅ (numpy 고정은 3-11에서 오류로 판명) |
| 3-11 | `numpy.dtype size changed, may indicate binary incompatibility` 재발 | **3-10에서 넣은 `numpy==1.26.4` 강제 다운그레이드가 원인** — 현재 Colab 기본 이미지는 opencv/jax/cupy/shap/cudf 등 수십 개 사전 설치 패키지가 전부 `numpy>=2`를 요구하도록 이미 맞춰져 있어서, numpy를 2.0 밑으로 내리면 오히려 그 패키지들과 충돌함. (지난 세션 지식에 기반한 잘못된 처방이었음, `pip install` 충돌 로그로 확인) | numpy 버전 지정을 완전히 제거 — Colab 기본값 그대로 사용 | ✅ |
| 3-12 | `RuntimeError: operator torchvision::nms does not exist` → `ModuleNotFoundError: 'Gemma3ForConditionalGeneration'` | Colab 기본 이미지 자체에 `torch`(2.13.0)와 `torchvision`(2.11.0용으로 빌드됨)이 이미 안 맞게 깔려있었음 (이번 작업에서 만든 문제 아님). MedGemma는 멀티모달 모델 클래스라 로드 시 torchvision을 건드리다가 막힘 | 텍스트 전용 파인튜닝엔 torchvision이 불필요 — 설치 셀에서 `pip uninstall -y torchvision` 추가 | ✅ |
| 3-13 | Drive 마운트 `MessageError: credential propagation was unsuccessful` | 광고 차단기/프라이버시 확장 프로그램, 서드파티 쿠키 차단 등 브라우저 환경 문제 | 확장 프로그램 비활성화, 쿠키 허용, `auth.authenticate_user()` 대안 가이드 | ✅ (환경 이슈라 재발 가능) |
| 3-14 | `NotImplementedError: "_amp_foreach_non_finite_check_and_unscale_cuda" not implemented for 'BFloat16'` | `fp16=True`로 학습 시 GradScaler가 켜지는데, Gemma 계열 모델은 LoRA 레이어 일부가 `bfloat16`으로 생성돼서 GradScaler가 이를 처리 못함. T4는 bf16 가속도 안 됨 | `fp16=False`, `bf16=False`로 AMP 자체를 끄고 기본 정밀도로 학습 | ✅ |

### 되짚어볼 점
- **numpy 관련(3-4→3-5, 3-10→3-11)처럼 한 번 틀린 처방을 다음 재작성 때 그대로 들고 간 경우가 있었음** — 특히 3-10에서 사용자가 제공한 스펙에 옛날 처방(`numpy==1.26.4`)이 들어있는 걸 그대로 반영했다가 재발함. 앞으로 패키지 버전을 강제 고정할 땐 "왜 이 버전이 필요한지"를 그 시점의 실제 에러 로그로 재검증하고 넣을 것.
- Colab 세션(커널)이 이전 상태를 메모리/디스크에 들고 있어서, 노트북 파일만 고쳐서는 안 되고 **"런타임 다시 시작"과 "런타임 연결 해제 및 삭제"를 구분**해서 안내해야 했던 경우가 여러 번 있었음(특히 잘못된 패키지가 디스크에 실제로 설치된 경우엔 후자가 필요).

## 현재 상태 / 다음 단계

- [ ] Colab에서 `trainer.train()` 끝까지 완주 (학습 자체는 아직 완료 확인 안 됨)
- [ ] LoRA 어댑터를 Hugging Face Hub private repo에 업로드 (`scripts/train_medgemma_lora.ipynb` 33~34번 셀, `ADAPTER_REPO` 이름 확정 필요)
- [ ] 어댑터 repo 이름이 정해지면 `ai/llm`(현재 빈 패키지)에 `PeftModel.from_pretrained(base, adapter_repo)` 로드하는 서빙 코드 작성
- [ ] `ai/consultation`에 공식 프롬프트 템플릿이 생기면 노트북의 `format_example`을 그쪽 함수로 교체
- [ ] 백엔드 `is_admin` 죽은 필드 정리 여부 결정 (1-3 참고)
