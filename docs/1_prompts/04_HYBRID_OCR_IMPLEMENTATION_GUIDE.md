# Hybrid OCR 구현 작업 지시서

> 2026-08-20 변경: 최초 작업 범위 이후 DOCX/PPTX의 PDF 변환 지원이 추가되었다.
> 현재 구현 내용은 `11_DOCX_PPTX_OCR_지원_구현_2026-08-20.md`, 전체 실행 구조는
> `12_OCR_전체_구조_흐름_분석_2026-08-20.md`를 기준으로 확인한다.

## 1. 작업 목적

현재 프로젝트에 **이미지 및 PDF 문서를 처리할 수 있는 Hybrid OCR 기능**을 구현한다.

이번 OCR 기능의 목적은 OCR 모델 성능 비교가 아니라,

**RAG에 등록할 문서에서 가능한 정확하게 텍스트를 추출하는 것**

이다.

따라서 과거 OCR 프로젝트처럼 여러 OCR 엔진을 동시에 실행하지 않는다.

이번 프로젝트에서는 다음 OCR 엔진만 사용한다.

```text
PaddleOCR
```

기존 Sub OCR 프로젝트의 OCR 구조와 전처리 경험은 참고하되, 기존 코드를 그대로 복사하지 않는다.

현재 프로젝트의 구조와 목적에 맞게 필요한 기능만 단순화하여 구현한다.

---

# 2. 핵심 처리 원칙

문서에 이미 디지털 텍스트가 존재한다면 OCR을 사용하지 않는다.

OCR은 **OCR이 필요한 이미지 영역에만 사용한다.**

전체 기본 흐름은 다음과 같다.

```text
파일 업로드
→ 파일 검증
→ 파일 종류 판별
→ 문서 분석
→ 디지털 텍스트 직접 추출
→ OCR이 필요한 이미지 추출
→ 이미지 전처리
→ PaddleOCR
→ 디지털 텍스트 + OCR 텍스트 통합
→ 텍스트 정제
→ Chunking
→ 결과 반환
```

이 구조를 Hybrid OCR의 기본 원칙으로 사용한다.

---

# 3. 지원 입력

이번 단계에서 우선 지원한다.

```text
PNG
JPG / JPEG
PDF
```

향후 다른 문서 포맷을 추가할 수 있도록 구조는 확장 가능하게 작성한다.

이번 작업에서는 DOCX, PPTX, HWP 등의 처리는 구현하지 않는다.

---

# 4. 파일 종류별 처리

## 4.1 일반 이미지

이미지 파일은 다음 흐름으로 처리한다.

```text
이미지
→ 파일 검증
→ 이미지 로드
→ EXIF 방향 보정
→ 이미지 크기 조정
→ 필요한 이미지 전처리
→ PaddleOCR
→ OCR 텍스트 정제
→ Chunking
→ 결과 반환
```

이미지는 전체 영역이 OCR 대상이다.

---

# 5. PDF 처리 원칙

PDF는 무조건 페이지 전체를 이미지로 변환하여 OCR하지 않는다.

먼저 PDF 내부의 디지털 텍스트와 이미지 구조를 분석한다.

PDF는 크게 다음 세 경우로 나누어 처리한다.

```text
PDF
├─ 디지털 PDF
├─ 디지털 텍스트 + 이미지 혼합 PDF
└─ 스캔 PDF
```

---

# 6. 디지털 PDF 처리

텍스트 선택이 가능한 일반 PDF는 Native Parser를 우선한다.

기본적으로 다음 라이브러리를 사용한다.

```text
PyMuPDF
pymupdf4llm
```

가능하면 `pymupdf4llm`을 사용해 문서 구조를 유지한 텍스트 또는 Markdown을 추출한다.

처리 흐름:

```text
PDF
→ pymupdf4llm
→ Native Text 추출
→ OCR 필요 여부 확인
→ OCR 대상이 없으면 추출 텍스트 확정
```

디지털 텍스트를 다시 이미지로 변환하여 PaddleOCR에 넣지 않는다.

---

# 7. 디지털 텍스트 + 이미지 PDF

텍스트와 그림/스캔 이미지가 함께 포함된 PDF는 Hybrid 방식으로 처리한다.

예:

```text
의학 논문
진료 안내 PDF
질환 설명 자료
검사 결과 설명 자료
```

등에서 다음과 같은 구조가 있을 수 있다.

```text
본문 텍스트

[표 또는 이미지]

본문 텍스트

[스캔된 문서 이미지]

본문 텍스트
```

이 경우 다음처럼 처리한다.

```text
PDF
→ pymupdf4llm
→ Native Text 추출
→ 포함 이미지 영역 탐색
→ 이미지 추출
→ 이미지 전처리
→ PaddleOCR
→ OCR 결과 반환
→ 원래 이미지 위치에 OCR 텍스트 삽입
→ 최종 문서 텍스트 생성
```

즉,

```text
Native Text
+
OCR Text
```

를 하나의 문서로 결합한다.

---

# 8. 이미지 위치에 OCR 결과 삽입

가능하면 `pymupdf4llm`이 생성한 Markdown 또는 문서 구조를 이용한다.

예:

```markdown
당뇨병은 혈당 조절에 이상이 발생하는 질환입니다.

![image](image_001.png)

주요 증상에는 다음과 같은 것들이 있습니다.
```

이미지 OCR 결과:

```text
정상 혈당 70~99 mg/dL
공복혈당장애 100~125 mg/dL
당뇨병 126 mg/dL 이상
```

최종 결과는 다음과 비슷한 구조가 되도록 한다.

```markdown
당뇨병은 혈당 조절에 이상이 발생하는 질환입니다.

[이미지 OCR]
정상 혈당 70~99 mg/dL
공복혈당장애 100~125 mg/dL
당뇨병 126 mg/dL 이상

주요 증상에는 다음과 같은 것들이 있습니다.
```

단순히 모든 OCR 텍스트를 문서 마지막에 붙이지 않는다.

가능한 한 원래 이미지가 있던 위치에 삽입해 문맥을 유지한다.

---

# 9. 스캔 PDF 처리

PDF 페이지에 실제 텍스트 레이어가 거의 없고 페이지 전체가 이미지 형태인 경우에는 스캔 PDF로 판단할 수 있다.

처리 흐름:

```text
스캔 PDF
→ PDF 페이지 렌더링
→ 페이지 이미지 생성
→ 이미지 전처리
→ PaddleOCR
→ 페이지별 OCR Text
→ 페이지 순서대로 병합
→ 최종 텍스트 생성
```

페이지 순서는 반드시 유지한다.

예:

```text
Page 1 OCR
→
Page 2 OCR
→
Page 3 OCR
```

형태로 결합한다.

---

# 10. PDF 유형 판단

PDF 유형을 단순히 확장자로 판단하지 않는다.

페이지에서 실제 추출되는 Native Text의 양과 이미지 존재 여부 등을 확인하여 처리 방법을 결정한다.

권장 개념:

```text
PDF 분석
→ Native Text 충분
    → 디지털 PDF

→ Native Text 있음 + 이미지 있음
    → Hybrid PDF

→ Native Text 거의 없음
    → 스캔 PDF
```

판단 기준은 별도의 함수로 분리한다.

예:

```python
analyze_pdf_structure()
```

반환 예:

```python
PdfAnalysisResult(
    has_native_text=True,
    has_images=True,
    requires_page_ocr=False,
)
```

구체적인 threshold는 코드에 흩어놓지 말고 constant 또는 config로 관리한다.

---

# 11. 이미지 전처리

기존 Sub OCR 프로젝트에서 사용했던 전처리 방식은 참고할 수 있다.

기존 프로젝트에서는 다음 처리들이 사용되었다.

```text
EXIF 방향 보정
Resize
Perspective Correction
Deskew
조명 보정
Noise 제거
CLAHE
Grayscale
Otsu
Adaptive Threshold
```

하지만 이번 프로젝트에서는 PaddleOCR 하나만 사용하므로 모든 전처리를 무조건 적용하지 않는다.

초기 기본 전처리는 단순하게 유지한다.

```text
이미지
→ EXIF 방향 보정
→ 적절한 Resize
→ 필요 시 Deskew
→ PaddleOCR
```

다음 기능은 필요한 경우에만 적용할 수 있도록 한다.

```text
Perspective Correction
Contrast 보정
Noise Reduction
CLAHE
```

과도한 이미지 전처리 때문에 원본 문자 형태가 손상되지 않도록 한다.

---

# 12. 이미지 전처리 구조

이미지 전처리는 OCR Service 안에 직접 길게 구현하지 않는다.

별도 모듈로 분리한다.

예:

```text
image_preprocessor.py
```

중심 함수 예:

```python
def preprocess_image(image):
    # 1. 이미지 방향을 정상화한다.
    image = correct_orientation(image)

    # 2. OCR 처리에 적절한 크기로 조정한다.
    image = resize_for_ocr(image)

    # 3. 기울어져 있는 문서는 필요한 경우 보정한다.
    image = deskew_if_needed(image)

    return image
```

주요 단계에는 기능 이해를 위한 한국어 주석을 작성한다.

---

# 13. PaddleOCR 전용 Service

PaddleOCR 호출 코드는 별도의 Service로 작성한다.

예:

```text
paddle_ocr_service.py
```

역할:

```text
PaddleOCR 초기화
OCR 실행
Paddle 결과 파싱
텍스트 추출
Confidence 계산
공통 결과 형식 반환
```

상위 Service가 PaddleOCR 라이브러리의 세부 반환 구조를 직접 다루지 않도록 한다.

예:

```python
result = paddle_ocr_service.extract_text(image)
```

반환 예:

```python
OcrResult(
    text="추출된 문서 내용",
    confidence=0.92,
    processing_time=1.42,
)
```

---

# 14. PaddleOCR 초기화

OCR 요청마다 PaddleOCR 모델을 새로 생성하지 않는다.

가능하면 애플리케이션 실행 중 PaddleOCR 인스턴스를 재사용한다.

예:

```text
FastAPI 실행
→ PaddleOCR 초기화
→ OCR 요청
→ 기존 PaddleOCR 인스턴스 사용
→ 결과 반환
```

GPU 사용 여부와 CPU fallback은 현재 실행 환경을 확인하여 적용한다.

GPU 초기화가 실패하면 CPU 실행이 가능하도록 구성하는 것을 권장한다.

단, 현재 프로젝트에 이미 공통 AI Device 설정 방식이 있다면 그것을 우선 사용한다.

---

# 15. 중심 실행 함수

Hybrid OCR 기능에는 전체 실행 흐름을 관리하는 중심 함수가 반드시 존재해야 한다.

예:

```python
async def process_document(file):
    """
    업로드된 문서를 분석하고 RAG에 사용할 텍스트를 생성하는 중심 함수.
    """

    # 1. 업로드 파일의 확장자, 크기, 손상 여부 등을 확인한다.
    validated_file = validate_document(file)

    # 2. 이미지인지 PDF인지 확인한다.
    file_type = detect_file_type(validated_file)

    # 3. 파일 형식에 맞는 문서 처리 함수를 호출한다.
    if file_type == "image":
        document_result = await process_image_document(
            validated_file
        )

    elif file_type == "pdf":
        document_result = await process_pdf_document(
            validated_file
        )

    # 4. 추출된 전체 텍스트를 RAG용으로 정리한다.
    cleaned_text = clean_document_text(
        document_result.text
    )

    # 5. RAG 검색에 사용할 Chunk를 만든다.
    chunks = create_chunks(cleaned_text)

    # 6. Frontend에서 검토할 수 있는 결과를 생성한다.
    return build_document_result(
        document_result=document_result,
        cleaned_text=cleaned_text,
        chunks=chunks,
    )
```

이 중심 함수만 읽어도 다음 실행 순서를 이해할 수 있어야 한다.

```text
검증
→ 파일 종류 확인
→ 이미지/PDF 처리
→ 텍스트 정제
→ Chunking
→ 결과 반환
```

---

# 16. PDF 중심 함수

PDF 내부에서도 전체 처리 순서를 확인할 수 있는 중심 함수를 둔다.

예:

```python
async def process_pdf_document(file):

    # 1. PDF 구조와 Native Text 존재 여부를 분석한다.
    pdf_info = analyze_pdf_structure(file)

    # 2. PDF의 디지털 텍스트와 문서 구조를 추출한다.
    native_document = extract_native_pdf_text(file)

    # 3. OCR이 필요한 이미지가 있는 경우 이미지 영역을 추출한다.
    images = extract_ocr_target_images(
        file,
        pdf_info,
    )

    # 4. 추출된 이미지만 PaddleOCR로 처리한다.
    ocr_results = []

    for image in images:
        processed_image = preprocess_image(image)

        ocr_result = paddle_ocr_service.extract_text(
            processed_image
        )

        ocr_results.append(ocr_result)

    # 5. Native Text와 OCR 결과를 원래 위치 기준으로 결합한다.
    merged_document = merge_native_and_ocr_text(
        native_document,
        ocr_results,
    )

    return merged_document
```

중요한 원칙:

```text
PDF Service
→ Image Preprocessor 호출
← 전처리 이미지 반환

PDF Service
→ PaddleOCR 호출
← OCR 결과 반환

PDF Service
→ Merge 함수 호출
← 통합 결과 반환
```

실행 흐름은 항상 중심 함수로 돌아온다.

---

# 17. 일반 이미지 중심 함수

이미지 처리 역시 복잡하게 만들 필요가 없다.

예:

```python
async def process_image_document(file):

    # 1. 업로드된 이미지 파일을 읽는다.
    image = load_image(file)

    # 2. PaddleOCR이 읽기 좋은 상태로 이미지를 정리한다.
    processed_image = preprocess_image(image)

    # 3. PaddleOCR을 실행하고 결과를 반환받는다.
    ocr_result = paddle_ocr_service.extract_text(
        processed_image
    )

    return ocr_result
```

실행 흐름:

```text
이미지 로드
→ 전처리
→ PaddleOCR
→ OCR 결과 반환
```

---

# 18. 텍스트 정제

OCR이 끝난 후 RAG에 사용하기 위한 최소한의 텍스트 정제를 수행한다.

예:

```text
불필요한 연속 공백 제거
과도한 빈 줄 제거
Unicode 정규화
페이지 구분 정리
OCR 결과의 불필요한 제어문자 제거
```

원문의 의미를 변경하는 적극적인 문장 교정은 하지 않는다.

OCR 오탈자를 LLM이 자동으로 수정하는 기능도 이번 Hybrid OCR 핵심 기능에 포함하지 않는다.

필요하다면 이후 별도의 단계로 추가한다.

---

# 19. Chunking

최종 통합 텍스트는 RAG에서 사용할 Chunk로 나눈다.

이번 Hybrid OCR 작업에서 Chunking은 기본 연결까지만 구현한다.

전체 관계:

```text
Hybrid OCR
→ Clean Text
→ Chunking
```

Embedding 및 VectorDB 저장은 별도 기능으로 분리한다.

즉 Hybrid OCR 중심 함수에서 직접 Embedding 또는 VectorDB 작업까지 실행하지 않는다.

---

# 20. OCR과 VectorDB 작업 분리

이번 관리자 기능의 목적상 OCR 테스트와 실제 RAG 등록은 분리한다.

권장 흐름:

```text
파일 업로드
→ Hybrid OCR
→ 추출 텍스트
→ Chunk Preview
→ Frontend 관리자 확인
```

그 다음 사용자가 저장을 선택하면:

```text
Chunk
→ Embedding
→ VectorDB
```

단계가 실행되도록 한다.

Hybrid OCR Service 내부에서 자동으로 VectorDB까지 저장하지 않는다.

---

# 21. 권장 Backend 구조

현재 프로젝트 구조를 먼저 분석하고 기존 구조를 우선 사용한다.

필요하다면 다음 구조를 참고한다.

```text
backend/app/
├─ api/
│  └─ admin/
│     └─ router.py
│
├─ services/
│  ├─ document_processing_service.py
│  ├─ pdf_parser_service.py
│  ├─ image_preprocessor.py
│  ├─ paddle_ocr_service.py
│  ├─ text_cleaner.py
│  └─ chunk_service.py
│
├─ schemas/
│  └─ admin_document.py
│
└─ repositories/
    └─ document_repository.py
```

단, 기존 프로젝트가 이미 다른 폴더 구조를 사용한다면 기존 구조를 우선한다.

이 지시서를 적용하기 위해 전체 프로젝트 디렉터리를 변경하지 않는다.

---

# 22. 각 파일의 권장 책임

| 파일                             | 책임                                      |
| -------------------------------- | ----------------------------------------- |
| `router.py`                      | HTTP 요청 수신 및 Response 반환           |
| `document_processing_service.py` | Hybrid OCR 전체 실행 흐름 관리            |
| `pdf_parser_service.py`          | PDF Native Text, 이미지, 페이지 구조 분석 |
| `image_preprocessor.py`          | OCR 이미지 보정                           |
| `paddle_ocr_service.py`          | PaddleOCR 초기화 및 실행                  |
| `text_cleaner.py`                | 최종 텍스트 정제                          |
| `chunk_service.py`               | RAG용 Chunk 생성                          |
| `document_repository.py`         | 필요한 경우 문서 DB 작업                  |
| `admin_document.py`              | Request/Response Schema                   |

---

# 23. API

관리자 OCR 테스트를 위한 Endpoint를 구현한다.

기존 프로젝트 Router 구조를 먼저 확인한 뒤 정확한 URL을 결정한다.

예:

```text
POST /api/admin/documents/analyze
```

입력:

```text
multipart/form-data
file
```

처리:

```text
파일
→ Hybrid OCR
→ Text 정제
→ Chunking
→ 결과 반환
```

반환 데이터 예:

```json
{
  "file_name": "medical_document.pdf",
  "document_type": "hybrid_pdf",
  "page_count": 12,
  "extracted_text": "...",
  "chunks": [
    {
      "index": 0,
      "text": "..."
    }
  ],
  "ocr": {
    "engine": "paddleocr",
    "image_count": 3,
    "average_confidence": 0.93
  }
}
```

구체적인 Schema 이름과 필드는 현재 Frontend의 `AdminAiService` 계약과 기존 Backend Schema를 확인하여 맞춘다.

Frontend 계약을 무시하고 임의로 응답 구조를 확정하지 않는다.

---

# 24. 파일 검증

서버에서 반드시 검증한다.

최소 검증 항목:

```text
지원 확장자
MIME Type
파일 크기
빈 파일
손상 이미지
손상 PDF
암호화 PDF
페이지 수
```

Frontend 검증만 신뢰하지 않는다.

잘못된 입력은 PaddleOCR까지 전달하지 않고 적절한 오류를 반환한다.

---

# 25. 임시 파일 관리

OCR을 위해 임시 파일 또는 PDF 이미지가 생성된다면 별도 작업 디렉터리를 사용한다.

예:

```text
temp/
├─ document_uuid/
│  ├─ page_001.png
│  ├─ page_002.png
│  └─ extracted_images/
```

작업 완료 후 필요하지 않은 임시 파일은 정리한다.

원본 문서의 영구 저장 여부는 OCR 기능과 분리하여 현재 프로젝트의 R2/Storage 정책을 따른다.

---

# 26. 로그

전체 처리 흐름을 확인할 수 있도록 주요 단계에 로그를 남긴다.

예:

```text
Hybrid OCR 시작
파일 검증 완료
PDF 분석 완료
Native Text 추출 완료
OCR 대상 이미지 3개 추출
PaddleOCR 시작
PaddleOCR 완료
텍스트 통합 완료
Chunk 25개 생성
Hybrid OCR 완료
```

개인정보가 포함된 문서 원문 전체를 로그에 출력하지 않는다.

---

# 27. 한국어 주석

주요 처리 코드에는 초심자가 이해할 수 있도록 한국어 주석을 작성한다.

특히 다음 부분에는 반드시 설명을 추가한다.

```text
PDF 유형 판별
Native Text 추출
이미지 추출
페이지 렌더링
이미지 전처리
PaddleOCR 호출
OCR 결과 파싱
Native/OCR Text 병합
Chunking
```

코드 문법 자체를 읽어주는 주석은 작성하지 않는다.

---

# 28. 기존 Sub OCR에서 가져올 것

기존 Sub OCR 프로젝트는 참고 자료로 사용한다.

다음 부분은 적극 참고할 수 있다.

```text
PyMuPDF / pymupdf4llm 사용 방식
PDF 검증 방식
EXIF 처리
이미지 Resize
Deskew
Perspective Correction
PaddleOCR 초기화
PaddleOCR 결과 변환
GPU → CPU fallback
OCR 실행 시간 측정
```

---

# 29. 기존 Sub OCR에서 제거할 것

다음 기능은 이번 프로젝트의 목적과 맞지 않으므로 가져오지 않는다.

```text
EasyOCR
Tesseract

3개 OCR asyncio.gather 병렬 비교

모델별 PENDING 상태

OCR 모델 비교

최적 OCR 엔진 선정

Ground Truth

CER

WER

OCR 정확도 비교 Report

모델별 재실행 API
```

이번 프로젝트는 PaddleOCR 단일 엔진으로 구현한다.

---

# 30. 과도한 구현 금지

이번 작업에서 다음 기능을 새로 추가하지 않는다.

```text
LLM OCR 교정
번역
Embedding
VectorDB 실제 저장
RAG 검색
Fine-tuning
OCR 모델 비교
OCR 성능 리포트
Celery / Redis 작업 큐
새로운 인증 구조
```

필요한 기능만 구현한다.

---

# 31. 기존 코드 보호

작업 전 현재 프로젝트 구조를 먼저 분석한다.

특히 다음을 확인한다.

```text
FastAPI Router 구조
Service 구조
Schema 구조
DB Session
Repository
Config
Logging
Exception 처리
Admin Frontend의 Request/Response 타입
```

이미 존재하는 코드를 재사용한다.

Hybrid OCR 구현을 위해 관련 없는 기존 기능을 수정하거나 리팩터링하지 않는다.

---

# 32. 테스트

최소한 다음 경우를 확인한다.

### 이미지

```text
정상 PNG
정상 JPG
회전된 이미지
큰 이미지
지원하지 않는 파일
손상 이미지
```

### PDF

```text
100% 디지털 PDF
텍스트 + 이미지 PDF
스캔 PDF
다중 페이지 PDF
빈 PDF
손상 PDF
암호화 PDF
```

특히 다음을 확인한다.

```text
디지털 PDF가 불필요하게 OCR되지 않는가?

Hybrid PDF에서 이미지 영역만 OCR되는가?

스캔 PDF가 페이지 OCR fallback으로 처리되는가?

페이지 순서가 유지되는가?

OCR 결과가 원래 문맥에 맞게 삽입되는가?
```

---

# 33. 작업 완료 후 실행 흐름 설명

작업 완료 후 반드시 실제 코드 기준으로 실행 흐름을 정리한다.

예:

```text
POST /api/admin/documents/analyze
→ admin/router.py
→ DocumentProcessingService.process_document()
→ PDFParserService.analyze()
→ PDFParserService.extract_native_text()
→ ImagePreprocessor.preprocess()
→ PaddleOcrService.extract_text()
→ DocumentProcessingService로 OCR 결과 반환
→ merge_native_and_ocr_text()
→ TextCleaner.clean()
→ ChunkService.create_chunks()
→ DocumentProcessingService에서 Response 구성
→ Router
→ Frontend
```

각 단계가 어느 파일과 함수에서 실행되는지도 표로 정리한다.

---

# 34. 가장 중요한 구현 원칙

이번 Hybrid OCR의 핵심은 다음과 같다.

```text
이미지
→ 전처리
→ PaddleOCR
→ Text

PDF
→ Native Text 우선 추출
→ OCR이 필요한 부분만 이미지화
→ 전처리
→ PaddleOCR
→ Native Text + OCR Text 병합
```

그리고 전체 흐름은 항상 중심 Service에서 관리한다.

```text
중심 함수
→ PDF Parser 호출
← 결과 반환

→ Image Preprocessor 호출
← 결과 반환

→ PaddleOCR 호출
← 결과 반환

→ Text Merge 호출
← 결과 반환

→ Chunk Service 호출
← 결과 반환

→ 최종 Response
```

**다른 파일에 세부 작업을 위임하더라도 실행 흐름의 주도권은 중심 함수에 유지한다.**

---

# 35. 최종 목표

최종적으로 다음 흐름이 작동해야 한다.

```text
관리자 파일 업로드
→ FastAPI
→ Hybrid OCR
→ Native Text + PaddleOCR Text
→ RAG용 정제 텍스트
→ Chunk 생성
→ 관리자 OCR 화면에 결과 반환
```

관리자는 반환된 결과를 확인한 후 별도의 VectorDB 저장 기능을 실행할 수 있어야 한다.

Hybrid OCR의 책임은 여기까지로 제한한다.
