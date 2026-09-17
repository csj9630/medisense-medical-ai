import unittest
from dataclasses import dataclass

from ai.consultation.classifier import DepartmentResult
from ai.consultation.pipeline import DEFAULT_MAX_OUTPUT_TOKENS, FALLBACK_ANSWER, consult
from ai.llm.contracts import LlmMessage


@dataclass
class FakeChunk:
    text: str
    metadata: dict | None = None


@dataclass
class FakeResult:
    answer: str
    finish_reason: str | None = None


@dataclass
class FakeExecution:
    result: FakeResult


class FakeLlmApplication:
    """llm_application.run()만 흉내내는 최소 stub — 실제 모델을 안 띄운다."""

    def __init__(
        self,
        answer: str | None = None,
        raise_error: bool = False,
        finish_reason: str | None = None,
    ) -> None:
        self._answer = answer
        self._raise_error = raise_error
        self._finish_reason = finish_reason
        self.last_model_id: str | None = None
        self.last_request = None

    async def run(self, model_id, request):  # noqa: ANN001 - 테스트 stub
        self.last_model_id = model_id
        self.last_request = request
        if self._raise_error:
            raise RuntimeError("모델을 사용할 수 없습니다.")
        return FakeExecution(
            result=FakeResult(answer=self._answer or "괜찮아지실 거예요.", finish_reason=self._finish_reason)
        )


class ConsultTest(unittest.IsolatedAsyncioTestCase):
    async def test_follow_up_reaches_provider_with_prior_question_and_answer(self) -> None:
        app = FakeLlmApplication(answer="어제부터 허리가 아프셨군요. 다친 적도 있으신가요?")
        history = (
            LlmMessage("user", "허리가 아파요"),
            LlmMessage("assistant", "언제부터 아프셨나요?"),
        )
        result = await consult(app, "어제부터요", history=history)
        messages = app.last_request.messages
        self.assertEqual([m.role for m in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(messages[1:3], history)
        self.assertEqual(messages[-1].content, "[사용자 질문]\n어제부터요")
        self.assertIn("다친 적도 있으신가요?", result.answer)

    async def test_past_emergency_does_not_override_current_question_with_hard_filter(self) -> None:
        app = FakeLlmApplication(answer="현재 궁금하신 내용을 알려주세요.")
        history = (
            LlmMessage("user", "갑자기 숨쉬기 힘들어요"),
            LlmMessage("assistant", "119에 연락하세요."),
        )
        result = await consult(app, "진료받고 회복했어요", history=history)
        self.assertIsNotNone(app.last_request)
        self.assertFalse(result.is_emergency)

    async def test_normal_answer_has_no_disclaimer_text(self) -> None:
        # 면책 문구는 이제 프론트엔드가 채팅 UI 배너로 보여준다 — 매 답변 텍스트에
        # 반복해서 붙이지 않는다(MessageBubble.tsx 참고).
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        result = await consult(app, "콧물이 나요")

        self.assertEqual(result.answer, "충분한 휴식을 취해보세요.")
        self.assertNotIn("※", result.answer)

    async def test_requests_max_output_tokens_to_avoid_mid_sentence_cutoff(self) -> None:
        # 실제 관찰된 사례 - Vast.ai 서버의 max_output_tokens 기본값(256)만 쓰면
        # 공감+원인+확인질문+주의사항을 다 담는 답변이 문장 중간에 잘렸다("...정확한
        # 진단 후 적절한"에서 끊김). 서버가 허용하는 최댓값을 명시적으로 요청해야 한다.
        app = FakeLlmApplication(answer="답변")
        await consult(app, "어깨가 아파요")

        self.assertEqual(app.last_request.max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS)

    async def test_llm_failure_returns_fallback_without_disclaimer(self) -> None:
        app = FakeLlmApplication(raise_error=True)
        result = await consult(app, "콧물이 나요")

        self.assertEqual(result.answer, FALLBACK_ANSWER)
        self.assertNotIn("※", result.answer)

    async def test_emergency_keyword_short_circuits_without_calling_llm(self) -> None:
        app = FakeLlmApplication()
        result = await consult(app, "갑자기 숨쉬기 힘들어요")

        self.assertIsNone(app.last_model_id)  # LLM이 아예 호출되지 않았어야 한다.
        self.assertIn("119", result.answer)
        self.assertIsNone(result.department)

    async def test_risky_dosage_in_llm_answer_gets_extra_warning(self) -> None:
        app = FakeLlmApplication(answer="타이레놀 500mg을 드세요.")
        result = await consult(app, "머리가 아파요")

        self.assertIn("[안전 안내]", result.answer)

    async def test_success_populates_dashboard_metadata(self) -> None:
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        result = await consult(app, "콧물이 나요", model_id="qwen-medical")

        self.assertEqual(result.model_id, "qwen-medical")
        self.assertFalse(result.is_fallback)
        self.assertFalse(result.is_emergency)
        self.assertIsNone(result.error_type)
        self.assertIsNotNone(result.response_time_ms)
        self.assertGreaterEqual(result.response_time_ms, 0)

    async def test_reference_chunks_set_rag_hit_count(self) -> None:
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        chunks = [object(), object(), object()]
        result = await consult(app, "콧물이 나요", reference_chunks=chunks)

        self.assertEqual(result.rag_hit_count, 3)

    async def test_no_reference_chunks_means_zero_rag_hit_count(self) -> None:
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        result = await consult(app, "콧물이 나요")

        self.assertEqual(result.rag_hit_count, 0)

    async def test_llm_failure_sets_fallback_flag_and_error_type(self) -> None:
        app = FakeLlmApplication(raise_error=True)
        result = await consult(app, "콧물이 나요")

        self.assertTrue(result.is_fallback)
        self.assertEqual(result.error_type, "RuntimeError")

    async def test_emergency_short_circuit_sets_emergency_flag(self) -> None:
        app = FakeLlmApplication()
        result = await consult(app, "갑자기 숨쉬기 힘들어요")

        self.assertTrue(result.is_emergency)
        self.assertFalse(result.is_fallback)
        self.assertIsNone(result.model_id)  # LLM을 아예 안 불렀으므로 model_id도 없음

    async def test_finish_reason_is_forwarded_from_provider_result(self) -> None:
        # "length"는 max_output_tokens에 걸려 답변이 중간에 잘렸다는 뜻 - 대시보드가
        # 이 비율을 집계하려면 여기서부터 값이 살아있어야 한다.
        app = FakeLlmApplication(answer="답변", finish_reason="length")
        result = await consult(app, "콧물이 나요")

        self.assertEqual(result.finish_reason, "length")

    async def test_finish_reason_is_none_when_not_provided_by_stub(self) -> None:
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        result = await consult(app, "콧물이 나요")

        self.assertIsNone(result.finish_reason)

    async def test_emergency_short_circuit_leaves_finish_reason_none(self) -> None:
        app = FakeLlmApplication()
        result = await consult(app, "갑자기 숨쉬기 힘들어요")

        self.assertIsNone(result.finish_reason)

    async def test_emergency_short_circuit_still_uses_precomputed_department(self) -> None:
        # 예전엔 응급 하드필터가 department_result를 통째로 무시하고 None을 강제해서,
        # message.py가 이미 분류까지 마쳐 넘겨준 결과가 응급 대화에서만 버려졌다
        # (관리자 화면에서 응급 대화가 전부 "기타"로만 집계되던 원인, 2026-09 실측).
        app = FakeLlmApplication()
        precomputed = DepartmentResult(department="신경과", confidence="중간")

        result = await consult(
            app,
            "갑자기 말이 어눌해지고 팔다리에 힘이 안 들어가요",
            department_result=precomputed,
        )

        self.assertTrue(result.is_emergency)
        self.assertIn("119", result.answer)
        self.assertEqual(result.department, "신경과")
        self.assertEqual(result.confidence, "중간")

    async def test_emergency_short_circuit_classifies_when_not_precomputed(self) -> None:
        # department_result를 안 넘긴 경우에도 자체 classifier로 분류를 시도해야 한다
        # (LLM은 호출하지 않으므로 model_id는 여전히 None이어야 함).
        app = FakeLlmApplication()

        result = await consult(app, "가슴이 답답하고 두근거림이 심해요")

        self.assertTrue(result.is_emergency)
        self.assertIsNone(app.last_model_id)
        self.assertEqual(result.department, "순환기내과")

    async def test_precomputed_department_result_is_used_without_reclassifying(self) -> None:
        # message.py가 RAG 검색의 진료과 부스트에도 같은 분류 결과를 쓰려고 미리
        # classify()를 해뒀다면, consult()는 그 결과를 그대로 써야 한다(자체
        # classifier를 아예 안 만들었는지까지 확인 - 만들면 낭비이자 이론상
        # 분류기 상태에 따라 값이 어긋날 여지를 만든다).
        app = FakeLlmApplication(answer="답변")
        precomputed = DepartmentResult(department="정형외과", confidence="높음")

        def _classifier_should_not_be_called():
            raise AssertionError("department_result를 미리 넘겼으면 classifier를 만들면 안 됨")

        result = await consult(
            app,
            "아무 증상 설명",
            department_result=precomputed,
            classifier=_classifier_should_not_be_called,  # 호출되면 TypeError로 즉시 드러남
        )

        self.assertEqual(result.department, "정형외과")
        self.assertEqual(result.confidence, "높음")

    async def test_falls_back_to_department_named_in_answer_when_precomputed_missed_it(self) -> None:
        # 사전 분류가 사용자 원문에서 진료과를 못 찾았어도("이 증상이 계속되네요"에는
        # 매칭되는 키워드가 없음), LLM이 RAG 참고자료까지 반영해서 답변에 명확히
        # 진료과를 하나만 언급했다면 그걸 카테고리로 채택한다.
        app = FakeLlmApplication(answer="정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")
        result = await consult(app, "이 증상이 계속되네요")

        self.assertEqual(result.department, "정형외과")
        self.assertEqual(result.confidence, "중간")

    async def test_ignores_answer_department_when_multiple_are_mentioned(self) -> None:
        # 실제 관찰된 사례 - 모델이 헷갈려서 서로 무관한 진료과를 여러 개 나열했다
        # (신경과+비뇨의학과). 어느 쪽도 확신할 근거가 없으므로 None을 유지한다 -
        # 잘못된 확신으로 엉뚱한 카테고리를 붙이는 것보다 미분류가 낫다.
        app = FakeLlmApplication(
            answer="신경과 진료센터를 추천드립니다. 비뇨의학과에서도 관련 검사가 필요합니다."
        )
        result = await consult(app, "이 증상이 계속되네요")

        self.assertIsNone(result.department)

    async def test_precomputed_department_takes_precedence_over_answer_mention(self) -> None:
        # 사전 분류가 이미 확신을 가졌다면(department가 있음), 답변에 다른 진료과
        # 이름이 우연히 섞여 있어도 사전 분류 결과를 그대로 유지한다 - 프롬프트
        # 힌트도 이미 그 진료과 기준으로 나갔으므로 일관성을 유지하는 쪽이 안전하다.
        app = FakeLlmApplication(answer="이비인후과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")
        precomputed = DepartmentResult(department="정형외과", confidence="중간")

        result = await consult(app, "어깨가 아파요", department_result=precomputed)

        self.assertEqual(result.department, "정형외과")

    async def test_non_answer_from_llm_is_replaced_with_fallback_answer(self) -> None:
        # response_validator.validate()가 메타 지시문만 있는 답변을 빈 문자열로
        # 걸러내면, LLM 호출 자체는 성공했어도 사용자에게는 FALLBACK_ANSWER를 보여야
        # 한다(실제 의료 답변이 아니므로).
        app = FakeLlmApplication(
            answer="답변 완료 후에는 새로운 프롬프트와 함께 다시 시작하십시오. 감사합니다!"
        )
        result = await consult(app, "목이 아파요")

        self.assertEqual(result.answer, FALLBACK_ANSWER)
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.error_type, "NonAnswerFiltered")

    async def test_rag_chunk_department_is_used_when_precomputed_is_low_confidence(self) -> None:
        # 사전 분류가 확신이 낮으면(또는 아예 없으면), 실제 검색된 참고 문서의 진료과
        # 메타데이터를 우선 채택한다 - 사용자 원문 키워드보다 검색된 근거가 더 신뢰도
        # 높은 신호라고 보기 때문.
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        chunks = [
            FakeChunk(text="내용1", metadata={"department": ["안과"]}),
            FakeChunk(text="내용2", metadata={"department": ["안과"]}),
        ]

        result = await consult(app, "눈이 좀 불편해요", reference_chunks=chunks)

        self.assertEqual(result.department, "안과")
        self.assertEqual(result.confidence, "높음")

    async def test_high_confidence_precomputed_department_is_not_overridden_by_rag(self) -> None:
        # 반대로 사전 분류가 이미 "높음"으로 확신했다면, RAG 문서 하나가 다른 진료과를
        # 가리켜도 뒤집지 않는다 - RAG가 무관한 문서를 끌어온 사례가 실제로 있었기
        # 때문에(2026-09), 강한 신호를 약한 신호로 덮어쓰지 않게 보수적으로 둔다.
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        precomputed = DepartmentResult(department="정형외과", confidence="높음")
        chunks = [FakeChunk(text="내용", metadata={"department": ["피부과"]})]

        result = await consult(
            app,
            "어깨가 결려서 병원에 가야할지 고민이에요",
            department_result=precomputed,
            reference_chunks=chunks,
        )

        self.assertEqual(result.department, "정형외과")

    async def test_execution_without_provider_or_tokens_leaves_them_none(self) -> None:
        # 테스트 stub(FakeExecution)처럼 provider/토큰 필드가 없는 llm_application도
        # 로깅 메타데이터 때문에 깨지면 안 된다 — 조용히 None으로 빠져야 한다.
        app = FakeLlmApplication(answer="충분한 휴식을 취해보세요.")
        result = await consult(app, "콧물이 나요")

        self.assertIsNone(result.provider_key)
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)
        self.assertIsNone(result.total_tokens)


if __name__ == "__main__":
    unittest.main()
