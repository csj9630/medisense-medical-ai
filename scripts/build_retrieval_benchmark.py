"""실제 Neon에 저장된 청크를 대상으로 하는 Retrieval Benchmark용 질의 세트를 만든다.

**방법**: question 필드가 있는 QA류 데이터셋(snuh-clinical-qa, genmed-gpt,
health-search-qa)의 원본 (질문, original_id)을 다시 읽어서, 그 행이 실제로
Neon에 저장됐는지(hf-dataset://{source}/{original_id} 합성 URL로 idempotency
키와 동일하게 조회) 확인하고, 저장됐다면 그 문서의 첫 번째 청크를 "정답 chunk"로
기록한다.

**이건 self-referential 평가다** - 질문이 그 청크 자신의 원본 데이터에서 나온다
(완전히 독립적인 제3자가 만든 질문이 아님). 그래서 절대적인 Recall/MRR 수치는
낙관적으로 나올 수 있다 - 하지만 지금 목적은 "숫자가 몇 점이냐"가 아니라
"Jina 단독 vs BGE 단독 vs RRF 결합 중 뭐가 더 나은가"를 실제 Neon 코퍼스로
상대 비교하는 것이라, 이 정도로도 유효하다. 사람이 만든 등급(0/1/2) relevance
평가셋은 별도 작업이다(TODO).

**학습 데이터 재사용 금지 원칙과는 다른 얘기다** - 여기선 평가만 하고, 이 질의
세트로 임베딩/reranker를 다시 학습하지 않는다(루트 CLAUDE.md 원칙 그대로 지킴).

asan(건강정보 아티클, Q&A 형식 아님)과 komed-instruct(Alpaca instruction 형식,
"질문"이 아님)는 question 필드가 없어서 이 방식으로는 평가셋을 못 만든다 -
제외한다.
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai.rag.ingestion.adapters.registry import get_adapter  # noqa: E402

QA_SOURCES = ("snuh-clinical-qa", "genmed-gpt", "health-search-qa")
DEFAULT_SAMPLE_PER_SOURCE = 300


def _synthetic_url(source: str, original_id: str) -> str:
    # backend/app/services/rag_bulk_ingestion_service.py의 _synthetic_url()과
    # 반드시 동일해야 한다 - idempotency 키를 그대로 재사용해서 실제 저장 여부를 확인한다.
    return f"hf-dataset://{source}/{original_id}"


def collect_candidates(cli_source: str, sample: int) -> list[dict]:
    # shuffle_seed를 절대 안 쓴다 - genmed-gpt처럼 원본에 별도 id가 없는 데이터셋은
    # original_id를 "이 스트림에서 몇 번째로 나왔는지"(index)로 만든다
    # (ai/rag/ingestion/adapters/genmed_gpt.py: original_id=str(index)). 실제
    # ingestion(rag_ingest.py)은 genmed-gpt를 셔플 없이 순서대로 돌렸으므로, 여기서
    # 셔플을 넣으면 "이번 샘플링에서의 n번째"를 "원본 n번째"로 착각해서 완전히
    # 다른 질문-청크 쌍이 매칭된다 - 실제로 이 버그로 GenMedGPT-5k-ko 300개 질의가
    # 전부 엉뚱한 정답 chunk_id를 갖게 되어 Recall@k가 전부 0으로 나온 적이 있다
    # (2026-09-02). 순서대로 앞에서부터 뽑으면 이미 완전히 ingestion된 genmed-gpt는
    # 항상 안전하고, 부분만 ingestion된 snuh/health-search-qa도 실제로 이미 저장된
    # 앞부분과 자연스럽게 겹쳐서 오히려 매칭 성공률이 올라간다(이 두 데이터셋은
    # question_id/id 같은 원본 필드를 쓰므로 원래 셔플에 안전하지만, 통일성과 이
    # 문서의 교훈을 위해 전부 셔플을 뺐다).
    adapter = get_adapter(cli_source)
    candidates = []
    for index, raw_row in enumerate(adapter.load_raw(sample)):
        normalized = adapter.to_normalized(raw_row, index)
        if normalized is None or not normalized.question or not normalized.question.strip():
            continue
        candidates.append(
            {
                # 합성 URL은 CLI --source 슬러그가 아니라 어댑터 내부 표시용
                # source(예: "GenMedGPT-5k-ko")를 쓴다 -
                # rag_bulk_ingestion_service.py의 _synthetic_url()과 반드시 일치해야
                # 실제 저장 여부를 확인할 수 있다(둘이 달라서 처음에 0건 매칭되는
                # 버그가 실제로 있었음).
                "source": normalized.source,
                "original_id": normalized.original_id,
                "question": normalized.question.strip(),
            }
        )
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval Benchmark 질의 세트 생성")
    parser.add_argument("--sample-per-source", type=int, default=DEFAULT_SAMPLE_PER_SOURCE)
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "scripts" / "eval_data" / "retrieval_benchmark_queries.jsonl"),
    )
    args = parser.parse_args(argv)

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.generated import AdminDocuments, DocumentChunks

    all_candidates: list[dict] = []
    for source in QA_SOURCES:
        print(f"[{source}] 원본 후보 수집 중... (sample={args.sample_per_source})")
        candidates = collect_candidates(source, args.sample_per_source)
        print(f"[{source}] question 있는 후보: {len(candidates)}건")
        all_candidates.extend(candidates)

    urls = [_synthetic_url(c["source"], c["original_id"]) for c in all_candidates]

    db = SessionLocal()
    try:
        # IN 쿼리 한 번으로 묶는다 - 후보 수백~수천 개를 행마다 조회하면 그 자체가
        # 병목이 된다(rag_bulk_ingestion_service.py의 find_existing_urls와 동일 원칙).
        url_to_doc_id: dict[str, object] = {}
        _BATCH = 1000
        for start in range(0, len(urls), _BATCH):
            batch = urls[start : start + _BATCH]
            rows = db.execute(
                select(AdminDocuments.original_file_url, AdminDocuments.id).where(
                    AdminDocuments.original_file_url.in_(batch)
                )
            ).all()
            url_to_doc_id.update({url: doc_id for url, doc_id in rows})

        doc_ids = list(url_to_doc_id.values())
        doc_id_to_first_chunk: dict[object, tuple[str, int]] = {}
        for start in range(0, len(doc_ids), _BATCH):
            batch = doc_ids[start : start + _BATCH]
            rows = db.execute(
                select(DocumentChunks.document_id, DocumentChunks.id, DocumentChunks.chunk_index).where(
                    DocumentChunks.document_id.in_(batch)
                )
            ).all()
            for document_id, chunk_id, chunk_index in rows:
                existing = doc_id_to_first_chunk.get(document_id)
                if existing is None or chunk_index < existing[1]:
                    doc_id_to_first_chunk[document_id] = (str(chunk_id), chunk_index)
    finally:
        db.close()

    written = 0
    by_source: dict[str, int] = {}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for cand, url in zip(all_candidates, urls, strict=True):
            doc_id = url_to_doc_id.get(url)
            if doc_id is None:
                continue
            chunk = doc_id_to_first_chunk.get(doc_id)
            if chunk is None:
                continue
            chunk_id, _ = chunk
            f.write(
                json.dumps(
                    {"query": cand["question"], "relevant_chunk_id": chunk_id, "source": cand["source"]},
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
            by_source[cand["source"]] = by_source.get(cand["source"], 0) + 1

    print(f"완료: {written}건을 {args.out}에 저장")
    for source, count in sorted(by_source.items()):
        print(f"  - {source}: {count}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
