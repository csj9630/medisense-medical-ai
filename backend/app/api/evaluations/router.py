from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.schemas.evaluation import (
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
    GroundTruthParseResponse,
)
from app.services.evaluation import (
    MAX_GROUND_TRUTH_BYTES,
    GroundTruthTooLargeError,
    GroundTruthValidationError,
    evaluate_answers,
    parse_ground_truth_input,
)

router = APIRouter()

# 2026-09-09 통합테스트에서 실제로 재현된 버그(TC-EVAL-004): FastAPI의 File()/Form()
# 자동 주입은 내부적으로 Starlette Request.form()을 기본값(max_part_size=1MB)으로
# 호출한다 - FastAPI가 이 값을 오버라이드할 방법을 아예 노출하지 않아서, 앱이
# 의도한 2MB 검증(parse_ground_truth_input의 GroundTruthTooLargeError, 413)이
# 실행되기도 전에 Starlette가 먼저 400 "Field exceeded maximum size of 1024KB"로
# 거부해버렸다. Request를 직접 받아서 더 넉넉한 max_part_size로 직접 파싱하면
# 앱 자체의 2MB 검증까지 정상적으로 도달한다.
_FORM_PART_SIZE_LIMIT = MAX_GROUND_TRUTH_BYTES + 1024 * 1024  # 앱 한도(2MB)보다 여유 있게


@router.post("/ground-truth/parse", response_model=GroundTruthParseResponse)
async def parse_ground_truth(request: Request) -> GroundTruthParseResponse:
    """정답 텍스트 또는 파일을 평가 가능한 Case 목록으로 변환합니다."""

    form = await request.form(max_part_size=_FORM_PART_SIZE_LIMIT)
    text_value = form.get("text")
    file_value = form.get("file")
    text = text_value if isinstance(text_value, str) else None
    # request.form()이 직접 만들어주는 파일 값은 fastapi.UploadFile이 아니라
    # starlette.datastructures.UploadFile이다(fastapi.UploadFile은 그 하위
    # 클래스일 뿐이라 isinstance(file_value, fastapi.UploadFile)은 항상
    # False였다) - 그래서 모든 실제 파일 업로드가 file=None으로 조용히
    # 사라져 파일 파싱 자체가 깨지고, text+file 동시 입력 거부 검증도 file이
    # 항상 None이 되면서 무력화됐다. parse_ground_truth_input은 .filename과
    # .read()만 쓰므로 starlette의 UploadFile을 그대로 넘겨도 동작한다.
    file = file_value if isinstance(file_value, StarletteUploadFile) else None

    try:
        return await parse_ground_truth_input(text=text, file=file)
    except GroundTruthTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except GroundTruthValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/answers/run", response_model=AnswerEvaluationResponse)
def run_answer_evaluation(payload: AnswerEvaluationRequest) -> AnswerEvaluationResponse:
    """입력된 정답과 모델 답변을 항목별·평균 지표로 계산합니다."""

    return evaluate_answers(payload)
