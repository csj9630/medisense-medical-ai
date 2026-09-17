"""add metadata column to document_chunks

RAG 데이터셋 ingestion(HuggingFace 의료 데이터셋 6개)에서 청크별 출처/진료과/질환/
신뢰도/검토필요 여부 등을 추적하기 위한 nullable JSONB 컬럼. 기존 OCR-admin
저장 경로(document_repository.save_with_chunks)는 이 값을 안 넘기므로 계속
NULL로 남는다 — 하위호환, 기존 데이터는 전혀 건드리지 않는다.

Revision ID: ebf81fbe5350
Revises: 0dcef89659d1
Create Date: 2026-09-01 11:53:51.719951
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'ebf81fbe5350'
down_revision: Union[str, Sequence[str], None] = '0dcef89659d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'document_chunks',
        sa.Column('metadata', JSONB(astext_type=sa.Text()), nullable=True),
        schema='vector_db',
    )


def downgrade() -> None:
    op.drop_column('document_chunks', 'metadata', schema='vector_db')
