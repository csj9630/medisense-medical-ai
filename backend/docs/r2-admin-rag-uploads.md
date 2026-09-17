# Admin RAG 8GB 업로드 설정

Admin RAG의 20MB 초과 파일은 Cloud Run 요청 본문을 거치지 않습니다. 브라우저가
64MB Part를 R2 presigned URL로 직접 전송하고, Backend는 완료된 Object를 스트리밍으로
분석합니다.

## 환경변수

```env
OCR_MAX_FILE_SIZE_MB=8192
OCR_INLINE_FILE_SIZE_MB=20
OCR_LARGE_ARCHIVE_UNCOMPRESSED_SIZE_MB=16384
```

R2 접속에는 기존 `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`을 사용합니다.
`RAG_R2_BUCKET_NAME`에는 공개 `r2.dev` URL이 연결되지 않은 RAG 전용 비공개 버킷을
설정합니다. 값을 비우면 기존 `R2_BUCKET_NAME`을 사용합니다. API Key는 두 버킷의
Object Read & Write 권한이 필요합니다.

## R2 CORS

Cloudflare R2 버킷의 CORS 정책에 실제 Frontend Origin을 등록합니다. `ETag`가 노출되지
않으면 브라우저가 완료 요청에 필요한 Part ETag를 읽을 수 없습니다.

```json
[
  {
    "AllowedOrigins": [
      "https://frontend.example.com",
      "http://localhost:5173"
    ],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

## 운영 설정

- Cloud Run은 응답 이후에도 분석 Task가 실행되도록 인스턴스 기반 CPU(`--no-cpu-throttling`)
  설정을 사용합니다.
- 현재 OCR Job 상태는 프로세스 메모리에 있으므로 다중 인스턴스 운영 시 session affinity를
  사용하거나, 장기적으로 Job 상태를 DB/Queue로 옮겨야 합니다.
- `admin-rag-artifacts/`는 VectorDB 저장 완료 후 삭제됩니다. 중단된 업로드와 실패한 Job을
  정리하도록 `admin-rag-uploads/`, `admin-rag-artifacts/` Prefix에 R2 Lifecycle 규칙을
  설정합니다.
- 20MB 초과 PDF·이미지·DOCX·PPTX는 현재 대용량 스트리밍 분석 대상이 아닙니다.
  해당 형식은 20MB 이하로 업로드하거나, 텍스트 데이터 또는 ZIP으로 변환합니다.
