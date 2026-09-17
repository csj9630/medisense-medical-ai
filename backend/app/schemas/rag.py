from pydantic import BaseModel


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    use_reranker: bool = False


class RagSearchResultItem(BaseModel):
    chunk_id: str | None
    document_id: str | None
    content: str
    score: float


class RagSearchResponse(BaseModel):
    query: str
    results: list[RagSearchResultItem]
