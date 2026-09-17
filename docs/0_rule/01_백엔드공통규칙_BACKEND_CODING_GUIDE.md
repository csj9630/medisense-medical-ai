# Backend Development Common Guide

> 이 문서는 특정 기능 구현을 위한 요구사항이 아니라 **프로젝트의 백엔드 코드를 작성·수정할 때 항상 적용해야 하는 공통 개발 규칙**이다.
>
> Codex 또는 다른 AI Agent에 별도의 기능 구현 프롬프트를 제공하더라도 이 문서가 함께 제공되었다면 **아래 원칙을 공통 개발 기준으로 적용한다.**
>
> 기능별 요구사항은 별도 프롬프트를 따르되, 코드 구조와 작성 방식은 가능한 한 이 문서를 따른다.

## <!-- 실행예시 : BACKEND_CODING_GUIDE.md의 공통 개발 원칙을 준수하면서 관리자 OCR API를 구현해라. -->

---

# 1. 가장 중요한 목표

백엔드 코드는 단순히 동작하는 것뿐 아니라 **초심자가 코드를 따라가면서 전체 실행 흐름을 이해할 수 있어야 한다.**

특히 다음 질문에 코드를 보면서 답할 수 있도록 작성한다.

- 요청이 어디에서 시작되는가?
- 어떤 함수가 전체 작업 순서를 관리하는가?
- 어떤 외부 로직을 호출하는가?
- 호출 결과가 어디로 돌아오는가?
- 다음 단계는 무엇인가?
- 최종 결과는 어디에서 반환되는가?

가능하면 코드를 처음 보는 사람이 **위에서 아래로 읽으면서 실행 순서를 따라갈 수 있는 구조**를 만든다.

---

# 2. 하나의 기능에는 중심 흐름을 관리하는 함수가 있어야 한다

하나의 기능을 구현할 때는 전체 처리 순서를 관리하는 **중심 함수(Main Flow / Orchestrator)**를 둔다.

예를 들어 OCR 문서 처리 기능이라면 다음과 같은 형태를 권장한다.

```python
def process_document(file):
    # 1. 파일 검증
    validated_file = validate_file(file)

    # 2. OCR 실행
    extracted_text = run_ocr(validated_file)

    # 3. 텍스트 정제
    cleaned_text = clean_text(extracted_text)

    # 4. Chunk 생성
    chunks = create_chunks(cleaned_text)

    # 5. 결과 구성
    result = build_result(
        extracted_text=cleaned_text,
        chunks=chunks,
    )

    return result
```

이 함수만 읽어도 다음 흐름을 파악할 수 있어야 한다.

```text
파일 입력 → 검증 → OCR → 텍스트 정제 → Chunking → 결과 반환
```

각 단계의 세부 구현이 다른 파일에 존재하더라도 **전체 실행 순서는 중심 함수에서 확인 가능해야 한다.**

---

# 3. 외부 함수를 호출해도 반드시 중심 흐름으로 복귀한다

기능 구현 중 다른 Service, Repository, Utility 등의 함수를 호출할 수 있다.

하지만 실행 흐름이 호출된 파일 내부에서 계속 이어지도록 만들지 않는다.

권장 구조:

```text
중심 함수

→ A 함수 호출
← A 결과 반환

→ B 함수 호출
← B 결과 반환

→ C 함수 호출
← C 결과 반환

→ 최종 결과 생성
```

예:

```python
def create_document(request):
    validated = document_validator.validate(request)

    saved_document = document_repository.save(validated)

    chunks = chunk_service.create_chunks(
        saved_document.text
    )

    return build_document_response(
        document=saved_document,
        chunks=chunks,
    )
```

가능하면 다음과 같은 구조를 피한다.

```text
A 함수
 ↓
B 함수
 ↓
C 함수
 ↓
D 함수
 ↓
Repository
 ↓
E 함수
```

이처럼 실행 흐름이 여러 파일을 연속적으로 이동하면 초심자가 전체 처리 과정을 파악하기 어려워진다.

---

# 4. 함수 호출은 "요청 → 결과 반환" 형태를 우선한다

함수는 가능하면 하나의 작업을 수행하고 **명확한 결과를 호출자에게 반환**한다.

예:

```python
text = ocr_service.extract_text(file)

chunks = chunk_service.split_text(text)

document = document_repository.save(
    text=text,
    chunks=chunks,
)
```

다음과 같이 함수 내부에서 너무 많은 다음 작업까지 자동으로 이어서 실행하는 구조는 필요하지 않다면 피한다.

```python
ocr_service.extract_and_chunk_and_save_and_embed(file)
```

기능을 지나치게 하나의 함수에 몰아넣으면 내부 동작을 이해하기 어렵다.

반대로 지나치게 작은 함수로 쪼개어 실행 흐름을 여러 파일로 분산시키는 것도 피한다.

**기능 단위로 적절하게 분리하되 전체 순서는 중심 함수에서 읽을 수 있어야 한다.**

---

# 5. 주요 코드에는 한국어 주석을 작성한다

초심자가 기능을 이해할 수 있도록 주요 코드에 **한국어 주석을 작성한다.**

주석은 코드 문법을 그대로 읽어주는 것이 아니라 다음 내용을 설명한다.

- 이 코드가 왜 필요한지
- 이 단계에서 무엇을 하는지
- 이전 단계에서 무엇을 받았는지
- 다음 단계에 무엇을 전달하는지
- 이해하기 어려운 라이브러리/API의 역할

좋은 예:

```python
# 사용자가 업로드한 파일이 OCR 처리 가능한 형식인지 먼저 확인한다.
validated_file = validate_upload_file(file)

# OCR 엔진에 파일을 전달하고 추출된 문자열을 반환받는다.
extracted_text = ocr_service.extract_text(validated_file)

# RAG 검색에 사용할 수 있도록 긴 텍스트를 작은 Chunk 단위로 나눈다.
chunks = chunk_service.create_chunks(extracted_text)
```

필요하지 않은 주석:

```python
# 변수를 만든다.
text = ""

# 함수를 호출한다.
result = execute()
```

코드만 봐도 알 수 있는 내용을 반복하는 주석은 작성하지 않는다.

---

# 6. 중심 함수에는 단계 번호 주석을 권장한다

여러 단계가 존재하는 Service의 중심 함수에는 실행 순서를 쉽게 따라갈 수 있도록 단계 번호를 사용할 수 있다.

예:

```python
async def process_rag_document(file: UploadFile):

    # 1. 업로드 파일 검증
    validated_file = validate_document(file)

    # 2. 문서에서 텍스트 추출
    extracted_text = await ocr_service.extract_text(
        validated_file
    )

    # 3. RAG 검색에 사용할 Chunk 생성
    chunks = chunk_service.create_chunks(
        extracted_text
    )

    # 4. Chunk를 Embedding Vector로 변환
    embeddings = embedding_service.embed(
        chunks
    )

    # 5. VectorDB에 문서와 Embedding 저장
    saved_document = document_repository.save(
        chunks=chunks,
        embeddings=embeddings,
    )

    # 6. Frontend에서 사용할 결과 반환
    return build_document_response(saved_document)
```

이 함수만 확인해도 전체 구조를 다음처럼 이해할 수 있어야 한다.

```text
파일 검증 → OCR → Chunking → Embedding → VectorDB 저장 → Response
```

---

# 7. FastAPI 계층별 책임을 명확하게 구분한다

FastAPI 프로젝트에서는 가능한 다음 책임 구분을 따른다.

```text
Router
  ↓
Service
  ↓
Repository
  ↓
Database
```

필요한 경우:

```text
Service
  ↓
AI / OCR / LLM / Embedding 모듈
```

을 호출할 수 있다.

---

## Router

Router는 HTTP 요청과 응답을 담당한다.

주요 역할:

- URL Endpoint
- HTTP Method
- Request DTO
- Response DTO
- Dependency Injection
- 인증 정보 전달
- Service 호출

Router 안에 실제 비즈니스 로직을 길게 작성하지 않는다.

예:

```python
@router.post("/documents")
async def upload_document(
    file: UploadFile,
    service: DocumentService = Depends(get_document_service),
):
    return await service.process_document(file)
```

Router는 가능하면 다음 정도로 읽혀야 한다.

```text
HTTP 요청 받음 → Service 호출 → 결과 반환
```

---

# 8. Service를 기능 실행 흐름의 중심으로 사용한다

Service는 **하나의 기능 전체 실행 순서를 관리하는 핵심 계층**으로 사용한다.

예:

```python
class DocumentService:

    async def process_document(self, file):

        # 1. 파일 검증
        validated = validate_file(file)

        # 2. OCR 실행
        text = await self.ocr_service.extract(validated)

        # 3. Chunk 생성
        chunks = self.chunk_service.create(text)

        # 4. 데이터 저장
        document = self.repository.save(
            text=text,
            chunks=chunks,
        )

        # 5. 결과 반환
        return document
```

가능하면 Service의 중심 함수에서 **전체 비즈니스 흐름을 확인할 수 있도록 유지한다.**

---

# 9. Repository는 DB 작업에 집중한다

Repository는 데이터베이스 접근을 담당한다.

예:

```python
def save_document(self, document):
    ...

def find_document_by_id(self, document_id):
    ...

def delete_document(self, document_id):
    ...
```

Repository에서 다음 작업을 수행하지 않는다.

- OCR 실행
- LLM 호출
- Prompt 생성
- HTTP Response 결정
- 사용자 입력 검증의 전체 흐름 관리
- 다른 Service의 비즈니스 로직 실행

Repository의 역할은 가능한 한:

```text
데이터 저장
데이터 조회
데이터 수정
데이터 삭제
```

에 집중한다.

---

# 10. Schema / DTO는 데이터 형태를 설명한다

Pydantic Schema를 이용해 요청과 응답 형태를 명확히 한다.

예:

```python
class LlmTestRequest(BaseModel):
    question: str
    model_ids: list[str]


class LlmTestResponse(BaseModel):
    model: str
    answer: str
    elapsed_time: float
```

초심자가 Schema만 보고도:

```text
Frontend에서 무엇을 보내는가?
Backend에서 무엇을 반환하는가?
```

를 알 수 있도록 한다.

---

# 11. Utility에 비즈니스 로직을 숨기지 않는다

`utils/`는 여러 기능에서 사용할 수 있는 단순 보조 기능만 둔다.

예:

```text
날짜 변환
문자열 정리
파일명 생성
공통 포맷 변환
```

다음과 같은 핵심 비즈니스 로직을 `utils`에 넣지 않는다.

```text
OCR 전체 실행
RAG 검색 전체 과정
회원가입 전체 처리
LLM 응답 생성 전체 과정
```

이런 기능은 Service 또는 해당 기능 모듈에 둔다.

---

# 12. 한 함수의 책임을 명확하게 한다

가능하면 함수 이름만 보고 무엇을 하는지 알 수 있도록 한다.

좋은 예:

```python
validate_document()
extract_text()
create_chunks()
generate_embeddings()
save_document()
generate_llm_answer()
```

피해야 할 이름:

```python
process()
execute()
handle()
run()
do_work()
```

단, 전체 실행 흐름을 담당하는 중심 함수라면 다음과 같은 이름은 사용할 수 있다.

```python
process_document()
run_ocr_pipeline()
run_llm_comparison()
execute_rag_pipeline()
```

이 경우 내부 단계가 주석과 함수 호출을 통해 명확하게 보여야 한다.

---

# 13. 지나친 추상화를 피한다

교육 프로젝트에서는 지나치게 복잡한 디자인 패턴보다 **읽기 쉬운 구조를 우선한다.**

필요하지 않다면 다음과 같은 구조를 과도하게 추가하지 않는다.

- Factory
- Abstract Factory
- Strategy
- Command
- Mediator
- Event Bus
- 복잡한 Dependency Container
- 과도한 Generic
- 지나친 Interface 계층

실제 교체 가능성이 있거나 여러 구현체가 존재하는 경우에는 사용할 수 있지만, 단순한 기능 하나를 위해 불필요한 계층을 만들지 않는다.

---

# 14. 지나친 함수 분리를 피한다

다음과 같은 식으로 한 줄짜리 함수를 지나치게 만들지 않는다.

```python
def get_text(data):
    return data.text


def clean(data):
    return data.strip()


def convert(data):
    return str(data)
```

함수 분리는 다음 기준으로 판단한다.

- 독립적인 역할이 있는가?
- 다른 곳에서도 재사용되는가?
- 외부 서비스/API/DB를 호출하는가?
- 테스트할 가치가 있는 단위인가?
- 중심 함수의 가독성이 좋아지는가?

---

# 15. 예외 처리도 흐름을 읽을 수 있게 작성한다

예외 발생 위치와 의미를 알 수 있도록 한다.

예:

```python
try:
    extracted_text = await ocr_service.extract(file)
except OcrProcessingError as exc:
    raise DocumentProcessingError(
        "OCR 처리 중 오류가 발생했습니다."
    ) from exc
```

모든 코드에 무조건 `try/except`를 추가하지 않는다.

처리할 수 있는 계층에서만 예외를 처리한다.

---

# 16. 로그는 주요 단계 중심으로 남긴다

기능 실행 흐름을 추적할 수 있도록 주요 단계에 로그를 남긴다.

예:

```python
logger.info("OCR 문서 처리 시작")

logger.info(
    "OCR 텍스트 추출 완료: characters=%d",
    len(extracted_text),
)

logger.info(
    "Chunk 생성 완료: count=%d",
    len(chunks),
)
```

비밀번호, Token, API Key, 개인정보 등 민감한 값은 로그에 출력하지 않는다.

---

# 17. 비동기 함수는 필요한 곳에서만 사용한다

FastAPI라는 이유만으로 모든 함수를 `async`로 만들지 않는다.

네트워크, 파일 I/O, 외부 API, 비동기 DB 등 실제 비동기 처리가 필요한 곳에서는 `async/await`을 사용한다.

단순 계산이나 문자열 처리 함수는 일반 함수로 작성할 수 있다.

예:

```python
async def call_llm():
    ...
```

```python
def split_chunks():
    ...
```

---

# 18. 데이터 흐름을 명확하게 유지한다

함수 간 데이터를 암묵적으로 공유하기보다 파라미터와 반환값으로 전달하는 방식을 우선한다.

권장:

```python
text = extract_text(file)

chunks = create_chunks(text)

embeddings = create_embeddings(chunks)

result = save_embeddings(
    chunks,
    embeddings,
)
```

가능하면 전역 상태를 이용해 다음 함수가 이전 함수의 결과를 암묵적으로 가져가도록 만들지 않는다.

---

# 19. 새 기능을 구현할 때 먼저 실행 흐름을 정의한다

복잡한 기능을 바로 코드로 작성하지 않는다.

먼저 다음과 같은 한 줄 흐름을 정리한다.

예:

```text
파일 업로드 → 검증 → OCR → Chunking → Embedding → VectorDB 저장
```

또는:

```text
질문 입력 → 모델 목록 확인 → 각 LLM 호출 → 결과 취합 → 비교 결과 반환
```

그 다음 이 흐름을 중심 함수 코드에 그대로 반영한다.

---

# 20. 신규 기능 구현 시 권장 작업 순서

새로운 Backend 기능을 구현할 때 가능하면 다음 순서로 진행한다.

### 1. 현재 프로젝트 구조 확인

기존:

- Router
- Service
- Repository
- Schema
- Model
- Dependency
- Config

구조를 먼저 확인한다.

### 2. 실행 흐름 정의

예:

```text
Request → Router → Service → Repository → DB → Service → Response
```

### 3. Request / Response Schema 정의

Frontend와 Backend의 데이터 계약을 먼저 명확히 한다.

### 4. 중심 Service 함수 작성

기능 전체 실행 순서를 확인할 수 있는 중심 함수를 작성한다.

### 5. 세부 기능 분리

필요한 경우:

- Repository
- OCR
- LLM
- Embedding
- Utility

등으로 분리한다.

### 6. Router 연결

Service의 중심 함수를 Endpoint에 연결한다.

### 7. 로그와 예외 처리 추가

### 8. 실행 흐름 검증

---

# 21. 코드 작성 후 반드시 실행 흐름을 설명한다

기능 구현이 끝나면 변경 파일만 나열하지 말고 **실제 실행 순서를 함께 설명한다.**

예:

```text
POST /api/admin/ocr
→ admin/router.py
→ DocumentService.process_document()
→ OcrService.extract_text()
→ ChunkService.create_chunks()
→ DocumentRepository.save()
→ DocumentService로 결과 반환
→ OcrResponse 생성
→ Frontend 반환
```

그리고 각 단계가 어느 파일에 있는지 설명한다.

---

# 22. 파일 간 호출 관계를 설명한다

작업 완료 보고에는 가능하면 다음 표를 포함한다.

| 순서 | 파일                     | 함수                 | 역할                |
| ---- | ------------------------ | -------------------- | ------------------- |
| 1    | `router.py`              | `upload_document()`  | HTTP 요청 수신      |
| 2    | `document_service.py`    | `process_document()` | 전체 실행 흐름 관리 |
| 3    | `ocr_service.py`         | `extract_text()`     | OCR 처리            |
| 4    | `chunk_service.py`       | `create_chunks()`    | Chunk 생성          |
| 5    | `document_repository.py` | `save()`             | DB 저장             |
| 6    | `document_service.py`    | `process_document()` | 결과 취합           |
| 7    | `router.py`              | `upload_document()`  | HTTP Response 반환  |

초심자가 이 표와 코드를 함께 보면서 실행 흐름을 따라갈 수 있도록 한다.

---

# 23. 기존 프로젝트 구조를 우선한다

이 문서는 공통 원칙이지만 기존 프로젝트가 이미 명확한 아키텍처를 가지고 있다면 이를 무리하게 변경하지 않는다.

예를 들어 기존 프로젝트가:

```text
routers/
services/
repositories/
schemas/
models/
```

구조라면 이를 유지한다.

이 지침을 적용하기 위해 기존 코드를 대규모로 리팩터링하지 않는다.

현재 기능 구현에 필요한 범위에서 적용한다.

---

# 24. 기존 코드 수정 범위를 최소화한다

새 기능 하나를 추가하기 위해 관련 없는 파일을 수정하지 않는다.

특히 다음을 피한다.

- 불필요한 프로젝트 전체 리팩터링
- 디렉터리 구조 전체 변경
- 기존 API 이름 변경
- 기존 DTO 임의 변경
- 사용 중인 라이브러리 교체
- 관련 없는 코드 formatting 대량 변경

협업 프로젝트에서는 **작은 변경 범위**를 우선한다.

---

# 25. 기존 기능을 먼저 분석하고 재사용한다

새 코드를 작성하기 전에 기존 코드에서 다음을 확인한다.

- 공통 DB Session
- API Router 등록 방식
- Error 처리 방식
- Logging 방식
- Repository 패턴
- Schema 작성 방식
- 인증 Dependency
- Config
- 기존 Utility
- 테스트 방식

이미 존재하는 기능을 중복 구현하지 않는다.

---

# 26. 학습 목적의 코드 가독성을 우선한다

이 프로젝트에서는 최소 코드 길이보다 **이해 가능한 코드**를 우선한다.

다음과 같은 코드를 목표로 한다.

```python
async def compare_llm_models(request):

    # 1. 비교할 모델 목록을 검증한다.
    models = validate_models(request.model_ids)

    # 2. 각 모델에 동일한 질문을 전달한다.
    results = []

    for model in models:
        result = await llm_service.generate(
            model=model,
            question=request.question,
        )

        results.append(result)

    # 3. Frontend에서 비교할 수 있도록 결과를 하나로 묶는다.
    return build_comparison_response(results)
```

복잡한 한 줄 표현보다 실행 순서를 이해하기 쉬운 형태를 선호한다.

---

# 27. AI가 코드를 생성할 때 적용할 원칙

Codex 또는 AI Agent는 다음 기준을 따른다.

1. 먼저 기존 프로젝트 구조를 읽는다.
2. 구현 전에 현재 구조와 연결 지점을 파악한다.
3. 기존 아키텍처를 최대한 유지한다.
4. 한 기능에 전체 흐름을 관리하는 중심 함수를 둔다.
5. 다른 파일의 함수를 호출한 뒤 결과를 중심 함수로 반환받는다.
6. 주요 처리 단계에 이해를 위한 한국어 주석을 작성한다.
7. Router에는 HTTP 처리 위주로 작성한다.
8. Service에 비즈니스 실행 흐름을 둔다.
9. Repository에는 DB 접근을 둔다.
10. Utility에 핵심 비즈니스 로직을 숨기지 않는다.
11. 필요하지 않은 추상화와 디자인 패턴을 추가하지 않는다.
12. 기존 기능을 불필요하게 변경하지 않는다.
13. 보안 정보와 환경변수 값을 코드에 하드코딩하지 않는다.
14. 작업 후 실행 흐름과 파일별 역할을 설명한다.

---

# 28. 최종 체크 기준

새 기능 구현 후 다음 질문에 모두 답할 수 있어야 한다.

- HTTP 요청을 처음 받는 함수는 어디인가?
- 전체 기능 실행 순서를 관리하는 함수는 어디인가?
- 입력 데이터의 형태는 어디에 정의되어 있는가?
- DB 접근 함수는 어디에 있는가?
- 외부 API/AI 호출은 어디에서 이루어지는가?
- 각 외부 함수가 반환한 값은 어디로 돌아오는가?
- 최종 Response는 어디에서 만들어지는가?
- 오류가 발생했을 때 어느 단계인지 확인할 수 있는가?
- 주요 코드의 목적을 한국어 주석으로 이해할 수 있는가?

이 질문에 답하기 어렵다면 구조를 다시 검토한다.

---

# 핵심 원칙 요약

가장 중요한 구조는 다음과 같다.

```text
HTTP Request
→ Router
→ 중심 Service 함수
→ 세부 기능 A 호출
→ 결과 반환
→ 중심 Service 함수
→ 세부 기능 B 호출
→ 결과 반환
→ 중심 Service 함수
→ Repository 호출
→ 결과 반환
→ 중심 Service 함수에서 최종 결과 조립
→ Router
→ HTTP Response
```

즉,

**다른 파일로 작업을 위임하더라도 실행 흐름의 주도권은 중심 함수가 유지한다.**

코드를 처음 보는 사람이 중심 함수를 읽으면서

```text
입력 → 처리 → 저장 → 결과
```

의 전체 흐름을 이해할 수 있도록 작성하는 것을 가장 중요한 기준으로 한다.
