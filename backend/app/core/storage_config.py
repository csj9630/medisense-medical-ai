from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ENV_FILE


class StorageSettings(BaseSettings):
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_url: str | None = None
    rag_r2_bucket_name: str | None = None

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def validate_r2(self) -> None:
        self.validate_r2_credentials()
        if not self.r2_public_url:
            raise RuntimeError("R2_PUBLIC_URL 환경변수가 설정되지 않았습니다.")

    def validate_r2_credentials(self) -> None:
        values = (
            self.r2_account_id,
            self.r2_access_key_id,
            self.r2_secret_access_key,
            self.r2_bucket_name,
        )
        if not all(values):
            raise RuntimeError("R2 환경변수가 설정되지 않았습니다.")


@lru_cache
def get_storage_settings() -> StorageSettings:
    return StorageSettings()


storage_settings = get_storage_settings()
