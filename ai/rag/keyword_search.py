"""BM25 키워드 검색 — Kiwi로 한국어 형태소 분석 후 Tantivy(Rust 풀텍스트 검색엔진)로
색인한다. SPLADE 같은 신경망 기반 sparse 모델과 달리 GPU/추론 없이 가볍게 동작하고,
pgvector 밖의 별도 인덱스 인프라(Elasticsearch 등)도 필요 없다."""
import tempfile

import tantivy
from kiwipiepy import Kiwi

_kiwi = Kiwi()

# 명사/동사/형용사/외국어/숫자만 남긴다 — 조사·어미는 검색 의미가 없어서 뺀다.
_MEANINGFUL_TAGS = {"NNG", "NNP", "VV", "VA", "SL", "SN"}


def tokenize(text: str) -> str:
    tokens = _kiwi.tokenize(text)
    return " ".join(t.form for t in tokens if t.tag in _MEANINGFUL_TAGS)


def search(chunks: list[str], query: str, top_k: int = 5) -> list[tuple[int, float]]:
    """chunks 안에서 query와 BM25로 가까운 순서대로 (청크 인덱스, 점수)를 반환한다.

    호출할 때마다 임시 인덱스를 새로 만든다 — 문서 하나 단위로 청크 수가 많지 않은
    이 랩/컨설테이션 용도엔 충분히 빠르고, 상태를 계속 들고 있지 않아도 되어 단순하다.
    """
    if not chunks:
        return []

    schema_builder = tantivy.SchemaBuilder()
    schema_builder.add_integer_field("chunk_index", stored=True, indexed=True)
    schema_builder.add_text_field("text", stored=False)
    schema = schema_builder.build()

    # ignore_cleanup_errors: 윈도우에서 Tantivy가 인덱스 파일 핸들을 곧바로 안 놓아서
    # 임시 디렉토리 삭제 시 "디렉토리가 비어있지 않음" 에러로 죽는 경우가 있어 무시한다.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        index = tantivy.Index(schema, path=tmp_dir)
        writer = index.writer()
        for i, chunk in enumerate(chunks):
            writer.add_document(tantivy.Document(chunk_index=i, text=tokenize(chunk)))
        writer.commit()
        index.reload()

        searcher = index.searcher()
        parsed_query = index.parse_query(tokenize(query), ["text"])
        hits = searcher.search(parsed_query, top_k).hits

        return [(searcher.doc(addr)["chunk_index"][0], score) for score, addr in hits]
