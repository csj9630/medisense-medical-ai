"""narrow chunk_embeddings.embedding to vector(1024)

03b8a4b5b62a가 VECTOR(2048)로 넓게 잡은 이유는 "나중에 더 큰 임베딩 모델이 오면
또 마이그레이션 안 해도 되게" 하기 위함이었다. 그런데 실제로 확정된 Jina v4/Medical
BGE-M3는 둘 다 1024차원이고(.env EMBEDDING_DIMENSION=1024), 저장하는 쪽
(ai/rag/embeddings/remote.py, backend/app/repositories/document_chunk.py의
pad_embedding())이 뒤쪽 1024자리를 전부 0으로 채워서 넣고 있었다.

실제 DB에서 확인한 결과(2026-09-02): chunk_embeddings가 전체 DB(489MB)의 91.6%인
448MB를 차지하고, 그중 순수 0-padding만 약 207MB(전체 DB의 42%)였다. Neon 무료
티어(512MB)에 걸려 ingestion이 막힌 상황이라 이 낭비를 없애기로 했다.

**손실 없음을 실제로 검증**: 저장된 벡터 200개(jina-v4/medical-bgem3 각각)의 뒤
1024차원이 전부 0인 것을 확인했고, 실제 쿼리로 2048-패딩 방식과 1024-폭 방식의
코사인 거리를 둘 다 계산해서 최대 차이 0.0(완전히 동일), Top-20 랭킹도 완전히
동일함을 확인했다 - 0-padding은 내적/노름 계산에 기여가 없어서 수학적으로 항상
같은 결과가 나온다.

pgvector의 vector 타입은 직접 슬라이싱을 지원하지 않아서 real[]로 캐스팅 →
배열 슬라이싱 → vector로 재캐스팅하는 방식을 쓴다(둘 다 실제 DB에서 미리 확인한
문법).

Revision ID: a1f3c9d2e8b4
Revises: ebf81fbe5350
Create Date: 2026-09-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1f3c9d2e8b4'
down_revision: Union[str, Sequence[str], None] = 'ebf81fbe5350'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_WIDTH = 1024
OLD_WIDTH = 2048


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE vector_db.chunk_embeddings
        ALTER COLUMN embedding TYPE vector({NEW_WIDTH})
        USING (embedding::real[])[1:{NEW_WIDTH}]::vector({NEW_WIDTH})
    """)


def downgrade() -> None:
    op.execute(f"""
        ALTER TABLE vector_db.chunk_embeddings
        ALTER COLUMN embedding TYPE vector({OLD_WIDTH})
        USING (embedding::real[] || array_fill(0.0::real, ARRAY[{OLD_WIDTH - NEW_WIDTH}]))::vector({OLD_WIDTH})
    """)
