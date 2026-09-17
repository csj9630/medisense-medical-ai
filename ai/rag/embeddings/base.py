"""임베딩 모델 선택은 팀원 담당, RAG 로직(청킹/검색/결합/저장)은 이 인터페이스 뒤에서
어떤 모델이 오든 몰라도 되게 만든다. 팀원이 최종 모델을 정하면 이 Protocol만
만족하는 구현체 하나(또는 여러 개) 만들어서 꽂으면 된다 — `pipeline.py`,
`document_ingestion_service.py`, `rag_search_service.py`는 코드를 안 바꿔도 된다.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """구현체가 갖춰야 하는 최소 계약. 지연 로딩/캐싱 여부, 실제 모델이 뭔지는
    구현체 안에서만 알면 된다."""

    #: DB에 저장할 때 이 벡터가 "어느 provider가 만들었는지" 구분하는 키.
    #: provider를 여러 개 쓸 때(앙상블) chunk_embeddings 테이블의 provider_name이 된다.
    name: str

    #: 이 provider가 실제로 내놓는 벡터 길이. DB 컬럼은 여러 provider를 한 테이블에
    #: 담기 위해 더 넓게(예: 2048) 잡아두고 나머지는 0으로 패딩한다 — 이 값 자체는
    #: "진짜 의미 있는 차원이 몇인지"를 기록해서 나중에 확인할 수 있게 한다.
    dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """문서(청크) 임베딩. 구현체는 코사인 유사도를 내적으로 계산할 수 있도록
        정규화된(단위) 벡터를 반환해야 한다."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """질의 임베딩 — 모델에 따라 문서와 다른 prompt/prefix를 쓸 수 있으므로
        `embed_texts([text])[0]`과 항상 같다고 가정하지 않는다."""
        ...
