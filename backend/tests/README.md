# Backend 테스트 폴더 안내

`backend/tests`는 Backend 기능이 예상대로 작동하는지 자동으로 검증하는 개발용 폴더다.

## 파일별 역할

- `test_admin_llm_api.py`: 관리자 LLM 모델 목록·실행·비교의 HTTP 계약을 검증한다.
- `test_llm_api.py`: 일반 LLM 모델 목록·Message 전달·비교의 HTTP 계약을 검증한다.
- `test_config_paths.py`: 최상위 `.env`와 프로젝트 경로 설정을 검증한다.
- `test_document_ocr_api.py`: 서비스 OCR API의 Text·Line 응답과 오류 계약을 검증한다.
- `test_admin_ocr_api.py`: Admin OCR Multipart 입력과 응답 계약을 검증한다.
- `test_ocr_workflow.py`: 공통 Core Thread 호출과 Admin Chunk·응답 조립을 검증한다.
- `test_ocr_jobs.py`: OCR 작업 생성과 상태 전이를 검증한다.
- `test_ocr_vector_save.py`: OCR Chunk Embedding 검증과 문서·Chunk Transaction 저장을 검증한다.
- `test_remote_embedding_provider.py`: Vast.ai query/passage HTTP 계약·인증·응답 검증을 검증한다.
- `test_rag_embedding_factory.py`: 기본 Jina/BGE 이중 Provider 조립을 검증한다.
- `test_rag_search_service.py`: 두 pgvector 순위의 Chunk UUID 기반 RRF 합성을 검증한다.
- `test_message_upload.py`: 메인·채팅 복수 파일의 개수·형식·크기와 multipart API를 검증한다.
- `test_evaluation_api.py`: 정답 데이터 파일·텍스트 파싱과 답변 성능지표 API를 검증한다.
- `__init__.py`: 이 폴더를 Python 패키지로 인식시킨다.
- `__pycache__`: Python 실행 중 자동 생성되는 캐시이며 소스 파일이 아니다.

## Admin 페이지 실행에 필요한가?

필수는 아니다. Admin 페이지는 다음 실제 서비스 코드를 통해 작동하며 테스트 폴더를 실행 과정에서 불러오지 않는다.

```text
Frontend Admin 페이지
  -> Backend API
  -> Backend 서비스 및 Provider
```

따라서 `backend/tests`가 운영 서버에 없어도 Admin 기능은 작동한다.

## 배포 환경에서 제외해도 되는가?

운영용 배포 이미지에서는 제외할 수 있다. 테스트 코드는 서비스 실행에 필요하지 않으며 이미지 크기와 불필요한 개발 파일을 줄일 수 있다.

다만 다음 원칙을 권장한다.

- Git 저장소에서는 테스트를 유지한다.
- 배포 전에 로컬 또는 CI 환경에서 테스트를 실행한다.
- 테스트가 통과한 소스만 운영 환경에 배포한다.
- 운영 이미지에서는 `tests`, `__pycache__`, 테스트 캐시를 제외할 수 있다.
- 장애 재현용 개발·검증 환경에는 테스트를 포함해도 된다.

즉, 테스트는 **Admin 기능 실행에는 선택 사항**이지만 **안전한 개발과 배포에는 중요한 검증 수단**이다.

Provider, Registry와 Application Service의 Framework 독립 테스트는 Repository Root의
`tests/ai/llm`에 둔다. Backend 테스트에서는 실제 Ollama, Gemini, MedGemma Runtime을
호출하지 않고 Fake Provider를 공통 Application Service에 주입한다.
