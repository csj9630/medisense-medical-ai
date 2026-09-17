"""팀원이 임베딩 모델을 정하면 실제로 갈아끼울 범용 provider.

BGE-M3, Jina, dragonkue, ko-sroberta 등 HuggingFace에 올라온 임베딩 모델은 거의 다
`sentence-transformers` 라이브러리로 로드할 수 있다 — 그래서 특정 모델 하나를
새로 코딩하는 대신, **모델 이름을 인자로 받는 범용 어댑터** 하나만 만들어둔다.
팀원이 최종 모델을 정하면 이 클래스에 모델 이름만 넘겨서 인스턴스 하나 만들면 끝난다
(코드 변경 없음, 설정값만 바뀜).
"""
from typing import Any

import numpy as np


class SentenceTransformerEmbeddingProvider:
    """`EmbeddingProvider` 계약을 만족하는 sentence-transformers 래퍼.

    Args:
        model_name: HuggingFace 모델 이름(예: "BAAI/bge-m3", "jinaai/jina-embeddings-v4").
        name: DB에 기록할 provider 구분 키. 안 주면 model_name을 그대로 쓴다.
        dimension: 실제 벡터 길이. 모르면 None으로 두면 모델 로드 후 자동으로 알아낸다.
        truncate_dim: Matryoshka 임베딩 지원 모델에서 차원을 줄이고 싶을 때(예: Jina v4를
            2048→1024로). 모델이 지원 안 하면 이 옵션을 넘기지 말 것.
        revision: 특정 commit에 고정하고 싶을 때 사용 — `trust_remote_code=True`와
            같이 쓸 모델은 반드시 지정할 것을 권장한다(ai/rag/CLAUDE.md의 보안 원칙 참고).
        trust_remote_code: HuggingFace 저장소의 임의 코드를 실행하는 옵션이라 기본값은
            False다. 이 옵션이 필요한 모델을 쓰려면 팀 검토 후 명시적으로 켤 것 —
            **임의로 True로 바꾸지 않는다.**
        query_prompt_name / document_prompt_name: 모델이 질의/문서를 다르게 인코딩하도록
            설계된 경우(e5, bge, jina 계열 등) 사용한다. 필요 없는 모델이면 None으로 둔다.
    """

    def __init__(
        self,
        model_name: str,
        *,
        name: str | None = None,
        dimension: int | None = None,
        truncate_dim: int | None = None,
        revision: str | None = None,
        trust_remote_code: bool = False,
        query_prompt_name: str | None = None,
        document_prompt_name: str | None = None,
    ) -> None:
        self.name = name or model_name
        self.dimension = truncate_dim or dimension or 0  # 모델 로드 전까지는 0, 로드 후 갱신됨
        self._model_name = model_name
        self._revision = revision
        self._trust_remote_code = trust_remote_code
        self._truncate_dim = truncate_dim
        self._query_prompt_name = query_prompt_name
        self._document_prompt_name = document_prompt_name
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                revision=self._revision,
                trust_remote_code=self._trust_remote_code,
            )
            if not self.dimension:
                self.dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def _encode(self, texts: list[str], prompt_name: str | None) -> list[list[float]]:
        model = self._get_model()
        kwargs: dict[str, Any] = {"normalize_embeddings": True}
        if self._truncate_dim:
            kwargs["truncate_dim"] = self._truncate_dim
        if prompt_name:
            kwargs["prompt_name"] = prompt_name
        vectors = model.encode(texts, **kwargs)
        return np.asarray(vectors).tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts, self._document_prompt_name)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], self._query_prompt_name)[0]
