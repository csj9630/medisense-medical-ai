"""add consultation_logs table

관리자 대시보드(모델별 사용/성공률, 폴백 응답 비율, RAG 검색 0건 비율, 사용자별
사용량, 응급 안내 추이, 토큰 사용량 등)에 필요한 요청 단위 로그 테이블. 지금은
`ai.consultation.consult()`/`message.py`가 응답 시간·토큰 수·RAG 히트 수 등을
매 요청마다 계산만 하고 어디에도 저장하지 않아서, 이 테이블 하나 없이는 위 지표
전부를 만들 수 없다.

메시지(app_db.messages) 하나당 로그 한 행 — 사용자 메시지에 대한 assistant
응답이 생성될 때마다 기록한다. 아직 이 테이블에 실제로 값을 채워 넣는 서비스
코드(로깅 연동)는 별도 작업이다 — 이 마이그레이션은 스키마만 추가한다.

개인정보 관련 결정(TODO, 아직 미정): user_id로 사용자별 집계는 가능하게 해두되,
대시보드에는 익명 집계(분포/TOP N 등)로만 노출하고 이메일 등 식별 정보를 직접
얹지 않는 것을 권장한다.

Revision ID: 0dcef89659d1
Revises: 03b8a4b5b62a
Create Date: 2026-08-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0dcef89659d1'
down_revision: Union[str, Sequence[str], None] = '03b8a4b5b62a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consultation_logs',
        sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        # 어떤 모델을 어떤 provider가 실제로 처리했는지 — 모델별 사용/성공률 지표용.
        sa.Column('model_id', sa.String(100), nullable=True),
        sa.Column('provider_key', sa.String(50), nullable=True),
        # consult()가 예외를 잡고 FALLBACK_ANSWER를 반환했는지 — "겉보기엔 200인데
        # 실제로는 정형 문구만 나간" 상태를 오류율과 별도로 구분하기 위함.
        sa.Column('is_fallback', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        # risk_detector.detect_emergency()가 걸렸는지 — 발생 추이/오탐 감지용.
        sa.Column('is_emergency', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('department', sa.String(50), nullable=True),
        sa.Column('confidence', sa.String(10), nullable=True),
        # 참고 의료 정보로 실제 사용된 RAG 청크 수 — 0이면 "검색 결과 없이 LLM+
        # 프롬프트만으로 응답"한 요청. RAG 검색 0건 비율 지표용.
        sa.Column('rag_hit_count', sa.Integer(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        # 실패했다면 예외 클래스 이름만 기록(스택트레이스/내부 메시지는 로그 파일에만,
        # 여기엔 안 남김) — 오류 유형별 분포 지표용.
        sa.Column('error_type', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ['user_id'], ['app_db.users.id'],
            name='consultation_logs_user_id_fkey', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['app_db.conversations.id'],
            name='consultation_logs_conversation_id_fkey', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['app_db.messages.id'],
            name='consultation_logs_message_id_fkey', ondelete='CASCADE',
        ),
        schema='app_db',
    )
    op.create_index('idx_consultation_logs_user_id', 'consultation_logs', ['user_id'], schema='app_db')
    op.create_index('idx_consultation_logs_created_at', 'consultation_logs', ['created_at'], schema='app_db')
    op.create_index('idx_consultation_logs_model_id', 'consultation_logs', ['model_id'], schema='app_db')


def downgrade() -> None:
    op.drop_index('idx_consultation_logs_model_id', table_name='consultation_logs', schema='app_db')
    op.drop_index('idx_consultation_logs_created_at', table_name='consultation_logs', schema='app_db')
    op.drop_index('idx_consultation_logs_user_id', table_name='consultation_logs', schema='app_db')
    op.drop_table('consultation_logs', schema='app_db')
