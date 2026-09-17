"""Bearer 인증을 사용하는 원격 Dense Embedding Provider입니다.

Vast.ai GPU 서버가 Jina v4와 Medical BGE-M3를 상주시키고, Backend은
이 Provider를 통해 query/passage Vector만 HTTP로 받습니다.
"""

import math
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx


class RemoteEmbeddingError(RuntimeError):
    """원격 Embedding 설정·호출·응답 검증이 실패했을 때 발생합니다."""


SyncClientFactory = Callable[..., httpx.Client]

# 일시적인 서버/네트워크 문제로 보는 상태코드만 재시도한다 - 4xx(인증 실패, 잘못된
# 요청 등)는 재시도해도 똑같이 실패하므로 재시도 대상이 아니다. Cloudflare 터널을
# 통한 원격 GPU 서버 호출에서 502(터널 재연결 중), 530("origin unreachable" - GPU
# 인스턴스가 잠깐 응답 안 함)이 실제로 관찰됐다 - 둘 다 몇 초~몇십 초 뒤 원격 서버가
# 다시 응답하는 걸 확인했다(재시작이 필요한 영구 장애가 아님). 520-530은 전부
# Cloudflare가 origin 서버와 통신 실패했을 때 쓰는 코드 범위라 통째로 재시도 대상에
# 넣는다.
_RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504, *range(520, 531)})


class RemoteEmbeddingProvider:
    """`EmbeddingProvider` 계약을 만족하는 동기 HTTP Client입니다."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        dimension: int = 1024,
        timeout_seconds: float = 60.0,
        batch_size: int = 32,
        name: str | None = None,
        transport: httpx.BaseTransport | None = None,
        client_factory: SyncClientFactory = httpx.Client,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip() if api_key else None
        self.model = model.strip()
        self.name = (name or self.model).strip()
        self.dimension = dimension
        self.timeout_seconds = max(1.0, timeout_seconds)
        self.batch_size = max(1, min(batch_size, 64))
        self._transport = transport
        self._client_factory = client_factory
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="passage")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], input_type="query")[0]

    def _embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["query", "passage"],
    ) -> list[list[float]]:
        self._validate_configuration()
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise RemoteEmbeddingError("빈 Text는 Embedding할 수 없습니다.")

        client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(self.timeout_seconds),
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        vectors: list[list[float]] = []
        try:
            with self._client_factory(**client_kwargs) as client:
                for start in range(0, len(texts), self.batch_size):
                    batch = texts[start : start + self.batch_size]
                    response = self._post_with_retry(client, input_type, batch)
                    vectors.extend(
                        self._extract_vectors(
                            response.json(),
                            expected_count=len(batch),
                        )
                    )
        except httpx.TimeoutException as exc:
            raise RemoteEmbeddingError("Embedding 생성 제한시간을 초과했습니다.") from exc
        except httpx.HTTPStatusError as exc:
            raise RemoteEmbeddingError("원격 Embedding 서버가 요청을 거부했습니다.") from exc
        except httpx.RequestError as exc:
            raise RemoteEmbeddingError("원격 Embedding 서버에 연결하지 못했습니다.") from exc
        except RemoteEmbeddingError:
            raise
        except Exception as exc:
            raise RemoteEmbeddingError("원격 Embedding 응답을 처리하지 못했습니다.") from exc

        if len(vectors) != len(texts):
            raise RemoteEmbeddingError("요청 Text와 Embedding Vector 개수가 다릅니다.")
        return vectors

    def _post_with_retry(
        self,
        client: httpx.Client,
        input_type: str,
        batch: list[str],
    ) -> httpx.Response:
        """502/503/504처럼 일시적인 서버 문제로 보이는 응답이나 연결 자체가 실패한
        경우에만 지수 백오프로 재시도한다. Cloudflare 터널 재연결처럼 몇 초 안에
        회복되는 경우가 실제로 있어서, 대량 처리(RAG ingestion) 도중 한 번 끊겼다고
        전체를 처음부터 다시 하지 않아도 되게 하기 위함이다. 인증 실패(401/403) 등
        재시도해도 똑같이 실패할 4xx는 즉시 그대로 올린다."""
        attempt = 0
        while True:
            try:
                response = client.post(
                    f"{self.base_url}/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input_type": input_type, "texts": batch},
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                is_retryable = exc.response.status_code in _RETRYABLE_STATUS_CODES
                if not is_retryable or attempt >= self.max_retries:
                    raise
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                attempt += 1
            except httpx.RequestError:
                # 연결 실패/타임아웃(httpx.TimeoutException은 RequestError의 하위클래스) -
                # 상태코드가 없으니 전부 일시적 문제로 보고 재시도한다.
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                attempt += 1

    def _extract_vectors(
        self,
        payload: Any,
        *,
        expected_count: int,
    ) -> list[list[float]]:
        if not isinstance(payload, dict):
            raise RemoteEmbeddingError("Embedding 서버가 JSON 객체를 반환하지 않았습니다.")
        if payload.get("model") != self.model:
            raise RemoteEmbeddingError("요청한 모델과 응답 모델이 일치하지 않습니다.")
        if payload.get("dimensions") != self.dimension:
            raise RemoteEmbeddingError(
                f"{self.model} Vector는 {self.dimension}차원이어야 합니다."
            )

        response_vectors = payload.get("embeddings")
        if not isinstance(response_vectors, list) or len(response_vectors) != expected_count:
            raise RemoteEmbeddingError("요청한 Text와 응답 Vector 개수가 다릅니다.")

        vectors: list[list[float]] = []
        for index, values in enumerate(response_vectors):
            if not isinstance(values, list):
                raise RemoteEmbeddingError(f"Vector {index}가 배열이 아닙니다.")
            try:
                vector = [float(value) for value in values]
            except (TypeError, ValueError) as exc:
                raise RemoteEmbeddingError(f"Vector {index}에 숫자가 아닌 값이 있습니다.") from exc
            if len(vector) != self.dimension:
                raise RemoteEmbeddingError(
                    f"Vector {index}의 차원은 {len(vector)}이며 "
                    f"필요한 차원은 {self.dimension}입니다."
                )
            if any(not math.isfinite(value) for value in vector):
                raise RemoteEmbeddingError(f"Vector {index}에 유효하지 않은 숫자가 있습니다.")
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                raise RemoteEmbeddingError(f"Vector {index}가 0 Vector입니다.")
            vectors.append([value / norm for value in vector])
        return vectors

    def _validate_configuration(self) -> None:
        if not self.base_url or not self.api_key:
            raise RemoteEmbeddingError(
                "EMBEDDING_REMOTE_BASE_URL과 EMBEDDING_API_KEY를 설정해야 합니다."
            )
        if not self.model or not self.name:
            raise RemoteEmbeddingError("원격 Embedding 모델 ID가 비어 있습니다.")
        if self.dimension != 1024:
            raise RemoteEmbeddingError("Jina/BGE 원격 Vector는 1024차원이어야 합니다.")
