"""add oauth_id to users for Google/GitHub social login

`users.auth_provider`는 이미 'local'/'guest' 값으로 쓰이고 있었다(password_hash가
nullable인 것도 guest 계정을 위한 설계) - 소셜 로그인도 같은 컬럼을 재사용하고
('google'/'github'), provider가 알려주는 고유 사용자 id(Google의 sub, GitHub의
숫자 id)만 새로 추가한다.

**email 하나만으로 사용자를 찾지 않는 이유**: 이메일은 위조/재사용 가능성이 있고
(예: 탈퇴한 이메일을 다른 사람이 재등록), (auth_provider, oauth_id) 조합이 실제로
그 provider가 보장하는 유일한 신원이다. 그래서 별도 유니크 제약을 둔다.

기존 local/guest 계정은 oauth_id가 NULL인 채로 남는다(Postgres UNIQUE 제약은 NULL을
여러 개 허용하므로 문제 없음).

Revision ID: e7c2a5f9b1d3
Revises: d4e6f1a9c3b7
Create Date: 2026-09-03 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7c2a5f9b1d3'
down_revision: Union[str, Sequence[str], None] = 'd4e6f1a9c3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('oauth_id', sa.String(255), nullable=True),
        schema='app_db',
    )
    op.create_unique_constraint(
        'users_auth_provider_oauth_id_key',
        'users',
        ['auth_provider', 'oauth_id'],
        schema='app_db',
    )


def downgrade() -> None:
    op.drop_constraint('users_auth_provider_oauth_id_key', 'users', schema='app_db', type_='unique')
    op.drop_column('users', 'oauth_id', schema='app_db')
