from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
managed_schemas = set(settings.model_schemas.split(","))


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    # TTL이 있는 OCR 작업 캐시는 SqlOcrJobStore가 독립적으로 생성·관리한다.
    # ORM 업무 모델에 없다는 이유로 다음 자동 마이그레이션에서 삭제하지 않는다.
    if type_ == "table" and name == "ocr_jobs" and parent_names.get("schema_name") == "app_db":
        return False
    if type_ == "schema":
        return name in managed_schemas
    schema_name = parent_names.get("schema_name")
    return schema_name is None or schema_name in managed_schemas


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
