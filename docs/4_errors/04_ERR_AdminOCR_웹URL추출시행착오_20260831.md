# Admin OCR 웹 URL 추출 시행착오 및 장애 대응

> 상태: 2026-08-31 질병관리청 건강정보 실페이지에서 발생한 본문 오선택과 내부 이미지 누락 문제의 재현, 원인, 수정 및 재발 방지 내용을 기록한다.

- 작성일: 2026-08-31
- 대상 기능: Admin OCR 웹페이지 URL 수집
- 관련 구현 보고서: `docs/2_reports/16_RPT_AdminOCR_웹URL수집확장_20260831.md`
- 관련 지시서: `docs/1_prompts/11_PRM_AdminOCR_웹URL수집확장지시서_20260831.md`
- 영향 범위: HTML 본문 추출, 내부 이미지 후보 선정, 이미지 다운로드 검증, 품질 확인 메모
- 비영향 범위: Gemini Embedding, `document_chunks`, Neon Schema, RAG 검색

---

## 1. 장애 요약

웹 URL OCR의 기본 구현과 자동 테스트는 통과했지만 실제 공공기관 페이지에서 다음 두 문제가 순차적으로 확인됐다.

| 구분 | 사용자 관찰 결과 | 직접 원인 |
|---|---|---|
| 본문 누락 | 상세 건강정보 대신 주제별 분류 문구 78자만 추출 | 첫 `<article>`이 본문이라고 가정했고, 실제 본문을 감싼 `<form>` 자식까지 삭제 |
| 이미지 누락 | 콘텐츠 이미지 4개가 있었지만 공공누리 배지만 OCR | 정상 JPEG 응답의 잘못된 `Content-Type: doesn/matter`를 MIME Allowlist에서 거부 |
| 경고 개수 불일치 | 이미지 4개가 실패했는데 경고는 3줄 | Alt Text가 같은 두 이미지의 경고 문자열이 같아 중복 제거됨 |

두 장애 모두 Library 자체의 오류가 아니라 실제 웹페이지 구조와 HTTP 응답이 초기 가정과 달라 발생했다.

---

## 2. 장애 1: 본문 대신 분류 필터만 추출

### 2.1 재현 URL

```text
https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/
gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=6765
```

### 2.2 증상

Admin OCR 결과에 다음 내용만 나타났다.

```text
주제별 전체 건강문제 치료방법 검사방법 생활습관 관리
신체계통별
성별
연령별
```

실제 페이지에는 고혈압의 요약, 정의, 원인, 진단, 치료 등 긴 본문이 있었으므로 정상 결과가 아니었다.

### 2.3 최초 구현의 잘못된 가정

초기 본문 선택은 다음 우선순위를 사용했다.

```text
첫 번째 <main>
→ 없으면 첫 번째 <article>
→ 없으면 <body>
```

일반적인 Blog나 Article 페이지에는 유효할 수 있지만 HTML Tag의 의미가 실제 콘텐츠 역할과 반드시 일치하지는 않는다.

질병관리청 페이지 구조는 다음과 달랐다.

```text
<article class="src-subject-wrap">
  주제별 분류 필터
</article>

<form ...>
  <div class="data-content">
    실제 고혈압 상세 본문
  </div>
</form>
```

페이지에는 `<main>`이 없었고 첫 `<article>`은 본문이 아니라 분류 UI였다.

### 2.4 두 번째 원인: Form 전체 삭제

초기 노이즈 제거 목록에는 다음 요소가 포함됐다.

```text
script, style, nav, footer, form, iframe, canvas, svg ...
```

`form.drop_tree()`는 Form Tag만 없애는 것이 아니라 모든 자식도 함께 삭제한다. 이 페이지는 실제 본문 전체를 Form으로 감싸므로 본문 후보 `data-content` 자체가 분석 전에 사라졌다.

결국 Parser에는 분류 Article만 남았고, 첫 Article 선택 로직이 해당 문구를 정상 본문으로 오인했다.

### 2.5 진단 과정

단순히 추출 결과만 보는 대신 다음 정보를 비교했다.

1. 원본 HTML 전체 문자 수
2. `main`, `article` 개수
3. `div`, `section`, `article` 후보별 전체 Text 길이
4. 후보별 `id`, `class`
5. Heading·Paragraph·List·Table의 Text 합계
6. Link Text 비율과 Form Control 개수

주요 후보는 다음과 같았다.

| 후보 | 역할 | 원본 Text 규모 |
|---|---|---:|
| `article.src-subject-wrap` | 주제별 분류 필터 | 약 2천 자 |
| `div.data-content` | 실제 상세 건강정보 | 약 2만 1천 자 |
| `div#print-content` | 인쇄용 상세 본문 | 약 2만 자 |

이 비교로 Semantic Tag 우선순위보다 콘텐츠 밀도와 Marker가 더 신뢰할 수 있음을 확인했다.

### 2.6 수정 내용

#### Form 자식 보존

```python
for node in root.xpath("//form"):
    node.drop_tag()
```

Form 자체는 제거하지만 내부 Text와 Image는 그대로 유지한다.

#### 콘텐츠 후보 점수화

다음 요소를 조합해 후보별 점수를 계산한다.

- Heading, Paragraph, List, Blockquote, Pre, Table Text 길이
- 전체 Text 길이
- `main`, `role=main`, `article` Semantic 가점
- `data-content`, `print-content`, `article-body` 등 본문 Marker 가점
- `filter`, `menu`, `search`, `subject-wrap`, `sidebar` 등 탐색 Marker 감점
- Link Text 비율 감점
- Button, Input, Select, Textarea 개수 감점

첫 번째 요소를 고정 선택하지 않고 가장 높은 점수의 후보를 실제 본문 Root로 사용한다.

### 2.7 수정 결과

| 항목 | 수정 전 | 수정 후 |
|---|---:|---:|
| 추출 Text | 78자 | 7,641자 |
| 제목 `고혈압` | 누락 | 포함 |
| 정의·원인·진단·치료 | 누락 | 포함 |
| 콘텐츠 Image 후보 | 0개 | 8개 |

---

## 3. 장애 2: 정상 JPEG를 미지원 형식으로 거부

### 3.1 재현 URL

```text
https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/
gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=5830
```

### 3.2 증상

두통 본문 Text는 정상적으로 추출됐지만 품질 확인 메모에 다음 경고가 표시됐다.

```text
내부 이미지 수집을 건너뛰었습니다 (...): 지원하지 않는 이미지 형식입니다.
```

페이지의 콘텐츠 이미지 4개는 건너뛰고 공공누리 라이선스 배지만 OCR됐다.

### 3.3 최초 구현의 잘못된 가정

초기 이미지 검증은 HTTP Header를 먼저 검사했다.

```text
image/jpeg
image/png
image/webp
```

Allowlist에 없는 `Content-Type`이면 Body의 실제 형식을 확인하기 전에 거부했다. 일반적인 웹서버는 올바른 MIME을 보낸다는 가정이었다.

### 3.4 실제 응답 분석

질병관리청 이미지 다운로드 Endpoint의 응답은 다음과 같았다.

```text
HTTP 200
Content-Type: doesn/matter
```

그러나 실제 Byte와 Pillow 판정은 모두 정상 JPEG였다.

| 콘텐츠 이미지 | Byte Magic | Pillow Format | 크기 |
|---|---|---|---:|
| 1 | `FF D8 FF E1` | JPEG | 550×766 |
| 2 | `FF D8 FF E0` | JPEG | 550×592 |
| 3 | `FF D8 FF E0` | JPEG | 550×544 |
| 4 | `FF D8 FF E0` | JPEG | 799×856 |

HTTP Metadata가 틀렸지만 실제 파일은 지원 형식이었다.

### 3.5 수정 내용

#### 실제 File Signature 우선

HTTP `Content-Type`을 최종 형식 판정 기준에서 제외했다. 다운로드 후 다음 조건을 모두 통과해야 OCR 대상으로 인정한다.

1. 개별·전체 Streaming Byte 제한
2. Pillow Image Decode 성공
3. 실제 Format이 JPEG, PNG, WebP 중 하나
4. 최소 가로·세로 크기 충족
5. 최대 Pixel 수 제한 충족
6. `image.verify()` 성공

Header를 덜 신뢰하게 바꿨지만 실제 Byte 검증이 최종 신뢰 경계이므로 HTML이나 임의 Binary가 이미지로 통과하지는 않는다.

#### 장식 이미지 제외

실제 본문 안에도 OCR 가치가 낮은 라이선스 배지, Logo, Icon이 존재할 수 있다. Image 자신과 상위 요소의 ID·Class·URL에서 다음 Marker를 검사한다.

```text
badge, copyright, footer, icon, license, logo, open-box
```

질병관리청 공공누리 이미지는 `open-box` 안에 있어 OCR 후보에서 제외된다.

#### 경고 식별 개선

Alt Text는 고유 식별자가 아니다. 두 콘텐츠 이미지가 같은 Alt Text를 사용해 동일한 경고 문구가 생성됐고, 경고 중복 제거 단계에서 한 줄이 사라졌다.

수정 후 경고에 이미지 순번을 포함한다.

```text
내부 이미지 #2 수집을 건너뛰었습니다 (...): 실패 원인
```

### 3.6 수정 결과

| 항목 | 수정 전 | 수정 후 |
|---|---:|---:|
| 콘텐츠 Image 후보 | 4개 | 4개 |
| 다운로드·실제 Format 검증 성공 | 0개 | 4개 |
| MIME 관련 경고 | 3줄 | 0개 |
| 공공누리 배지 OCR | 실행 | 후보 제외 |

`PaddleOCR 처리 이미지` 수는 다운로드 성공 개수가 아니라 실제 인식 Text가 생성된 Image 개수다. 다운로드된 4개 중 인식 가능한 Text가 없는 Image가 있다면 이 수는 4보다 작을 수 있으며 해당 사유가 Warning에 남는다.

---

## 4. 왜 초기 자동 테스트에서 발견하지 못했는가

초기 Fixture는 다음과 같이 이상적인 HTML과 HTTP 응답만 사용했다.

```text
<main> 또는 실제 본문 <article> 존재
본문이 Form 밖에 존재
이미지 Content-Type이 image/png 또는 image/jpeg
Image Alt Text가 서로 다름
본문 내부에 License Badge가 없음
```

즉 구현한 정상 경로는 검증했지만 웹의 비정상·레거시 관행을 충분히 반영하지 못했다.

보완한 Test Case는 다음과 같다.

- Filter Article과 별도 `data-content`가 함께 있는 HTML
- 실제 본문이 Form 내부에 있는 HTML
- 잘못된 `Content-Type`을 가진 정상 JPEG
- 본문 안의 Copyright·License Badge
- 같은 Alt Text를 사용하는 복수 이미지

---

## 5. 재발 방지 원칙

### 5.1 Semantic Tag는 힌트이지 보장이 아니다

`main`, `article`, `section`이라는 Tag 이름만으로 본문 여부를 결정하지 않는다. Text 밀도, Link 비율, Form Control 수, Class Marker를 함께 평가한다.

### 5.2 제거와 Tag 해제를 구분한다

```text
drop_tree(): Element와 모든 자식 제거
drop_tag(): Element Tag만 제거하고 자식 보존
```

Script나 Style은 `drop_tree()`가 맞지만 Form처럼 본문을 감쌀 수 있는 요소는 `drop_tag()`를 사용한다.

### 5.3 HTTP Header와 실제 Byte를 분리 검증한다

- Header는 빠른 Hint로만 사용한다.
- 보안 및 Format 판정은 실제 Byte Signature와 Decoder 결과를 기준으로 한다.
- 실제 Decode 전에도 Streaming 크기 제한을 적용해 대용량 입력을 방지한다.

### 5.4 Alt Text를 식별자로 사용하지 않는다

Alt Text는 접근성 설명이며 중복될 수 있다. 로그와 경고에는 후보 순번 또는 URL 기반 식별자를 함께 사용한다.

### 5.5 실사이트 회귀 검증이 필요하다

Fixture만으로는 공공기관·Legacy CMS·Download Endpoint의 비표준 구조를 모두 재현하기 어렵다. 대표 사이트 URL은 외부 상태에 의존하지 않는 최소 Fixture로 변환해 자동 테스트에 남긴다.

---

## 6. 장애 대응 체크리스트

### 본문이 지나치게 짧을 때

1. 원본 HTML Byte·문자 수 확인
2. 추출 Text 길이와 비교
3. `main`, `article`, `role=main` 개수 확인
4. 후보별 ID·Class·Text 길이 출력
5. 실제 본문이 Form, Template, Iframe 안에 있는지 확인
6. Link 중심 탐색 영역이 선택됐는지 확인
7. JavaScript 렌더링 이후에만 본문이 생기는지 확인

### 이미지가 건너뛰어질 때

1. 후보 Image 개수와 URL 확인
2. HTTP 상태 및 Redirect 확인
3. `Content-Type`, Content-Length 확인
4. 앞 16 Byte Magic Number 확인
5. Pillow Format·크기·`verify()` 결과 확인
6. 개별·전체 Byte Budget 확인
7. 최소 크기·최대 Pixel 제한 확인
8. 장식 이미지 Marker에 오탐됐는지 확인
9. PaddleOCR 결과가 빈 Text인지 확인

---

## 7. 관련 코드와 테스트

### 수정 코드

- `ai/ocr/extractors/web.py`
- `backend/app/services/web_document_fetcher.py`

### 회귀 테스트

- `backend/tests/test_web_ocr.py`
  - 밀도 높은 본문 Container 선택
  - Form 내부 본문 보존
  - 잘못된 MIME의 정상 JPEG 허용
  - 장식 Badge 제외
  - 이미지 Byte Budget 유지

### 최종 검증

| 검증 | 결과 |
|---|---|
| Web OCR 전용 unittest | 12개 통과 |
| Backend 전체 unittest | 75개 통과 |
| Python Compile | 통과 |
| `git diff --check` | 통과 |
| 고혈압 실페이지 HTML 추출 | 7,641자, 본문 포함 |
| 두통 실페이지 콘텐츠 이미지 Fetch | 4/4 성공, 경고 0개 |

---

## 8. 남은 제한 사항

- JavaScript 실행 후에만 본문이 생성되는 SPA는 현재 HTML Fetch 방식으로 처리하지 못한다.
- Iframe 내부 문서는 별도 URL 수집 대상으로 자동 확장하지 않는다.
- CSS Background Image는 현재 OCR 후보가 아니다.
- 장식 Image Marker는 일반 규칙이므로 사이트에 따라 추가 조정이 필요할 수 있다.
- 외부 사이트의 HTML 구조와 응답 정책이 바뀌면 실페이지 결과도 달라질 수 있다.

이번 장애의 핵심 교훈은 웹 수집에서 표준적인 Tag와 Header를 신뢰하되, 그것만을 최종 판정 기준으로 사용해서는 안 된다는 점이다.
