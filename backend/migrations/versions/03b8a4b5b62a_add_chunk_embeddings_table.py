"""add chunk_embeddings table

임베딩 모델이 아직 정해지지 않은 상태(팀원이 별도 진행 중)에서 RAG 검색을 미리
구현하기 위한 정규화된 임베딩 저장 테이블. 기존 `document_chunks.embedding`
컬럼(Gemini 파이프라인이 이미 사용 중)은 전혀 건드리지 않는다 — 완전히 새 테이블만
추가한다.

한 청크(chunk_id)에 대해 provider(모델)별로 행이 하나씩 생긴다. 이러면:
- 모델을 몇 개 쓰든(1개, 또는 Dense 앙상블 N개) 스키마 변경 없이 그냥 행만 늘어남.
- 모델이 바뀌면(팀원 최종 결정, 또는 나중에 교체) 새 provider_name으로 새 행을
  추가하기만 하면 됨 — 컬럼 추가/마이그레이션 불필요.

VECTOR(2048)로 넓게 잡고 실제 차원(`dimension` 컬럼)은 별도로 기록한다. 실제
벡터가 이보다 짧으면 저장하는 쪽(`ai.rag.embeddings`)이 0으로 패딩한다 — 코사인
유사도는 두 벡터를 같은 자리만큼 0으로 패딩해도 값이 안 바뀐다(내적/노름 모두
0 기여). 단, pgvector의 HNSW/ivfflat 인덱스는 2000차원까지만 지원하므로, 나중에
ANN 인덱스를 붙이려면 2000차원 이하로 자르거나(Matryoshka 등) 다른 인덱스 전략이
필요하다 — 지금은 인덱스 없이 순차 스캔으로 충분한 규모라 인덱스는 안 만든다.

Revision ID: 03b8a4b5b62a
Revises: 2e7a98381f96
Create Date: 2026-08-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy.vector import VECTOR


revision: str = '03b8a4b5b62a'
down_revision: Union[str, Sequence[str], None] = '2e7a98381f96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_COLUMN_WIDTH = 2048


def upgrade() -> None:
    op.create_table(
        'chunk_embeddings',
        sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('chunk_id', sa.Uuid(), nullable=False),
        sa.Column('provider_name', sa.String(100), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('embedding', VECTOR(EMBEDDING_COLUMN_WIDTH), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ['chunk_id'], ['vector_db.document_chunks.id'],
            name='chunk_embeddings_chunk_id_fkey', ondelete='CASCADE',
        ),
        # 같은 청크에 같은 provider로 두 번 임베딩해서 중복 저장하는 걸 막는다 —
        # 재수집(re-ingest) 시에는 먼저 지우고 새로 넣는 방식으로 처리한다.
        sa.UniqueConstraint('chunk_id', 'provider_name', name='chunk_embeddings_chunk_id_provider_name_key'),
        schema='vector_db',
    )
    op.create_index(
        'idx_chunk_embeddings_chunk_id', 'chunk_embeddings', ['chunk_id'], schema='vector_db',
    )
    op.create_index(
        'idx_chunk_embeddings_provider_name', 'chunk_embeddings', ['provider_name'], schema='vector_db',
    )


def downgrade() -> None:
    op.drop_index('idx_chunk_embeddings_provider_name', table_name='chunk_embeddings', schema='vector_db')
    op.drop_index('idx_chunk_embeddings_chunk_id', table_name='chunk_embeddings', schema='vector_db')
    op.drop_table('chunk_embeddings', schema='vector_db')
