"""정답 데이터 입력과 답변 성능평가의 HTTP 계약입니다."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class GroundTruthCaseResponse(EvaluationSchema):
    id: str
    question: str
    expected_answer: str = Field(alias="expectedAnswer")


class GroundTruthParseResponse(EvaluationSchema):
    source_name: str = Field(alias="sourceName")
    cases: list[GroundTruthCaseResponse]


class AnswerEvaluationCaseRequest(EvaluationSchema):
    id: str = Field(min_length=1, max_length=100)
    question: str = Field(default="", max_length=2_000)
    expected_answer: str = Field(alias="expectedAnswer", min_length=1, max_length=20_000)
    predicted_answer: str = Field(alias="predictedAnswer", min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def validate_answers(self) -> "AnswerEvaluationCaseRequest":
        if not self.expected_answer.strip() or not self.predicted_answer.strip():
            raise ValueError("정답과 모델 답변을 모두 입력해 주세요.")
        return self


class AnswerEvaluationRequest(EvaluationSchema):
    cases: list[AnswerEvaluationCaseRequest] = Field(min_length=1, max_length=200)


class AnswerEvaluationCaseResult(EvaluationSchema):
    id: str
    question: str
    expected_answer: str = Field(alias="expectedAnswer")
    predicted_answer: str = Field(alias="predictedAnswer")
    exact_match: float = Field(alias="exactMatch", ge=0, le=1)
    token_f1: float = Field(alias="tokenF1", ge=0, le=1)
    character_similarity: float = Field(alias="characterSimilarity", ge=0, le=1)


class AnswerEvaluationResponse(EvaluationSchema):
    case_count: int = Field(alias="caseCount", ge=1)
    exact_match: float = Field(alias="exactMatch", ge=0, le=1)
    token_f1: float = Field(alias="tokenF1", ge=0, le=1)
    character_similarity: float = Field(alias="characterSimilarity", ge=0, le=1)
    results: list[AnswerEvaluationCaseResult]
