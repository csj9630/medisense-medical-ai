"""add finish_reason to consultation_logs

`ai/llm/contracts.py`의 `ProviderGenerateResult.finish_reason`(provider가 응답을
왜 멈췄는지 - "stop"=정상 종료, "length"=max_output_tokens에 걸려 잘림 등)은
remote_http.py/ollama.py가 이미 정규화해서 채워주고 있었는데, `ai/consultation/
pipeline.py`의 `consult()`가 이 필드를 안 읽고 버려서 실제 답변이 잘렸는지
여부를 어디서도(로그/대시보드) 추적할 수 없는 gap이었다. `ConsultationResult`에
필드를 추가하고 여기까지 그대로 흘려보낸다 - 이제 "잘림 비율" 같은 지표를
`model_id`별로 집계할 수 있다.

Revision ID: d4e6f1a9c3b7
Revises: a1f3c9d2e8b4
Create Date: 2026-09-02 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e6f1a9c3b7'
down_revision: Union[str, Sequence[str], None] = 'a1f3c9d2e8b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'consultation_logs',
        sa.Column('finish_reason', sa.String(50), nullable=True),
        schema='app_db',
    )


def downgrade() -> None:
    op.drop_column('consultation_logs', 'finish_reason', schema='app_db')
