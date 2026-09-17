"""add guest_ip_throttle table for guest signup rate limiting

게스트 세션은 브라우저 localStorage에 토큰을 캐싱해서 재사용하지만(같은 브라우저
재방문 시 같은 게스트 유지), 시크릿창/다른 브라우저/기기를 쓰면 새 게스트 계정을
얼마든지 새로 받을 수 있어서 guest_message_limit(설정값)을 사실상 무제한으로
우회할 수 있다. 완전히 막을 수는 없지만(익명 사용자라 신원 자체가 없음), 같은
IP에서 짧은 시간에 게스트 계정을 너무 많이 새로 만드는 것 정도는 막는다.

**`users` 테이블에 ip 컬럼을 추가하지 않고 별도 테이블로 둔 이유**: 이건 신원
정보가 아니라 순전히 "이 IP가 최근에 몇 번 새 게스트를 만들었는지"만 세는
카운터다. `users.ip`로 두면 계정이 살아있는 한 IP가 영구히 남는데, 그럴 필요가
없다(개인정보 최소 수집 원칙) - 이 테이블은 시간 창(window)이 지나면 그냥 다시
1로 리셋되고 과거 기록을 안 쌓는다.

Revision ID: f3a8d6c1b2e4
Revises: e7c2a5f9b1d3
Create Date: 2026-09-03 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a8d6c1b2e4'
down_revision: Union[str, Sequence[str], None] = 'e7c2a5f9b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'guest_ip_throttle',
        # IPv6 최대 표기 길이(45자, 예: 브라켓 없는 압축형 기준 여유있게) 기준.
        sa.Column('ip', sa.String(45), primary_key=True),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        schema='app_db',
    )


def downgrade() -> None:
    op.drop_table('guest_ip_throttle', schema='app_db')
