# MainProject-AILLM Backend Admin FastAPI Mock 구현 지시서

작성 기준일: 2026-08-17

---

## 1. 작업 목적

이번 작업의 목표는 **기존 프로젝트 구조를 유지한 상태에서 Admin 페이지와 통신 가능한 FastAPI Backend 기본 구조를 구현하는 것**이다.

현재 단계에서는 실제 OCR, LLM, Embedding, RAG, Fine-tuning 기능을 구현하지 않는다.

우선 다음 흐름이 정상적으로 동작하도록 한다.

```text
React Admin Page
→ FastAPI Router
→ Admin Service의 중심 함수
→ Backend Mock 처리
→ Response Schema
→ Frontend 표시
```

이후 실제 AI/OCR 로직이 준비되면 **Mock 처리 부분만 실제 구현으로 교체할 수 있는 구조**를 만든다.

---

# 2. 이번 작업의 핵심 목표

반드시 다음 항목을 만족해야 한다.

- Frontend와 실제 HTTP 통신 가능한 FastAPI API 구현
- Admin 기능별 Request / Response Schema 정의
- Backend에서 기능별 Mock 데이터 반환
- 향후 Mock 부분만 실제 OCR / LLM 구현으로 교체 가능
- 주요 코드에 기능 이해를 위한 한국어 주석 추가
- 하나의 기능에는 전체 실행 순서를 관리하는 중심 함수가 존재
- 다른 파일의 로직을 호출하더라도 결과를 반환받아 중심 흐름으로 복귀
- 기존 프로젝트 구조 유지
- Admin 관련 코드만 가능한 최소 범위로 수정
- 기존 팀원 코드 및 다른 페이지 기능에 영향 최소화

---

# 3. 최우선 제약사항

## 3.1 기존 프로젝트 구조를 변경하지 않는다

현재 Repository 구조를 먼저 분석하고 기존 패턴을 최대한 그대로 따른다.

예를 들어 현재 구조가 다음과 같다면:

```text
backend/
├── app/
│   ├── routers/
│   ├── services/
│   ├── repositories/
│   ├── schemas/
│   ├── models/
│   ├── core/
│   ├── db/
│   ├── utils/
│   └── main.py
├── tests/
├── uploads/
├── requirements.txt
└── .env
```

새로운 Architecture를 적용한다는 이유로 다음 작업을 하지 않는다.

- 프로젝트 전체 폴더 구조 변경
- 기존 Router / Service 이동
- 기존 파일명 변경
- 기존 API URL 변경
- 기존 Response 형식 변경
- 기존 DB Schema 변경
- 인증 구조 변경
- 팀원이 작성한 코드를 스타일 통일 목적으로 수정
- `use_cases/`, `application/` 등의 새 계층을 프로젝트 전체에 강제로 추가
- 기존 기능 대규모 리팩터링

이번 작업은 **Admin 기능 내부에서만 읽기 쉬운 실행 흐름을 만드는 것**이 목적이다.

---

# 4. 작업 전 Repository 분석

구현 전에 반드시 현재 프로젝트를 먼저 분석한다.

확인할 내용:

1. FastAPI 실행 진입점
2. `main.py` 위치
3. Router 등록 방식
4. API Prefix 규칙
5. 기존 `routers/` 구조
6. 기존 `services/` 구조
7. 기존 `schemas/` 구조
8. DB / Repository 구조
9. 인증 및 Dependency 구조
10. CORS 설정
11. 환경 변수 관리 방식
12. Admin 관련 기존 Backend 코드 존재 여부
13. Frontend Admin 페이지 구조
14. Frontend API 호출 방식
15. OCR / LLM Admin 화면에서 실제로 요구하는 Request / Response 데이터

기존 프로젝트의 코드 패턴을 우선 사용한다.

Admin 구현에 반드시 필요한 경우에만 `main.py` 등의 공통 파일을 최소 수정한다.

---

# 5. 설계의 핵심 원칙

이번 Backend에서 가장 중요하게 지켜야 할 원칙은 다음이다.

> 하나의 기능에는 전체 실행 순서를 관리하는 하나의 중심 함수가 존재해야 한다.

세부 기능은 여러 파일로 분리할 수 있다.

하지만 전체 흐름은 중심 함수를 위에서 아래로 읽는 것만으로 파악할 수 있어야 한다.

기본 구조:

```text
중심 함수
→ 하위 함수 호출
← 결과 반환
→ 다음 하위 함수 호출
← 결과 반환
→ Response 생성
→ Return
```

예:

```python
async def compare_models(request):

    validated_request = validate_request(request)

    model_results = create_mock_model_results(
        validated_request
    )

    response = build_compare_response(
        model_results
    )

    return response
```

이 함수만 읽어도 다음 순서를 이해할 수 있어야 한다.

```text
Request
→ Validation
→ Mock 처리
→ Response 생성
→ Return
```

---

# 6. 원하는 코드 흐름

다른 파일의 함수나 Service를 호출하는 것은 허용한다.

하지만 다음 패턴을 우선한다.

```text
AdminService 중심 함수
→ 하위 로직 A 호출
← A 결과 반환

→ 하위 로직 B 호출
← B 결과 반환

→ Response 생성
← 결과

→ Router로 반환
```

반대로 가능한 다음과 같은 연쇄 호출은 피한다.

```text
Router
→ Service A
   → Service B
      → Service C
         → Repository
            → 다른 Service
```

Service가 다른 Service를 계속 호출해 전체 실행 흐름이 여러 파일에 숨지 않도록 한다.

---

# 7. "한 파일에 다 넣기"가 목적이 아니다

코드를 이해하기 쉽게 한다고 해서 모든 로직을 하나의 파일에 작성하지 않는다.

목표는 다음 두 가지를 동시에 만족하는 것이다.

```text
세부 책임은 파일별로 분리
+
전체 실행 순서는 중심 함수에서 확인 가능
```

예:

```python
async def run_ocr(request):

    validated_file = validate_file(request)

    mock_result = create_mock_ocr_result(
        validated_file
    )

    response = build_ocr_response(
        mock_result
    )

    return response
```

각 세부 함수는 다른 파일에 있어도 된다.

다만 세부 함수가 다음 작업까지 임의로 이어서 실행하지 않고 결과를 호출자에게 반환해야 한다.

---

# 8. Router 작성 원칙

Router는 HTTP 요청과 응답 연결만 담당한다.

담당:

- Endpoint 정의
- Request Schema 수신
- 인증 / Dependency 전달
- 중심 Service 함수 호출
- Response 반환
- 필요한 HTTP Status 처리

예:

```python
@router.post("/admin/llm/compare")
async def compare_llm(request: LlmCompareRequest):
    return await admin_llm_service.compare_models(request)
```

Router 내부에 다음 로직을 직접 작성하지 않는다.

- Mock 데이터 생성
- OCR 처리
- LLM 처리
- Prompt 구성
- 복잡한 조건 분기
- DB 비즈니스 로직
- Embedding
- RAG

Router는 가능한 다음 형태가 보여야 한다.

```text
Request
→ Service
→ Response
```

---

# 9. Service 중심 함수

현재 프로젝트에 이미 `services/` 구조가 있다면 새 `use_cases/` 계층을 만들지 않는다.

대신 Admin Service의 대표 함수가 **UseCase / Orchestrator 역할**을 하도록 한다.

예:

```python
async def compare_models(
    request: LlmCompareRequest
) -> LlmCompareResponse:

    validated_request = validate_request(request)

    model_results = create_mock_model_results(
        validated_request
    )

    response = build_compare_response(
        model_results
    )

    return response
```

또는 OCR:

```python
async def run_ocr(
    request: OcrRequest
) -> OcrResponse:

    validated = validate_ocr_request(request)

    mock_result = create_mock_ocr_result(validated)

    response = build_ocr_response(mock_result)

    return response
```

중심 함수만 읽어도 전체 흐름을 30초~1분 안에 이해할 수 있어야 한다.

---

# 10. 함수 작성 기본 원칙

가능한 핵심 함수는 다음 구조를 따른다.

```text
입력 → 처리 → 출력
```

예:

```python
mock_result = create_mock_ocr_result(request)
```

```text
request
→ Mock OCR 생성
→ mock_result
```

다음:

```python
response = build_ocr_response(mock_result)
```

```text
mock_result
→ Response 변환
→ response
```

함수 이름과 변수 이름만 보고 현재 데이터가 무엇인지 예상할 수 있도록 작성한다.

피해야 할 예:

```python
data = process(x)
result = handler(data)
final = manager.run(result)
```

권장:

```python
validated_request = validate_request(request)
mock_results = create_mock_model_results(validated_request)
response = build_compare_response(mock_results)
```

---

# 11. Side Effect 관리

다음 작업은 Side Effect로 본다.

- DB 저장
- 파일 저장
- 파일 삭제
- 외부 API 호출
- Ollama 호출
- 상태값 변경
- Background Task 생성

현재 Mock 단계에서는 이러한 Side Effect를 최소화한다.

필요한 경우 중심 Service 함수에서 호출 위치가 보이도록 한다.

예:

```python
mock_result = create_mock_result(request)

await result_repository.save(mock_result)

return build_response(mock_result)
```

다음처럼 하위 함수 내부에서 여러 Side Effect가 숨겨지지 않도록 한다.

```python
result = process(request)
```

하지만 `process()` 내부에서:

```text
Mock 생성
→ DB 저장
→ 로그 저장
→ 다른 Service 호출
→ 상태 변경
```

까지 처리하는 방식은 피한다.

---

# 12. Async / Await 원칙

`async/await`는 사용할 수 있다.

다음 구조는 직선 흐름으로 본다.

```python
a = await service_a()

b = await service_b(a)

c = await service_c(b)

return c
```

실행 흐름:

```text
Service A
→ Result A
→ Service B
→ Result B
→ Service C
→ Result C
```

현재 Admin Mock 구현에서는 특별한 이유가 없다면 다음을 추가하지 않는다.

- `asyncio.create_task()`
- FastAPI `BackgroundTasks`
- Event Driven 처리
- Callback Chain
- Message Queue

Mock API는 가능한 요청을 받고 즉시 Mock Response를 반환한다.

---

# 13. 병렬 처리 원칙

현재 Mock 단계에서는 불필요한 병렬 처리를 추가하지 않는다.

추후 여러 LLM을 실제로 동시에 실행해야 할 경우에도 분기와 합류가 한 함수에서 보이도록 한다.

예:

```python
async def compare_models(prompt):

    gemma_task = gemma_service.generate(prompt)
    qwen_task = qwen_service.generate(prompt)

    gemma_result, qwen_result = await asyncio.gather(
        gemma_task,
        qwen_task,
    )

    return ModelComparisonResult(
        gemma=gemma_result,
        qwen=qwen_result,
    )
```

흐름:

```text
Gemma ───┐
         ├→ gather → Result → 기존 흐름 복귀
Qwen ────┘
```

병렬 Task를 여러 파일에서 각각 생성하지 않는다.

---

# 14. Admin OCR 기능

## 목적

Admin OCR 탭은 향후 RAG에서 사용할 문서를 다음 목적으로 테스트하는 화면이다.

- 문서 업로드 테스트
- OCR 결과 확인
- 향후 실제 OCR 연동
- 이후 Embedding / Vector DB 삽입 전 문서 처리 테스트

현재 단계에서는 실제 OCR 엔진을 실행하지 않는다.

구현 흐름:

```text
Frontend
→ Admin OCR Router
→ Admin OCR Service 중심 함수
→ Request 검증
→ Backend Mock OCR 생성
→ Response 생성
→ Frontend
```

예:

```python
async def run_ocr(request):

    validated_request = validate_ocr_request(request)

    mock_result = create_mock_ocr_result(
        validated_request
    )

    response = build_ocr_response(
        mock_result
    )

    return response
```

---

# 15. OCR Mock Response

최종 Schema는 반드시 현재 Frontend 요구사항을 분석해서 결정한다.

예시:

```json
{
  "document_id": "mock-document-001",
  "filename": "sample.pdf",
  "status": "completed",
  "text": "OCR Mock 추출 결과입니다.",
  "confidence": 0.94,
  "elapsed_time": 1.25
}
```

필요할 수 있는 필드:

- `document_id`
- `filename`
- `status`
- `text`
- `confidence`
- `elapsed_time`
- `model`
- `pages`

필드는 임의로 추가하지 말고 현재 Admin Frontend 구현과 맞춘다.

---

# 16. Admin LLM 기능

## 목적

Admin LLM 탭은 동일한 Prompt를 여러 LLM 모델에 전달한 뒤 결과를 비교하기 위한 테스트 화면이다.

향후 후보:

- Gemma
- Qwen
- MedGemma
- Fine-tuned Model

현재 단계에서는 실제 Ollama나 모델을 호출하지 않는다.

구현 흐름:

```text
Frontend
→ Admin LLM Router
→ Admin LLM Service 중심 함수
→ Request 검증
→ 모델별 Mock Result 생성
→ Response 생성
→ Frontend
```

예:

```python
async def compare_models(request):

    validated_request = validate_llm_request(request)

    mock_results = create_mock_model_results(
        validated_request
    )

    response = build_compare_response(
        mock_results
    )

    return response
```

---

# 17. LLM Request / Response 예시

Request 예:

```json
{
  "prompt": "두통이 있을 때 확인해야 할 증상을 알려줘",
  "models": [
    "gemma3",
    "qwen3",
    "medgemma"
  ]
}
```

Response 예:

```json
{
  "results": [
    {
      "model": "gemma3",
      "response": "[MOCK] Gemma3 테스트 응답입니다.",
      "elapsed_time": 1.42
    },
    {
      "model": "qwen3",
      "response": "[MOCK] Qwen3 테스트 응답입니다.",
      "elapsed_time": 1.17
    },
    {
      "model": "medgemma",
      "response": "[MOCK] MedGemma 테스트 응답입니다.",
      "elapsed_time": 1.66
    }
  ]
}
```

실제 Response 구조는 Frontend가 현재 기대하는 형식을 우선한다.

---

# 18. Mock 구현 원칙

Mock 데이터는 Router에 직접 작성하지 않는다.

잘못된 예:

```python
@router.post("/admin/ocr")
async def run_ocr():
    return {
        "text": "mock text",
        "confidence": 0.95
    }
```

권장:

```python
@router.post("/admin/ocr")
async def run_ocr(request: OcrRequest):
    return await admin_ocr_service.run_ocr(request)
```

Service:

```python
async def run_ocr(request):

    mock_result = create_mock_ocr_result(request)

    return build_ocr_response(mock_result)
```

---

# 19. 실제 구현으로 교체 가능한 구조

Mock 코드가 여러 계층에 퍼지지 않도록 한다.

현재:

```python
results = create_mock_model_results(request)
```

향후:

```python
results = await ollama_service.generate_models(request)
```

처럼 교체할 수 있어야 한다.

OCR도 동일하다.

현재:

```python
ocr_result = create_mock_ocr_result(request)
```

향후:

```python
ocr_result = await ocr_service.run(request)
```

이상적으로 중심 함수의 전후 흐름과 Response Schema는 그대로 유지한다.

---

# 20. 과도한 추상화 금지

Mock을 실제 구현으로 교체 가능하게 만든다고 해서 다음 구조를 미리 만들 필요는 없다.

- 사용하지 않는 Interface
- Abstract Factory
- Provider Factory
- Manager → Handler → Service 연쇄 구조
- 구현체 하나뿐인 추상 클래스
- 미래 확장만을 위한 과도한 계층

현재 단계에서는 **가장 단순하면서 교체 위치가 명확한 구조**를 우선한다.

---

# 21. Schema 작성

Frontend와 Backend의 Request / Response를 Pydantic Schema로 명확하게 정의한다.

예:

```python
class LlmCompareRequest(BaseModel):
    prompt: str
    models: list[str]
```

Response:

```python
class LlmModelResult(BaseModel):
    model: str
    response: str
    elapsed_time: float


class LlmCompareResponse(BaseModel):
    results: list[LlmModelResult]
```

Mock 단계부터 Schema를 사용하여 향후 실제 구현으로 변경해도 Frontend 계약이 유지되도록 한다.

---

# 22. 주석 작성 원칙

이번 작업에서는 초보 개발자가 코드를 읽고 전체 흐름을 이해할 수 있도록 주요 코드에 한국어 주석을 추가한다.

주석을 작성할 위치:

- 파일 최상단: 파일 역할
- 주요 클래스: 클래스 책임
- 중심 함수: 전체 기능 흐름
- 하위 Service 호출 이유
- Mock 처리 위치
- 향후 실제 구현으로 교체할 위치
- 이해하기 어려운 조건문
- 기존 코드와 연결되는 부분

좋은 예:

```python
# Router에서는 실제 LLM 처리 로직을 수행하지 않는다.
# 요청을 Admin LLM Service의 중심 함수에 전달하여
# 전체 처리 순서를 Service에서 한눈에 확인할 수 있도록 한다.
return await admin_llm_service.compare_models(request)
```

Service:

```python
# 현재 단계에서는 실제 Ollama를 호출하지 않는다.
# 향후 이 부분만 실제 LLM 호출 함수로 교체한다.
model_results = create_mock_model_results(request)

# Frontend는 Mock/실제 구현 여부와 관계없이
# 동일한 Response 구조를 사용하도록 한다.
response = build_compare_response(model_results)
```

불필요한 주석:

```python
# 변수에 값을 넣는다.
result = ...
```

코드만 읽어도 명확한 내용을 반복하지 않는다.

---

# 23. 오류 처리

Mock API라도 최소한의 오류 처리를 구현한다.

예:

- Prompt가 비어 있음
- 모델 목록이 비어 있음
- 지원하지 않는 모델 이름
- 업로드 파일 없음
- 지원하지 않는 파일 확장자

Pydantic Validation과 FastAPI의 기존 Error 처리 방식을 우선 사용한다.

프로젝트에 없는 복잡한 Error Architecture를 새로 만들지 않는다.

예외를 무조건 삼키는 방식은 피한다.

```python
try:
    ...
except Exception:
    return None
```

오류 발생 위치가 확인 가능하도록 한다.

---

# 24. Logging

프로젝트에 기존 Logging 방식이 있다면 이를 따른다.

필요한 경우 중심 함수의 주요 단계에서 로그를 남긴다.

예:

```text
[AdminOCR] request received
[AdminOCR] request validation completed
[AdminOCR] mock result created
[AdminOCR] response created
```

또는:

```text
[AdminLLM] compare request received
[AdminLLM] 3 mock model results created
[AdminLLM] response returned
```

과도한 로그를 추가하지 않는다.

사용자 입력 전체나 민감 정보가 불필요하게 로그에 남지 않도록 한다.

---

# 25. Frontend 통신 검증

구현 후 실제 Frontend와 통신 가능한지 확인한다.

확인 항목:

- FastAPI 서버 정상 실행
- Admin Router 정상 등록
- API Prefix 정상
- Frontend API URL과 일치
- CORS 문제 없음
- Request Schema 정상
- Response Schema 정상
- Frontend fetch / axios 호출 성공
- Frontend에서 Mock 데이터 정상 표시
- FastAPI `/docs`에서 API 호출 가능

가능한 경우 Frontend의 실제 Admin 화면에서 확인한다.

---

# 26. 현재 구현하지 않을 기능

이번 작업에서는 다음 기능을 구현하지 않는다.

- 실제 PaddleOCR
- 실제 EasyOCR
- 실제 Tesseract
- 실제 Ollama 호출
- Gemma 실제 실행
- Qwen 실제 실행
- MedGemma 실제 실행
- Fine-tuning
- LoRA
- QLoRA
- Embedding
- Vector DB
- RAG
- Reranker
- 실제 AI 학습
- 의료 Dataset 처리
- 실제 DB 저장이 필요하지 않은 Mock 기능의 DB 영속화
- Background Worker
- Redis
- Celery
- Kafka

현재 목표는 **Frontend ↔ Backend 통신 구조와 API 계약을 먼저 확정하는 것**이다.

---

# 27. 기존 코드 수정 범위

Admin 기능 구현에 필요하지 않은 파일은 수정하지 않는다.

특히 다음 영역은 가능한 손대지 않는다.

- 일반 사용자 페이지
- 로그인 / 회원가입
- 마이페이지
- 메인 Chat 페이지
- 팀원이 작성한 Router
- 팀원이 작성한 Service
- 인증 로직
- DB Schema
- 공통 Layout
- 기존 API Response

`main.py`에 Admin Router 등록이 필요한 경우처럼 실제 실행을 위해 필요한 최소 수정만 허용한다.

---

# 28. 권장 파일 배치

실제 프로젝트 분석 후 기존 Naming Convention에 맞춘다.

예시:

```text
backend/
└── app/
    ├── routers/
    │   ├── admin_ocr.py
    │   └── admin_llm.py
    │
    ├── services/
    │   ├── admin_ocr_service.py
    │   └── admin_llm_service.py
    │
    ├── schemas/
    │   ├── admin_ocr.py
    │   └── admin_llm.py
    │
    └── main.py
```

Mock 코드가 커질 경우에만 Service 내부 또는 별도 Mock 모듈로 분리한다.

예:

```text
services/
├── admin_ocr_service.py
├── admin_llm_service.py
└── mocks/
    ├── ocr_mock.py
    └── llm_mock.py
```

단, 현재 규모에서 필요하지 않다면 불필요하게 파일을 늘리지 않는다.

---

# 29. Admin OCR 최종 코드 흐름

코드상 다음 흐름이 명확하게 보여야 한다.

```text
React OCR Admin
→ POST /admin/.../ocr
→ OCR Router
→ Admin OCR Service 중심 함수
→ Request Validation
→ Mock OCR Result 생성
→ Response Schema 생성
→ Router
→ React
```

---

# 30. Admin LLM 최종 코드 흐름

```text
React LLM Admin
→ POST /admin/.../llm
→ LLM Router
→ Admin LLM Service 중심 함수
→ Request Validation
→ 모델별 Mock Result 생성
→ Response Schema 생성
→ Router
→ React
```

---

# 31. 구현 순서

한 번에 과도하게 작업하지 않는다.

## STEP 1. Repository 분석

현재 Backend와 Admin Frontend 구조를 확인한다.

## STEP 2. API 계약 확인

Frontend가 요구하는 Request / Response 구조를 확인한다.

## STEP 3. Schema 구현

Pydantic Request / Response를 정의한다.

## STEP 4. Mock Service 구현

각 기능별 중심 함수를 만든다.

## STEP 5. Router 연결

Router에서는 중심 Service 함수만 호출한다.

## STEP 6. main.py 연결

필요한 경우 Admin Router를 기존 방식대로 등록한다.

## STEP 7. Frontend 통신 테스트

실제 Admin 화면에서 Request / Response를 확인한다.

## STEP 8. 기존 기능 회귀 확인

Admin 외 기존 API가 영향을 받지 않았는지 확인한다.

---

# 32. Codex가 임의로 하지 말아야 할 것

명시적으로 요구하지 않는 한 다음 작업을 하지 않는다.

- 전체 프로젝트 Architecture 변경
- 기존 폴더 대규모 이동
- 기존 API URL 변경
- 기존 Response Format 변경
- DB Migration
- 기존 인증 방식 변경
- 라이브러리 임의 교체
- 모든 Service를 Interface로 변경
- Clean Architecture 전면 도입
- Repository Pattern 전면 재작성
- Microservice 분리
- Background Task 추가
- Queue 추가
- Redis / Celery / Kafka 도입
- 실제 AI 모델 다운로드
- 실제 OCR 모델 다운로드
- 대규모 Refactoring

---

# 33. 구현 완료 후 보고 형식

작업을 완료한 뒤 반드시 다음 내용을 정리한다.

## 33.1 현재 Backend 구조 분석 결과

Admin 기능과 관련된 기존 구조를 짧게 설명한다.

## 33.2 생성 파일

```text
파일 경로
→ 역할
```

## 33.3 수정 파일

```text
파일 경로
→ 변경 이유
```

## 33.4 OCR API 흐름

```text
Frontend
→ Router
→ Service 중심 함수
→ Mock
→ Response
```

## 33.5 LLM API 흐름

```text
Frontend
→ Router
→ Service 중심 함수
→ Mock
→ Response
```

## 33.6 API 목록

| Method | URL | Request | Response | 목적 |
|---|---|---|---|---|
| POST | 실제 구현 URL | Schema | Schema | OCR Mock |
| POST | 실제 구현 URL | Schema | Schema | LLM Mock |

## 33.7 Request / Response 예시

실제 구현된 Schema 기준 JSON 예시를 제공한다.

## 33.8 Mock 교체 위치

향후 실제 OCR / LLM 구현 시 어느 함수 또는 어느 줄을 교체하면 되는지 명확히 설명한다.

예:

```text
admin_llm_service.py
create_mock_model_results()
→ 실제 Ollama 호출 함수로 교체
```

## 33.9 기존 코드 영향

Admin 외 기존 코드에 어떤 영향을 주었는지 설명한다.

가능하면:

```text
Admin Router 등록 외 기존 기능 변경 없음
```

처럼 명확하게 작성한다.

## 33.10 실행 방법

FastAPI 실행 방법과 테스트 Endpoint를 정리한다.

---

# 34. 최종 검증 기준

다음 조건을 모두 확인한다.

- [ ] 기존 프로젝트 구조를 변경하지 않았다.
- [ ] Admin 관련 범위만 최소 수정했다.
- [ ] FastAPI가 정상 실행된다.
- [ ] Frontend Admin 페이지에서 실제 API 요청이 가능하다.
- [ ] OCR API가 Backend Mock Response를 반환한다.
- [ ] LLM API가 Backend Mock Response를 반환한다.
- [ ] Request / Response Schema가 명확하다.
- [ ] Router에 Mock 비즈니스 로직을 직접 넣지 않았다.
- [ ] 기능별 중심 Service 함수가 존재한다.
- [ ] 중심 함수만 읽어도 전체 실행 순서를 파악할 수 있다.
- [ ] 하위 함수는 결과를 중심 함수로 반환한다.
- [ ] Service 간 불필요한 연쇄 호출이 없다.
- [ ] 주요 코드에 이해를 돕는 한국어 주석이 있다.
- [ ] Mock 처리 위치가 명확하다.
- [ ] 향후 실제 OCR / LLM 로직으로 쉽게 교체 가능하다.
- [ ] 실제 OCR / Ollama / RAG 등은 아직 구현하지 않았다.
- [ ] 기존 다른 페이지 및 API 동작에 영향을 주지 않았다.

---

# 35. 가장 중요한 기준

이번 작업의 목적은 실제 AI 기능 완성이 아니다.

현재 우선순위는 다음과 같다.

```text
1. 기존 프로젝트 보존
2. Frontend ↔ FastAPI 통신
3. Request / Response 구조 확정
4. 기능별 중심 실행 흐름 확보
5. Backend Mock 데이터 반환
6. 코드 이해를 돕는 주석
7. 향후 실제 구현으로 쉽게 교체
```

최종적으로 다음 흐름이 단순하고 명확하게 보여야 한다.

```text
Frontend 요청
→ FastAPI Router
→ Admin Service 중심 함수
→ Mock 처리
→ Response 생성
→ Frontend 표시
```

그리고 실제 AI/OCR 기능이 준비된 이후에는:

```text
Mock 처리
```

부분만:

```text
실제 OCR / Ollama / AI Service
```

로 교체할 수 있어야 한다.

---

# 36. 코드 가독성 최종 원칙

이 프로젝트에서는 복잡한 Architecture Pattern 적용 자체보다 **사람이 기능 흐름을 쉽게 이해하는 것**을 우선한다.

우선순위:

```text
명확한 실행 흐름
> 과도한 추상화

유지보수성
> 코드 길이 최소화

현재 필요한 구조
> 미래 확장을 위한 과설계

읽기 쉬운 코드
> Design Pattern 적용 자체
```

처음 프로젝트를 보는 개발자가 다음 순서로 코드를 읽을 수 있어야 한다.

```text
Admin Router 확인
→ 연결된 Admin Service의 중심 함수 확인
→ 전체 처리 순서 이해
→ 필요한 세부 함수만 확인
```

목표는 파일 수를 줄이는 것이 아니라 **실행 흐름을 잃어버리지 않는 것**이다.
