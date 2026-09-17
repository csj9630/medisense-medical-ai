"""정답 데이터 파싱과 답변 성능지표 계산 흐름을 관리합니다."""

import csv
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from ai.evaluation import character_similarity, exact_match, token_f1
from app.schemas.evaluation import (
    AnswerEvaluationCaseResult,
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
    GroundTruthCaseResponse,
    GroundTruthParseResponse,
)

MAX_GROUND_TRUTH_BYTES = 2 * 1024 * 1024
MAX_GROUND_TRUTH_CASES = 200
SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".csv", ".txt"}
QUESTION_KEYS = ("question", "query", "질문")
ANSWER_KEYS = ("expected_answer", "expectedAnswer", "ground_truth", "answer", "정답")


class GroundTruthValidationError(Exception):
    """정답 데이터 형식이나 내용이 유효하지 않을 때 발생합니다."""


class GroundTruthTooLargeError(GroundTruthValidationError):
    """정답 파일이 허용 크기를 초과했을 때 발생합니다."""


@dataclass(frozen=True)
class ParsedGroundTruth:
    question: str
    expected_answer: str


async def parse_ground_truth_input(
    *,
    text: str | None,
    file: UploadFile | None,
) -> GroundTruthParseResponse:
    """텍스트 또는 파일을 읽고 동일한 정답 Case 목록으로 변환합니다."""

    has_text = bool(text and text.strip())
    if has_text == (file is not None):
        raise GroundTruthValidationError("정답 텍스트와 파일 중 하나만 입력해 주세요.")

    if file is not None:
        file_name = Path((file.filename or "").replace("\\", "/")).name
        extension = Path(file_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise GroundTruthValidationError("JSON, JSONL, CSV, TXT 파일만 업로드할 수 있습니다.")
        content = await file.read(MAX_GROUND_TRUTH_BYTES + 1)
        if len(content) > MAX_GROUND_TRUTH_BYTES:
            raise GroundTruthTooLargeError("정답 데이터 파일은 2MB 이하여야 합니다.")
        try:
            source_text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise GroundTruthValidationError("정답 데이터 파일은 UTF-8로 저장해 주세요.") from exc
        source_name = file_name
        cases = _parse_by_extension(source_text, extension)
    else:
        source_text = (text or "").strip()
        source_name = "직접 입력"
        cases = _parse_text_input(source_text)

    validated = _validate_cases(cases)
    return GroundTruthParseResponse(
        sourceName=source_name,
        cases=[
            GroundTruthCaseResponse(
                id=f"case-{index}",
                question=case.question,
                expectedAnswer=case.expected_answer,
            )
            for index, case in enumerate(validated, start=1)
        ],
    )


def evaluate_answers(request: AnswerEvaluationRequest) -> AnswerEvaluationResponse:
    """각 정답과 모델 답변의 지표를 계산하고 평균을 반환합니다."""

    results = [
        AnswerEvaluationCaseResult(
            id=case.id,
            question=case.question,
            expectedAnswer=case.expected_answer,
            predictedAnswer=case.predicted_answer,
            exactMatch=exact_match(case.expected_answer, case.predicted_answer),
            tokenF1=token_f1(case.expected_answer, case.predicted_answer),
            characterSimilarity=character_similarity(case.expected_answer, case.predicted_answer),
        )
        for case in request.cases
    ]
    case_count = len(results)
    return AnswerEvaluationResponse(
        caseCount=case_count,
        exactMatch=sum(result.exact_match for result in results) / case_count,
        tokenF1=sum(result.token_f1 for result in results) / case_count,
        characterSimilarity=sum(result.character_similarity for result in results) / case_count,
        results=results,
    )


def _parse_by_extension(text: str, extension: str) -> list[ParsedGroundTruth]:
    if extension == ".json":
        return _parse_json(text)
    if extension == ".jsonl":
        return _parse_jsonl(text)
    if extension == ".csv":
        return _parse_csv(text)
    return _parse_text_input(text)


def _parse_json(text: str) -> list[ParsedGroundTruth]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GroundTruthValidationError("JSON 형식을 확인해 주세요.") from exc
    if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        payload = payload["cases"]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise GroundTruthValidationError("JSON은 정답 객체 배열이어야 합니다.")
    return [_case_from_mapping(item, index) for index, item in enumerate(payload, start=1)]


def _parse_jsonl(text: str) -> list[ParsedGroundTruth]:
    cases: list[ParsedGroundTruth] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GroundTruthValidationError(f"JSONL {index}번째 줄 형식을 확인해 주세요.") from exc
        cases.append(_case_from_mapping(payload, index))
    return cases


def _parse_csv(text: str) -> list[ParsedGroundTruth]:
    try:
        dialect = csv.Sniffer().sniff(text[:4_096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise GroundTruthValidationError("CSV Header에 question과 answer가 필요합니다.")
    # csv 모듈의 기본 field_size_limit(128KB)이 앱이 실제로 허용하는 파일 크기
    # 한도(MAX_GROUND_TRUTH_BYTES, 2MB)보다 훨씬 작아서, TC-EVAL-004 수정으로
    # 프레임워크의 1MB 제한을 넘긴 뒤에도 128KB~2MB 사이 필드 하나만으로 여기서
    # 처리되지 않은 _csv.Error가 나며 그대로 500으로 터졌다. 파일 전체가 이미
    # MAX_GROUND_TRUTH_BYTES로 제한돼 있으니 필드 하나도 그 이상 클 수 없다 -
    # 한도를 맞춰서 정상적으로 파싱되게 하고, 전역 상태이므로 파싱 후 원래
    # 값으로 되돌린다.
    previous_field_size_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_GROUND_TRUTH_BYTES)
    try:
        return [_case_from_mapping(row, index) for index, row in enumerate(reader, start=1)]
    finally:
        csv.field_size_limit(previous_field_size_limit)


def _parse_text_input(text: str) -> list[ParsedGroundTruth]:
    if not text.strip():
        raise GroundTruthValidationError("정답 데이터를 입력해 주세요.")
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return _parse_json(text)

    labelled_cases = _parse_labelled_blocks(text)
    if labelled_cases:
        return labelled_cases

    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    delimiter = "\t" if any("\t" in line for line in nonempty_lines) else "|"
    if any(delimiter in line for line in nonempty_lines):
        cases: list[ParsedGroundTruth] = []
        for index, line in enumerate(nonempty_lines, start=1):
            if delimiter not in line:
                raise GroundTruthValidationError(
                    f"직접 입력 {index}번째 줄을 '질문{delimiter}정답' 형식으로 입력해 주세요."
                )
            question, answer = line.split(delimiter, 1)
            cases.append(ParsedGroundTruth(question.strip(), answer.strip()))
        return cases

    # 구분자가 없는 일반 텍스트는 질문 없는 단일 정답으로 취급합니다.
    return [ParsedGroundTruth("직접 입력 항목", text.strip())]


def _parse_labelled_blocks(text: str) -> list[ParsedGroundTruth]:
    blocks = [block.strip() for block in text.replace("\r\n", "\n").split("\n---\n") if block.strip()]
    if not any("정답:" in block or "answer:" in block.lower() for block in blocks):
        return []

    cases: list[ParsedGroundTruth] = []
    for index, block in enumerate(blocks, start=1):
        question = ""
        answer_lines: list[str] = []
        reading_answer = False
        for line in block.splitlines():
            lowered = line.lower().strip()
            if lowered.startswith("질문:") or lowered.startswith("question:"):
                question = line.split(":", 1)[1].strip()
                reading_answer = False
            elif lowered.startswith("정답:") or lowered.startswith("answer:"):
                answer_lines.append(line.split(":", 1)[1].strip())
                reading_answer = True
            elif reading_answer:
                answer_lines.append(line.strip())
        cases.append(ParsedGroundTruth(question or f"항목 {index}", "\n".join(answer_lines).strip()))
    return cases


def _case_from_mapping(payload: Any, index: int) -> ParsedGroundTruth:
    if not isinstance(payload, dict):
        raise GroundTruthValidationError(f"{index}번째 정답 항목은 객체여야 합니다.")
    question = _first_string(payload, QUESTION_KEYS) or f"항목 {index}"
    answer = _first_string(payload, ANSWER_KEYS)
    return ParsedGroundTruth(question, answer)


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _validate_cases(cases: list[ParsedGroundTruth]) -> list[ParsedGroundTruth]:
    if not cases:
        raise GroundTruthValidationError("정답 데이터가 비어 있습니다.")
    if len(cases) > MAX_GROUND_TRUTH_CASES:
        raise GroundTruthValidationError(f"정답 데이터는 최대 {MAX_GROUND_TRUTH_CASES}개까지 평가할 수 있습니다.")
    for index, case in enumerate(cases, start=1):
        if not case.expected_answer:
            raise GroundTruthValidationError(f"{index}번째 항목의 정답이 비어 있습니다.")
        if len(case.question) > 2_000:
            raise GroundTruthValidationError(f"{index}번째 질문은 2,000자 이하여야 합니다.")
        if len(case.expected_answer) > 20_000:
            raise GroundTruthValidationError(f"{index}번째 정답은 20,000자 이하여야 합니다.")
    return cases
