"""인스턴스가 바뀌어도 조회할 수 있는, TTL이 있는 OCR 작업 저장소.

업무 테이블과 독립된 임시 작업 테이블 하나만 관리한다. 배포 시 전체
Alembic 이력을 실행하지 않고 이 테이블만 준비하며 기존 데이터는 변경하지 않는다.
"""

from threading import Lock
from time import time

from sqlalchemy import Column, Float, JSON, MetaData, String, Table, delete, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from app.schemas.admin import OcrJobStatusResponse


class SqlOcrJobStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.table = Table(
            "ocr_jobs",
            MetaData(schema="app_db" if engine.dialect.name == "postgresql" else None),
            Column("job_id", String(32), primary_key=True),
            Column("expires_at", Float, nullable=False, index=True),
            Column("payload", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        )
        self._ready = False
        self._init_lock = Lock()

    def prepare(self) -> None:
        if self._ready:
            return
        with self._init_lock:
            if self._ready:
                return
            with self.engine.begin() as connection:
                if self.engine.dialect.name == "postgresql":
                    # 동시에 시작한 Cloud Run 인스턴스끼리도 테이블 생성을 직렬화한다.
                    connection.execute(text("SELECT pg_advisory_xact_lock(729401830125)"))
                self.table.create(connection, checkfirst=True)
            self._ready = True

    def put(self, status: OcrJobStatusResponse, expires_at: float) -> None:
        self.prepare()
        insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        payload = status.model_dump(mode="json", by_alias=True)
        if status.result is not None:
            # API에서는 숨기는 R2 참조도 저장해야 다른 인스턴스에서
            # 대용량 문서의 전체 Chunk를 VectorDB에 저장할 수 있다.
            payload["result"]["chunk_artifact_key"] = status.result.chunk_artifact_key
            payload["result"]["original_object_key"] = status.result.original_object_key
        statement = insert(self.table).values(
            job_id=status.job_id,
            expires_at=expires_at,
            payload=payload,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self.table.c.job_id],
            set_={"expires_at": statement.excluded.expires_at, "payload": statement.excluded.payload},
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def get(self, job_id: str) -> OcrJobStatusResponse | None:
        self.prepare()
        with self.engine.connect() as connection:
            payload = connection.execute(
                select(self.table.c.payload).where(
                    self.table.c.job_id == job_id,
                    self.table.c.expires_at > time(),
                )
            ).scalar_one_or_none()
        return None if payload is None else OcrJobStatusResponse.model_validate(payload)

    def remove_expired(self) -> None:
        self.prepare()
        with self.engine.begin() as connection:
            connection.execute(delete(self.table).where(self.table.c.expires_at <= time()))


def create_shared_job_store() -> SqlOcrJobStore:
    from app.core.database import engine

    return SqlOcrJobStore(engine)


if __name__ == "__main__":
    create_shared_job_store().prepare()
