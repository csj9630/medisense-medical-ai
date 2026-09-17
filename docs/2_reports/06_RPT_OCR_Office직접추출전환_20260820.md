# OCR Office 직접 추출 전환 결과 보고서

작성일: 2026-08-20  
구분: 작업 결과 보고서  
대상: 관리자 OCR의 DOCX/PPTX 처리

## 1. 작업 목적

기존 DOCX/PPTX 처리에서는 모든 Office 문서를 LibreOffice headless로 PDF 변환한 뒤 기존 Hybrid PDF 파이프라인에 전달했다.

이번 작업에서는 RAG용 텍스트 추출이라는 프로젝트 목적과 협업·배포 편의성을 기준으로 다음 구조로 전환했다.

```text
기존
DOCX/PPTX → LibreOffice → PDF → Hybrid PDF 분석 → Chunking

변경
DOCX → python-docx + OOXML 보완 → 포함 이미지 OCR → Chunking
PPTX → python-pptx → 포함 이미지 OCR → Chunking
```

LibreOffice는 기본 경로뿐 아니라 Backend 필수 의존성에서도 제거했다. 정확한 Office 페이지 렌더링이 필요한 사용자는 원본 프로그램에서 PDF로 내보낸 뒤 PDF를 업로드하는 방식으로 처리한다.

## 2. 구현 결과 요약

| 항목 | 결과 |
| --- | --- |
| DOCX 기본 처리 | OOXML 직접 추출로 전환 |
| PPTX 기본 처리 | OOXML 직접 추출로 전환 |
| Office 포함 이미지 | 기존 PaddleOCR로 선택 처리 |
| LibreOffice subprocess | 제거 |
| LibreOffice 환경 변수 | 제거 |
| Docker LibreOffice 패키지 | 제거 |
| DOCX 실제 페이지 수 | `null` 반환 |
| PPTX 슬라이드 수 | `pageCount`에 슬라이드 수 반환 |
| Frontend 표시 | DOCX `계산 안 됨`, PPTX `슬라이드` 표시 |

## 3. Backend 변경 사항

### 3.1 직접 파서 추가

새 파일 `office_parser_service.py`에 다음 계약과 구현을 추가했다.

- `OfficeDocumentParser`
- `DirectOfficeDocumentParser`
- `ParsedOfficeDocument`
- `OfficeContentUnit`
- `OfficeImage`

중심 처리 서비스는 구체적인 라이브러리에 직접 의존하지 않고 `OfficeDocumentParser` 계약만 사용한다.

### 3.2 DOCX 직접 추출

`python-docx`를 사용해 다음 요소를 추출한다.

- 제목과 일반 문단
- 목록 문단
- 표의 행·열
- 텍스트 상자
- 변경 추적 삽입 내용
- 각주와 미주
- 본문에 연결된 이미지

다음 요소는 경고를 남기거나 제외한다.

- 변경 추적 삭제 내용
- `altChunk` 외부 콘텐츠
- OLE 또는 임베디드 객체
- 텍스트 상자의 정확한 화면상 위치

DOCX 실제 페이지 수는 Word 렌더링 결과이므로 직접 파싱만으로 정확하게 계산하지 않는다. 문서 속성의 페이지 수는 오래되거나 잘못될 수 있어 API에서 `null`을 반환한다.

### 3.3 PPTX 직접 추출

`python-pptx`를 사용해 다음 요소를 슬라이드 단위로 추출한다.

- 텍스트 상자와 placeholder 텍스트
- 그룹 도형 내부 텍스트
- 표
- 이미지
- 차트 제목과 계열명
- 발표자 노트

슬라이드 도형은 `top`, `left` 좌표를 기준으로 위→아래, 왼쪽→오른쪽 순서로 정렬한다.

SmartArt, Diagram, OLE는 완전한 의미 복원이 어려우므로 결과 경고에 누락 가능성을 표시한다.

### 3.4 Office 이미지 OCR

직접 파서가 찾은 이미지는 기존 이미지 전처리와 PaddleOCR를 재사용한다.

```text
Office 이미지
→ 이미지 디코딩
→ 최대 픽셀 검증
→ EXIF 방향·투명 배경 처리
→ 최대 변 길이 제한
→ 64×64 미만 수준의 작은 이미지 제외
→ PaddleOCR
→ 해당 문서/슬라이드 텍스트 뒤에 이미지 OCR 추가
```

동일 이미지 바이트는 중복 처리하지 않는다. OCR할 수 없는 벡터 이미지나 손상 이미지는 문서 전체를 실패시키지 않고 경고를 남긴 뒤 건너뛴다.

### 3.5 오류 계약 변경

기존 `OfficeConversionError`를 제거하고 `OfficeExtractionError`로 교체했다.

직접 파싱할 수 없는 문서에는 다음 복구 방향을 안내한다.

- Word 또는 PowerPoint에서 새 파일로 다시 저장
- 원본 프로그램에서 PDF로 내보낸 뒤 PDF 업로드

### 3.6 설정 정리

다음 LibreOffice 전용 설정을 제거했다.

- `OCR_MAX_CONVERTED_PDF_SIZE_MB`
- `OCR_OFFICE_CONVERSION_TIMEOUT_SECONDS`
- `OCR_OFFICE_CONVERTER_COMMAND`

최상위 `.env.example`과 로컬 `.env`에서도 LibreOffice 실행 경로를 제거했다.

유지한 Office 보안 설정:

- `OCR_MAX_OFFICE_UNCOMPRESSED_SIZE_MB`
- `OCR_MAX_OFFICE_ARCHIVE_ENTRIES`

OOXML도 ZIP 기반 입력이므로 경로 순회, 암호화, ZIP CRC, 압축 해제 크기, 엔트리 개수 검증은 계속 필요하다.

### 3.7 Python 의존성

`backend/requirements.txt`에 다음 패키지를 추가했다.

```text
python-docx>=1.2,<2.0
python-pptx>=1.0,<2.0
```

로컬 가상환경 설치 결과:

- `python-docx 1.2.0`
- `python-pptx 1.0.2`
- 전이 의존성: `lxml 6.1.2`, `XlsxWriter 3.2.9`

## 4. LibreOffice 제거 사항

삭제 또는 정리한 항목:

- `office_converter_service.py`
- LibreOffice 변환 Protocol과 구현
- subprocess 실행과 120초 timeout
- 임시 입력·출력·프로필 디렉터리
- 변환 PDF 검증 경로
- LibreOffice 전용 단위 테스트
- Docker의 `libreoffice-writer`
- Docker의 `libreoffice-impress`
- PDF 변환용 글꼴 패키지 설치
- Windows `soffice.com` 환경 변수

Docker는 Python requirements 설치만 수행한다.

## 5. API 및 Frontend 변경

### 5.1 `pageCount`

Backend와 Frontend의 타입을 다음과 같이 변경했다.

```text
기존: number
변경: number | null
```

형식별 의미:

| 형식 | `pageCount` |
| --- | --- |
| PDF | 실제 PDF 페이지 수 |
| PNG/JPG | `1` |
| PPTX | 슬라이드 수 |
| DOCX | `null` |

### 5.2 결과 UI

- PPTX 결과는 `페이지` 대신 `슬라이드`로 표시한다.
- DOCX 결과는 페이지 수 대신 `계산 안 됨`을 표시한다.
- DOCX/PPTX 선택 화면에서 PDF 변환 안내를 제거했다.
- Office 문서는 텍스트·표·이미지 구조를 직접 분석한다고 안내한다.
- 정확한 페이지 미리보기가 필요하면 PDF 업로드를 안내한다.

## 6. 테스트 변경

LibreOffice mock PDF 테스트를 실제 OOXML 문서 생성·직접 추출 테스트로 교체했다.

추가·갱신한 주요 검증:

- DOCX 제목·문단·표 추출
- DOCX 페이지 수 `null`
- PPTX 슬라이드 텍스트 추출
- PPTX 발표자 노트 추출
- DOCX 포함 이미지 OCR
- PPTX 포함 이미지 OCR
- 읽을 수 없는 DOCX 구조의 도메인 오류
- 기존 PDF Native/Hybrid/Scanned 처리 회귀 검증
- 이미지 전처리와 Chunking 회귀 검증

## 7. 검증 결과

### 7.1 Backend

```text
명령: .venv\Scripts\python.exe -m unittest discover -s tests -v
결과: 31 tests, OK
```

Python compileall도 통과했다.

### 7.2 Frontend

```text
명령: npm.cmd run build
결과: TypeScript 검사 및 Vite production build 성공
```

### 7.3 실제 샘플 직접 파싱

파일 읽기 시간과 PaddleOCR 실행은 제외하고 직접 구조 파싱만 측정했다.

| 문서 | 크기 | 결과 | 추출 문자 | 이미지 | 파싱 시간 |
| --- | ---: | --- | ---: | ---: | ---: |
| `File.docx` | 14,046B | 성공 | 675 | 0 | 0.0111초 |
| 개발자 이력서 DOCX | 249,112B | 성공 | 13,966 | 1 | 0.0863초 |
| `프레젠테이션1.pptx` | 78,608B | 성공 | 1,214 | 2 | 0.0207초 |

문제 사례였던 `09_.docx`는 검증 시점에 기존 G: 경로에서 파일이 사라져 새 파서로 재실행하지 않았다. 이전 정적 분석에서는 표·이미지·매크로가 없는 일반 텍스트 OOXML로 확인됐으므로 직접 추출 경로에 적합한 유형이다.

## 8. 알려진 제한 사항

- DOCX 실제 페이지 수와 페이지별 출처를 제공하지 않는다.
- DOCX 텍스트 상자는 문서 끝에 모아 추출한다.
- PPTX 좌표 정렬은 사람이 의도한 읽기 순서와 다를 수 있다.
- SmartArt, OLE, 복잡한 차트 의미를 완전하게 복원하지 않는다.
- Office 벡터 이미지는 Pillow/PaddleOCR에서 처리하지 못할 수 있다.
- Office 원본 화면 미리보기는 제공하지 않는다.

정확한 화면 순서, 페이지 번호, 원본 레이아웃 확인이 필요한 문서는 PDF로 내보내 업로드해야 한다.

## 9. 협업 및 배포 영향

개발자가 별도로 수행하던 다음 작업이 사라졌다.

- LibreOffice 설치
- LibreOffice 버전 통일
- `soffice` PATH 또는 절대 경로 설정
- Windows와 Linux의 headless 차이 확인
- 서버 글꼴 패키지 조정
- LibreOffice 자식 프로세스와 timeout 진단

이제 Python requirements 설치만으로 DOCX/PPTX 직접 추출 경로를 재현할 수 있다.

## 10. 변경 파일

주요 추가:

- `backend/app/services/hybrid_ocr/office_parser_service.py`
- `docs/2_reports/06_RPT_OCR_Office직접추출전환_20260820.md`
- `docs/3_flow/05_FLW_OCR_전체구조흐름_20260820.md`

주요 삭제:

- `backend/app/services/hybrid_ocr/office_converter_service.py`

주요 수정:

- Backend 중심 처리, 모델, 오류, 설정, requirements, Dockerfile, 테스트, README
- Frontend 결과 타입, 결과 요약, Office 미리보기 안내, Mock 결과
- 최상위 `.env.example`

## 11. 작업 완료 상태

- LibreOffice 기반 DOCX/PPTX 처리 제거 완료
- DOCX/PPTX 직접 추출 구현 완료
- Office 이미지 OCR 연결 완료
- Backend 테스트 완료
- Frontend 빌드 완료
- 실제 샘플 직접 파싱 완료
- Git commit은 수행하지 않음

