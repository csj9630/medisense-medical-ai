import json
import unittest

import httpx

from ai.rag import RemoteEmbeddingError, RemoteEmbeddingProvider


class RemoteEmbeddingProviderTest(unittest.TestCase):
    def test_query_and_passage_contract_batching_and_normalization(self) -> None:
        received: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            received.append(
                {
                    "payload": payload,
                    "authorization": request.headers.get("Authorization"),
                }
            )
            vector = [3.0, 4.0] + [0.0] * 1022
            return httpx.Response(
                200,
                json={
                    "model": payload["model"],
                    "dimensions": 1024,
                    "embeddings": [vector for _ in payload["texts"]],
                },
            )

        provider = _provider(httpx.MockTransport(handler), batch_size=2)
        passages = provider.embed_texts(["하나", "둘", "셋"])
        query = provider.embed_query("질문")

        self.assertEqual(len(passages), 3)
        self.assertAlmostEqual(passages[0][0], 0.6)
        self.assertAlmostEqual(passages[0][1], 0.8)
        self.assertAlmostEqual(query[0], 0.6)
        self.assertEqual(
            [item["payload"]["input_type"] for item in received],
            ["passage", "passage", "query"],
        )
        self.assertTrue(
            all(item["authorization"] == "Bearer secret-key" for item in received)
        )
        self.assertTrue(all(item["payload"]["model"] == "jina-v4" for item in received))

    def test_wrong_dimension_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "jina-v4",
                    "dimensions": 128,
                    "embeddings": [[0.1] * 128],
                },
            )

        with self.assertRaises(RemoteEmbeddingError):
            _provider(httpx.MockTransport(handler)).embed_query("질문")

    def test_missing_configuration_is_rejected_before_request(self) -> None:
        provider = RemoteEmbeddingProvider(
            base_url="",
            api_key=None,
            model="jina-v4",
        )

        with self.assertRaises(RemoteEmbeddingError) as raised:
            provider.embed_query("질문")

        self.assertIn("EMBEDDING_REMOTE_BASE_URL", str(raised.exception))

    def test_upstream_body_is_not_exposed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="secret upstream body")

        with self.assertRaises(RemoteEmbeddingError) as raised:
            _provider(httpx.MockTransport(handler), retry_backoff_seconds=0).embed_query("질문")

        self.assertNotIn("secret upstream", str(raised.exception))

    def test_transient_502_is_retried_and_recovers(self) -> None:
        # 실제 관찰된 사례 - Cloudflare 터널이 잠깐 끊기면서 502가 한 번 나고,
        # 재연결되면 정상 응답이 온다. 대량 처리 도중 이런 일시적 문제로 전체를
        # 처음부터 다시 하지 않아도 되게 재시도한다.
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] < 3:
                return httpx.Response(502, text="bad gateway")
            vector = [1.0] + [0.0] * 1023
            return httpx.Response(
                200, json={"model": "jina-v4", "dimensions": 1024, "embeddings": [vector]}
            )

        provider = _provider(httpx.MockTransport(handler), retry_backoff_seconds=0)
        result = provider.embed_query("질문")

        self.assertEqual(calls["count"], 3)
        self.assertAlmostEqual(result[0], 1.0)

    def test_transient_530_origin_unreachable_is_retried(self) -> None:
        # 실제 관찰된 사례 - Vast.ai GPU 인스턴스가 잠깐 응답 안 하면 Cloudflare가
        # 530(origin unreachable)을 준다. 이것도 몇 초 뒤엔 복구되는 걸 확인했다.
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] < 2:
                return httpx.Response(530, text="origin unreachable")
            vector = [1.0] + [0.0] * 1023
            return httpx.Response(
                200, json={"model": "jina-v4", "dimensions": 1024, "embeddings": [vector]}
            )

        provider = _provider(httpx.MockTransport(handler), retry_backoff_seconds=0)
        result = provider.embed_query("질문")

        self.assertEqual(calls["count"], 2)
        self.assertAlmostEqual(result[0], 1.0)

    def test_gives_up_after_max_retries(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(503, text="service unavailable")

        provider = _provider(httpx.MockTransport(handler), retry_backoff_seconds=0)
        provider.max_retries = 2

        with self.assertRaises(RemoteEmbeddingError):
            provider.embed_query("질문")
        self.assertEqual(calls["count"], 3)  # 최초 시도 + 재시도 2번

    def test_permanent_4xx_is_not_retried(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(401, text="unauthorized")

        provider = _provider(httpx.MockTransport(handler), retry_backoff_seconds=0)
        with self.assertRaises(RemoteEmbeddingError):
            provider.embed_query("질문")
        self.assertEqual(calls["count"], 1)


def _provider(
    transport: httpx.BaseTransport,
    *,
    batch_size: int = 32,
    retry_backoff_seconds: float = 0.5,
) -> RemoteEmbeddingProvider:
    return RemoteEmbeddingProvider(
        base_url="https://embedding.test",
        api_key="secret-key",
        model="jina-v4",
        dimension=1024,
        timeout_seconds=5,
        batch_size=batch_size,
        transport=transport,
        retry_backoff_seconds=retry_backoff_seconds,
    )


if __name__ == "__main__":
    unittest.main()
