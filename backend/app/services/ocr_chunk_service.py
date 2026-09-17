"""정제된 OCR Text를 관리자 검토용 문자 기준 Chunk로 나눕니다."""


def create_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """문장 경계를 우선하면서 지정한 문자 수와 Overlap으로 분할합니다."""

    if not text:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(text):
        maximum_end = min(start + chunk_size, len(text))
        end = find_natural_boundary(text, start, maximum_end, chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break

        # Overlap 뒤에도 시작점이 반드시 앞으로 이동하도록 보장합니다.
        start = max(end - overlap, start + 1)

    return chunks


def find_natural_boundary(
    text: str,
    start: int,
    maximum_end: int,
    chunk_size: int,
) -> int:
    """`large_document_service._StreamingChunker`도 그대로 재사용한다(2026-09-07) -
    8GB 스트리밍 청커는 문서 전체가 아니라 지금 버퍼만 갖고 있지만, 그 버퍼를
    하나의 완결된 text처럼(start=0) 넘기면 이 함수는 그대로 동작한다."""
    if maximum_end >= len(text):
        return len(text)

    minimum_end = start + int(chunk_size * 0.6)
    for separator in ("\n\n", "\n", ". ", " "):
        boundary = text.rfind(separator, minimum_end, maximum_end)
        if boundary != -1:
            return boundary + len(separator)
    return maximum_end
