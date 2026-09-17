from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ENV_FILE


class Settings(BaseSettings):
    app_name: str = "MediSense API"
    app_env: str = "local"
    api_prefix: str = "/api"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    database_url: str = "sqlite:///./local.db"
    model_schemas: str = "app_db,vector_db"
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_reset_expire_minutes: int = 30
    frontend_url: str = "http://localhost:5173"
    # 비로그인 사용자도 채팅을 쓸 수 있게 하는 게스트 계정 관련 설정.
    # 게스트 토큰은 로그인 수단이 없으므로 길게 잡아 재방문 시 같은 게스트로 이어지게 한다.
    # 아래 두 한도는 하루 단위가 아니라 게스트 계정 하나가 평생 쓸 수 있는 총량이다
    # (다 쓰면 로그인 유도) — 새 게스트를 발급받으면(=localStorage 초기화) 다시 리셋됨.
    guest_token_expire_minutes: int = 60 * 24 * 30  # 30일
    guest_message_limit: int = 30
    guest_attachment_limit: int = 5
    # 시크릿창/다른 브라우저로 guest_message_limit을 우회(새 게스트 계정 계속
    # 발급)하는 것까지 완전히 막을 순 없지만(익명 사용자라 신원이 없음), 같은
    # IP에서 짧은 시간에 새 게스트 계정을 너무 많이 만드는 것 정도는 막는다.
    guest_signup_limit_per_ip: int = 5
    guest_signup_window_hours: int = 24
    # 메인·채팅 multipart 첨부 제한. 원본은 요청 동안 검증한 뒤 보관하지 않는다.
    message_max_files_per_request: int = 5
    message_max_file_size_mb: int = 20

    # 콜백 주소를 생략하면 FRONTEND_URL + provider별 경로를 사용한다.
    # 프론트 콜백 라우트가 서버로 전달하고, 코드 교환은 서버에서만 처리한다.
    # Google/GitHub 콘솔에도 같은 프론트 콜백 주소를 등록해야 한다.
    # 로컬 개발 등 별도 주소가 필요할 때만 provider별 값을 명시한다.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_oauth_redirect_uri: str = ""
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_redirect_uri: str = ""

    @property
    def effective_google_oauth_redirect_uri(self) -> str:
        return self.google_oauth_redirect_uri.strip() or f"{self.frontend_url.rstrip('/')}/auth/google/callback"

    @property
    def effective_github_oauth_redirect_uri(self) -> str:
        return self.github_oauth_redirect_uri.strip() or f"{self.frontend_url.rstrip('/')}/oauth/github/callback"

    # 관리자 RAG 원본은 8GiB까지 R2 멀티파트로 받되, 메모리에 올리는
    # 기존 multipart OCR 경로는 독립된 20MiB 한도를 유지한다.
    ocr_max_file_size_mb: int = 8 * 1024
    ocr_inline_file_size_mb: int = 20
    ocr_max_pdf_pages: int = 50
    ocr_native_text_min_chars: int = 20
    ocr_significant_image_area_ratio: float = 0.03
    ocr_pdf_render_dpi: int = 200
    ocr_max_image_side: int = 2400
    ocr_max_image_pixels: int = 40_000_000
    ocr_paddle_device: str = "cpu"
    ocr_paddle_language: str = "korean"
    ocr_min_confidence: float = 0.5
    ocr_enable_denoise: bool = True
    ocr_enable_deskew: bool = True
    ocr_max_office_uncompressed_size_mb: int = 200
    ocr_max_office_archive_entries: int = 5_000
    ocr_large_archive_uncompressed_size_mb: int = 16 * 1024
    ocr_job_ttl_minutes: int = 60
    ocr_max_pending_jobs: int = 5
    ocr_web_max_url_length: int = 500
    ocr_web_max_html_size_mb: int = 5
    ocr_web_max_text_chars: int = 100_000
    ocr_web_max_chunks: int = 200
    ocr_web_max_redirects: int = 3
    ocr_web_connect_timeout_seconds: float = 5
    ocr_web_read_timeout_seconds: float = 15
    ocr_web_max_images: int = 20
    ocr_web_max_image_size_mb: int = 5
    ocr_web_max_total_image_size_mb: int = 30
    ocr_web_image_concurrency: int = 4

    # 모든 LLM은 Vast.ai의 공통 원격 추론 서버에서 실행합니다.
    llm_remote_enabled: bool = False
    llm_remote_base_url: str = ""
    llm_remote_api_key: str | None = None
    llm_remote_gemma_model: str = "gemma"
    llm_remote_medgemma_final_model: str = "medgemma-final"
    llm_remote_medgemma_dataset_model: str = "medgemma-dataset"
    llm_remote_qwen_model: str = "qwen"
    llm_remote_llama_model: str = "llama"
    llm_remote_timeout_seconds: float = 300.0
    llm_remote_max_concurrency: int = 5

    # OCR 저장과 메인 RAG가 공통으로 사용하는 Vast.ai 이중 Embedding API.
    embedding_remote_base_url: str = ""
    embedding_api_key: str | None = None
    embedding_jina_model: str = "jina-v4"
    embedding_bge_model: str = "medical-bgem3"
    embedding_dimension: int = 1024
    embedding_timeout_seconds: float = 60.0
    embedding_batch_size: int = 32
    # RAG 검색 튜닝값 — rag_search_service.py에서 사용(ai/rag는 Backend 설정을
    # 모르므로 여기서만 읽는다). candidates: provider별로 우선 넉넉히 뽑아둘 후보 수
    # (top_k*4와 비교해 더 큰 쪽을 씀). rrf_k: RRF 결합 공식의 상수 — 값이 클수록
    # 순위 차이가 점수에 덜 반영된다(더 완만하게 합쳐짐).
    embedding_search_candidates: int = 20
    embedding_rrf_k: int = 60

    # remote_dual은 위 Jina/BGE 설정을 OCR과 RAG에 공통 적용합니다.
    # 필요한 개발 환경에서만 hashing 또는 sentence_transformer로 바꿀 수 있습니다.
    # rag_embedding_dimension/truncate_dim을 비우면 로컬 모델이 자동 판별합니다.
    rag_embedding_provider: str = "remote_dual"
    rag_embedding_model_name: str | None = None
    rag_embedding_dimension: int | None = None
    rag_embedding_truncate_dim: int | None = None
    rag_embedding_revision: str | None = None
    rag_embedding_trust_remote_code: bool = False
    rag_embedding_query_prompt_name: str | None = None
    rag_embedding_document_prompt_name: str | None = None

    @field_validator("rag_embedding_dimension", "rag_embedding_truncate_dim", mode="before")
    @classmethod
    def _blank_env_string_means_none(cls, value: object) -> object:
        # .env 관례상 안 쓰는 optional 값은 `KEY=`(빈 문자열)로 남겨둔다 — pydantic은
        # 빈 문자열을 int로 못 바꾸니 여기서 미리 None으로 취급한다.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
