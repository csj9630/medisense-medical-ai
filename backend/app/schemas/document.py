from pydantic import BaseModel


class OcrLineResponse(BaseModel):
    text: str
    confidence: float
    page: int = 0


class OcrResponse(BaseModel):
    text: str
    lines: list[OcrLineResponse]
