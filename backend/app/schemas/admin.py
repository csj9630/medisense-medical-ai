"""Admin OCR·LLM API가 Frontend와 공유하는 Request/Response 계약입니다."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminSchema(BaseModel):
    """Frontend의 camelCase와 Backend의 snake_case를 함께 허용합니다."""

    model_config = ConfigDict(populate_by_name=True)


ReferenceDocumentName = Annotated[str, Field(min_length=1, max_length=255)]
      
class OcrAnalyzeRequest(AdminSchema):
    document_name: str = Field(alias="documentName", min_length=1, max_length=255)
    file_size: int = Field(alias="fileSize", ge=0)
    content_type: str | None = Field(default=None, alias="contentType", max_length=100)
    chunk_size: int = Field(default=512, alias="chunkSize", ge=50, le=4096)
    overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_chunk_options(self) -> "OcrAnalyzeRequest":
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap은 Chunk Size보다 작아야 합니다.")
        return self


class OcrDocumentResponse(AdminSchema):
    document_name: str = Field(alias="documentName")
    page_count: int | None = Field(alias="pageCount")
    character_count: int = Field(alias="characterCount")
    estimated_chunks: int = Field(alias="estimatedChunks")
    confidence: float
    extracted_text: str = Field(alias="extractedText")
    chunks: list[str]
    readiness: Literal["review", "ready"]
    notes: list[str]
    source_type: Literal["file", "url"] = Field(default="file", alias="sourceType")
    source_url: str | None = Field(default=None, alias="sourceUrl", max_length=500)
    chunk_artifact_key: str | None = Field(default=None, exclude=True)
    original_object_key: str | None = Field(default=None, exclude=True)


class OcrUrlJobRequest(AdminSchema):
    url: str = Field(min_length=1, max_length=500)
    chunk_size: int = Field(default=512, alias="chunkSize", ge=100, le=4096)
    overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_chunk_options(self) -> "OcrUrlJobRequest":
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap은 Chunk Size보다 작아야 합니다.")
        return self
class OcrJobCreatedResponse(AdminSchema):
    job_id: str = Field(alias="jobId")
    status: Literal["queued"]


class OcrJobStatusResponse(AdminSchema):
    job_id: str = Field(alias="jobId")
    status: Literal["queued", "processing", "completed", "failed"]
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    result: OcrDocumentResponse | None = None
    error: str | None = None


class OcrMultipartUploadInitRequest(AdminSchema):
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    file_size: int = Field(alias="fileSize", ge=1, le=8 * 1024**3)
    content_type: str = Field(alias="contentType", min_length=1, max_length=150)


class OcrMultipartUploadInitResponse(AdminSchema):
    upload_id: str = Field(alias="uploadId")
    object_key: str = Field(alias="objectKey")
    part_size: int = Field(alias="partSize")
    part_count: int = Field(alias="partCount")


class OcrMultipartPartUrlRequest(AdminSchema):
    upload_id: str = Field(alias="uploadId", min_length=1, max_length=512)
    object_key: str = Field(alias="objectKey", min_length=1, max_length=1024)
    part_number: int = Field(alias="partNumber", ge=1, le=10_000)


class OcrMultipartPartUrlResponse(AdminSchema):
    upload_url: str = Field(alias="uploadUrl")


class OcrMultipartCompletedPart(AdminSchema):
    part_number: int = Field(alias="partNumber", ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=200)


class OcrMultipartUploadCompleteRequest(AdminSchema):
    upload_id: str = Field(alias="uploadId", min_length=1, max_length=512)
    object_key: str = Field(alias="objectKey", min_length=1, max_length=1024)
    file_size: int = Field(alias="fileSize", ge=1, le=8 * 1024**3)
    parts: list[OcrMultipartCompletedPart] = Field(min_length=1, max_length=10_000)


class OcrMultipartUploadCompleteResponse(AdminSchema):
    object_key: str = Field(alias="objectKey")
    etag: str
    file_size: int = Field(alias="fileSize")


class OcrMultipartUploadAbortRequest(AdminSchema):
    upload_id: str = Field(alias="uploadId", min_length=1, max_length=512)
    object_key: str = Field(alias="objectKey", min_length=1, max_length=1024)


class OcrRemoteJobRequest(AdminSchema):
    object_key: str = Field(alias="objectKey", min_length=1, max_length=1024)
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    file_size: int = Field(alias="fileSize", ge=1, le=8 * 1024**3)
    content_type: str = Field(alias="contentType", min_length=1, max_length=150)
    chunk_size: int = Field(default=512, alias="chunkSize", ge=50, le=4096)
    overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_chunk_options(self) -> "OcrRemoteJobRequest":
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap은 Chunk Size보다 작아야 합니다.")
        return self


class OcrVectorSaveRequest(AdminSchema):
    job_id: str = Field(alias="jobId", min_length=1, max_length=64)


class OcrVectorSaveResponse(AdminSchema):
    message: str
    document_id: UUID = Field(alias="documentId")
    chunk_count: int = Field(alias="chunkCount", ge=1)
    embedding_provider: str = Field(alias="embeddingProvider")
    embedding_dimension: int = Field(alias="embeddingDimension")
    embedding_model: str = Field(alias="embeddingModel")


class LlmRunRequest(AdminSchema):
    prompt: str = Field(min_length=1, max_length=10_000)
    model_id: str = Field(alias="modelId", min_length=1, max_length=100)
    document_name: str | None = Field(default=None, alias="documentName", max_length=255)
    document_names: list[ReferenceDocumentName] = Field(
        default_factory=list,
        alias="documentNames",
        max_length=5,
    )

    @model_validator(mode="after")
    def validate_prompt(self) -> "LlmRunRequest":
        if not self.prompt.strip():
            raise ValueError("Prompt를 입력해 주세요.")
        if len(set(self.document_names)) != len(self.document_names):
            raise ValueError("동일한 참고 문서를 중복해서 선택할 수 없습니다.")
        return self

    def joined_document_names(self) -> str | None:
        names = self.document_names or ([self.document_name] if self.document_name else [])
        return ", ".join(names) or None


class LlmRunResponse(AdminSchema):
    model_id: str = Field(alias="modelId")
    provider: str
    provider_model: str = Field(alias="providerModel")
    answer: str
    response_time_seconds: float = Field(alias="responseTimeSeconds")
    input_tokens: int | None = Field(alias="inputTokens")
    output_tokens: int | None = Field(alias="outputTokens")
    total_tokens: int | None = Field(alias="totalTokens")
    finish_reason: str | None = Field(default=None, alias="finishReason")
    is_mock: bool = Field(alias="isMock")


class LlmModelDefinitionResponse(AdminSchema):
    id: str
    label: str
    family: str
    training_stage: str = Field(alias="trainingStage")
    description: str
    group: Literal["main", "other"]
    provider: str
    provider_model: str = Field(alias="providerModel")
    enabled: bool
    available: bool
    availability_message: str | None = Field(alias="availabilityMessage")
    is_mock: bool = Field(alias="isMock")


class LlmCompareRequest(AdminSchema):
    prompt: str = Field(min_length=1, max_length=10_000)
    model_ids: list[str] = Field(alias="modelIds", min_length=2, max_length=5)
    document_name: str | None = Field(default=None, alias="documentName", max_length=255)
    document_names: list[ReferenceDocumentName] = Field(
        default_factory=list,
        alias="documentNames",
        max_length=5,
    )
    chunk_size: int = Field(default=512, alias="chunkSize", ge=50, le=4096)
    overlap: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def validate_compare_options(self) -> "LlmCompareRequest":
        if not self.prompt.strip():
            raise ValueError("Prompt를 입력해 주세요.")
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError("동일한 모델을 중복해서 선택할 수 없습니다.")
        if len(set(self.document_names)) != len(self.document_names):
            raise ValueError("동일한 참고 문서를 중복해서 선택할 수 없습니다.")
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap은 Chunk Size보다 작아야 합니다.")
        return self

    def joined_document_names(self) -> str | None:
        names = self.document_names or ([self.document_name] if self.document_name else [])
        return ", ".join(names) or None


class LlmModelResponse(AdminSchema):
    model_id: str = Field(alias="modelId")
    status: Literal["success", "error"]
    answer: str | None = None
    error: str | None = None
    response_time_seconds: float = Field(alias="responseTimeSeconds")
    input_tokens: int | None = Field(alias="inputTokens")
    output_tokens: int | None = Field(alias="outputTokens")
    chunk_size: int = Field(alias="chunkSize")
    overlap: int


class RetrievalEvalResponse(AdminSchema):
    """`scripts/eval_data/*.jsonl` 기준 dense 검색 정확도. 값은 매번 새로 계산한다
    (캐시 없음) — corpus/쿼리 임베딩 계산이 끝나야 응답이 온다."""

    num_queries: int = Field(alias="numQueries")
    # JSON 키는 문자열이어야 해서 k값(int)을 문자열로 바꿔 보낸다(예: {"1": 0.42, "5": 0.71}).
    recall_at_k: dict[str, float] = Field(alias="recallAtK")
    mrr: float
    dataset_name: str = Field(alias="datasetName")
