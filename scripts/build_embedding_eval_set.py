"""ClinicalQA로 임베딩 검색 평가셋을 만든다.

각 문제의 해설(explanation)을 "정답 청크"로, 질문(question)을 "쿼리"로 쓴다 —
실제 RAG에서 사용자가 증상을 물으면 관련 설명 청크를 찾아야 하는 상황과 비슷한
구조라, 쿼리·청크 표현이 겹치지 않으면서도 주제는 이어지는 현실적인 평가셋이 된다.
1,045개 전체가 코퍼스에 들어가서, 쿼리 하나당 나머지 1,044개가 자연스러운
방해 후보(distractor)가 된다.

산출물:
  scripts/eval_data/embedding_corpus.jsonl   — {id, text} 전체 청크
  scripts/eval_data/embedding_queries.jsonl  — {query, relevant_id} 정답 매핑
"""
import json
from pathlib import Path

from datasets import load_dataset

OUT_DIR = Path(__file__).parent / "eval_data"


def build():
    dataset = load_dataset("snuh/ClinicalQA", split="train")

    corpus_path = OUT_DIR / "embedding_corpus.jsonl"
    queries_path = OUT_DIR / "embedding_queries.jsonl"
    OUT_DIR.mkdir(exist_ok=True)

    with corpus_path.open("w", encoding="utf-8") as corpus_f, \
         queries_path.open("w", encoding="utf-8") as queries_f:
        for row in dataset:
            doc_id = f"clinicalqa-{row['question_id']}"
            explanation = (row.get("explanation") or "").strip()
            question = (row.get("question") or "").strip()
            chief_complaint = (row.get("chief_complaint") or "").strip()

            if not explanation or not question:
                continue  # 해설/질문이 비어있는 행은 평가셋에서 제외

            corpus_f.write(json.dumps({"id": doc_id, "text": explanation}, ensure_ascii=False) + "\n")

            query = f"{chief_complaint} {question}".strip() if chief_complaint else question
            queries_f.write(json.dumps({"query": query, "relevant_id": doc_id}, ensure_ascii=False) + "\n")

    print(f"corpus: {corpus_path}")
    print(f"queries: {queries_path}")


if __name__ == "__main__":
    build()
