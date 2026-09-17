# DOCX/PPTX OCR 지원 구현

작성일: 2026-08-20

## 1. 구현 결과

관리자 OCR 테스트에서 기존 PDF, PNG, JPG와 함께 DOCX와 PPTX를 업로드할 수 있도록 확장했다.

Office 문서를 별도의 OCR 방식으로 처리하지 않고 다음과 같이 기존 Hybrid PDF 파이프라인에 연결한다.

```text
DOCX/PPTX
→ OOXML 구조 검증
→ LibreOffice headless PDF 변환
→ 변환 PDF 재검증
→ 기존 Hybrid PDF 텍스트/OCR 처리
→ 텍스트 정제
→ Chunking
→ 기존 응답 형식 반환
```

이 구조를 선택한 이유는 PDF에 이미 구현된 디지털 텍스트 추출, 포함 이미지 OCR, 스캔 페이지 OCR, 페이지 순서 유지 기능을 재사용하기 위해서다.

## 2. 지원 범위

| 입력 형식 | 처리 방법 |
| --- | --- |
| PNG, JPG, JPEG | 이미지 전처리 후 PaddleOCR |
| PDF | Native Text와 이미지 구조를 분석하는 Hybrid PDF 처리 |
| DOCX | LibreOffice로 PDF 변환 후 Hybrid PDF 처리 |
| PPTX | LibreOffice로 PDF 변환 후 Hybrid PDF 처리 |

다음 형식은 이번 구현 범위에 포함하지 않았다.

- DOC, PPT
- DOCM, PPTM 등 매크로 문서
- HWP, HWPX
- 암호화된 Office 문서

## 3. Backend 변경사항

### 3.1 Office 문서 검증

`document_validator.py`에서 다음 항목을 검증한다.

1. 허용 확장자와 MIME Type
2. ZIP 기반 OOXML 문서인지 여부
3. DOCX의 `word/document.xml` 존재 여부
4. PPTX의 `ppt/presentation.xml` 존재 여부
5. `[Content_Types].xml`, `_rels/.rels` 존재 여부
6. 암호화된 ZIP 엔트리 여부
7. `..` 또는 절대 경로를 사용한 안전하지 않은 내부 경로
8. 압축 내부 파일 개수 제한
9. 전체 압축 해제 크기 제한
10. ZIP CRC 손상 여부

DOCX 파일명을 PPTX로 바꾸는 것처럼 확장자와 실제 내부 형식이 다르면 변환 전에 거부한다.

### 3.2 LibreOffice 변환 계층

새 파일 `office_converter_service.py`의 책임은 다음과 같다.

- LibreOffice 실행 파일 탐색
- 작업별 임시 입력·출력·프로필 디렉터리 생성
- headless PDF 변환 subprocess 실행
- 제한시간 적용
- 종료 코드와 PDF 생성 여부 확인
- 변환 결과 크기 제한
- 작업 완료 후 임시 파일 자동 정리

각 작업은 별도의 LibreOffice 사용자 프로필 URI를 사용한다. 여러 작업이 같은 기본 프로필 lock을 공유하지 않게 하기 위한 설정이다.

실행 개념은 다음과 같다.

```text
soffice
-env:UserInstallation=<작업별 profile URI>
--headless
--convert-to pdf
--outdir <작업별 output>
<작업별 source.docx 또는 source.pptx>
```

### 3.3 변환 후 재검증

LibreOffice가 파일을 생성했더라도 곧바로 PDF 파서로 전달하지 않는다.

- PDF signature
- 암호화 여부
- 페이지 존재 여부
- 최대 페이지 수
- 페이지 객체 손상 여부

를 업로드 PDF와 동일하게 다시 검증한다.

### 3.4 중심 처리 서비스

`DocumentProcessingService._extract_document()`의 분기는 다음과 같이 변경되었다.

```text
image → 이미지 OCR
pdf   → 기존 PDF 처리
docx  → PDF 변환 → 기존 PDF 처리
pptx  → PDF 변환 → 기존 PDF 처리
```

응답 API 계약은 변경하지 않았다. 결과 `notes`에는 Office 문서인 경우 다음 정보가 추가된다.

```text
원본 형식: DOCX 또는 PPTX
PDF로 변환해 분석했다는 안내
원본 프로그램과 글꼴·도형 배치가 달라질 수 있다는 안내
```

진행 상태에는 `converting` 단계가 추가되었다.

## 4. Frontend 변경사항

- 파일 선택 `accept`에 `.docx`, `.pptx` 추가
- 지원 형식 안내 문구 갱신
- Mock 서비스 지원 확장자 갱신
- Office 파일 선택 시 브라우저 직접 미리보기 대신 PDF 변환 처리 안내 표시

브라우저는 DOCX/PPTX를 PDF처럼 직접 렌더링하지 않기 때문에 현재 화면에서는 원본 파일 미리보기를 제공하지 않는다. 서버 변환 PDF를 미리보기로 제공하려면 변환 산출물 조회 API와 임시 저장소가 별도로 필요하다.

## 5. Container 변경사항

Backend Docker 이미지에 다음 OS 패키지를 설치한다.

```text
libreoffice-writer
libreoffice-impress
fonts-liberation
fonts-noto-cjk
```

Writer는 DOCX, Impress는 PPTX 변환에 사용한다. Liberation과 Noto CJK 글꼴은 영문·한글 대체 글꼴 누락을 줄이기 위한 기본 구성이다.

## 6. 환경 설정

| 환경 변수 | 기본값 | 의미 |
| --- | ---: | --- |
| `OCR_MAX_FILE_SIZE_MB` | 20 | 원본 업로드 최대 크기 |
| `OCR_MAX_PDF_PAGES` | 50 | 원본 및 변환 PDF 최대 페이지 수 |
| `OCR_MAX_OFFICE_UNCOMPRESSED_SIZE_MB` | 200 | OOXML 전체 압축 해제 크기 제한 |
| `OCR_MAX_OFFICE_ARCHIVE_ENTRIES` | 5000 | OOXML 내부 엔트리 수 제한 |
| `OCR_MAX_CONVERTED_PDF_SIZE_MB` | 50 | 변환 PDF 최대 크기 |
| `OCR_OFFICE_CONVERSION_TIMEOUT_SECONDS` | 120 | LibreOffice 변환 제한시간 |
| `OCR_OFFICE_CONVERTER_COMMAND` | `soffice` | LibreOffice 명령 또는 실행 파일 경로 |

Windows 로컬 환경에서 `soffice`가 PATH에 없다면 프로젝트 최상위 `.env`에 다음과 같이 실제 설치 경로를 지정한다.

```text
OCR_OFFICE_CONVERTER_COMMAND=C:\Program Files\LibreOffice\program\soffice.com
```

Windows에서는 subprocess의 완료 코드와 콘솔 출력을 안정적으로 받기 위해 GUI 래퍼인
`soffice.exe`보다 콘솔 실행 파일인 `soffice.com`을 사용한다.

Docker/Cloud Run에서는 이미지 안에 LibreOffice가 설치되므로 기본 `soffice` 값을 사용한다.

## 7. 오류 처리

| 상황 | 처리 |
| --- | --- |
| 잘못된 확장자/MIME | `DocumentValidationError` |
| 손상되거나 형식이 다른 OOXML | `DocumentValidationError` |
| 암호화 문서 | `DocumentValidationError` |
| LibreOffice 미설치 | `OfficeConversionError` |
| 변환 timeout | `OfficeConversionError` |
| 변환 PDF 미생성/크기 초과 | `OfficeConversionError` |
| 변환 PDF 손상/페이지 초과 | `DocumentValidationError` |

Job API에서는 위 도메인 오류가 OCR Job의 `failed` 상태와 사용자용 오류 메시지로 반환된다.

## 8. 테스트 결과

2026-08-20 기준 다음 검증을 완료했다.

```text
Backend: python -m unittest discover -s tests -v
결과: 28 tests, OK

Frontend: npm run build
결과: TypeScript 검사 및 Vite production build 성공
```

추가된 주요 테스트는 다음과 같다.

- DOCX → 가짜 변환 PDF → 기존 PDF 파이프라인 연결
- PPTX → 가짜 변환 PDF → 기존 PDF 파이프라인 연결
- 손상 OOXML 거부
- DOCX를 PPTX로 이름만 변경한 입력 거부
- 잘못된 Office MIME 거부
- 격리된 LibreOffice 프로필과 headless 명령 구성
- LibreOffice 실행 파일 부재 오류

로컬 개발 PC에는 LibreOffice 26.2.5.2를 설치하고 최상위 `.env`에
`soffice.com` 경로를 설정했다. LibreOffice가 생성한 실제 DOCX와 PPTX를 각각
현재 OOXML 검증기와 PDF 변환 서비스에 통과시키는 로컬 통합 테스트도 성공했다.

```text
DOCX: docx_bytes=5182 → pdf_bytes=15799
PPTX: pptx_bytes=6917 → pdf_bytes=13942
```

Docker daemon이 실행 중이 아니어서 Docker 이미지 빌드 검증은 수행하지 못했다.
배포 전에는 Docker 이미지에서도 실제 업무 DOCX/PPTX 샘플로 통합 테스트해야 한다.

## 9. 알려진 제한사항

- LibreOffice 변환 결과는 Microsoft Word/PowerPoint와 완전히 동일하지 않을 수 있다.
- 설치되지 않은 글꼴은 대체되며 줄바꿈, 페이지 수, 도형 위치가 달라질 수 있다.
- PowerPoint 애니메이션, 영상, 일부 OLE 개체는 정적 PDF에 보존되지 않는다.
- PPTX 발표자 노트는 기본 슬라이드 PDF 변환 결과에 포함되지 않는다.
- DOCX의 변경 추적, 주석, 복잡한 필드는 최종 PDF 표현에 따라 결과가 달라진다.
- Native Text가 있는 변환 PDF는 OCR하지 않으므로 표시되는 confidence는 변환 정확도를 의미하지 않는다.
- Office 변환이 추가되어 컨테이너 이미지 크기, cold start, CPU와 메모리 사용량이 증가한다.

## 10. 배포 전 확인사항

1. 실제 Docker 이미지가 LibreOffice와 글꼴을 정상 설치하는지 확인
2. 한글 DOCX, 표 중심 DOCX, 도형 중심 PPTX의 변환 결과 확인
3. Cloud Run CPU/메모리/concurrency/timeout 명시
4. 동시 변환 시 메모리 사용량 측정
5. 변환 실패와 timeout 로그 확인
6. 민감 문서의 임시 파일이 작업 종료 후 정리되는지 확인
