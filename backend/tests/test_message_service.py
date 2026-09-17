import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from app.services import message as message_module
from app.services.message import MessageService
from ai.llm.contracts import LlmMessage


def _bare_service(db) -> MessageService:
    # ConversationService/ConversationRepository/MessageRepository는 진짜 DB 쿼리를
    # 하므로, 여기서 테스트하려는 RAG/모델 선택 로직만 떼어내기 위해 __init__을
    # 건너뛰고 필요한 속성만 채운다.
    service = MessageService.__new__(MessageService)
    service.db = db
    service.conversations = MagicMock()
    service.consultation_logs = MagicMock()
    return service


class SearchReferenceChunksTest(unittest.TestCase):
    def test_returns_search_result_on_success(self) -> None:
        db = MagicMock()
        service = _bare_service(db)
        fake_chunks = [object()]
        with patch.object(message_module.rag_search_service, "search", return_value=fake_chunks):
            result = service._search_reference_chunks("두통이 있어요")
        self.assertEqual(result, fake_chunks)
        db.rollback.assert_not_called()

    def test_swallows_exception_and_rolls_back_session(self) -> None:
        # chunk_embeddings 테이블이 아직 마이그레이션 안 된 경우 등을 흉내낸다 —
        # 검색이 실패해도 빈 리스트를 반환하고, DB 세션을 롤백해서 이후 이 요청의
        # 다른 DB 작업(응답 메시지 저장 등)이 "트랜잭션 abort" 상태로 실패하지
        # 않게 해야 한다.
        db = MagicMock()
        service = _bare_service(db)
        with patch.object(
            message_module.rag_search_service, "search", side_effect=RuntimeError("relation does not exist")
        ):
            result = service._search_reference_chunks("두통이 있어요")
        self.assertEqual(result, [])
        db.rollback.assert_called_once()


class GenerateReplyTest(unittest.IsolatedAsyncioTestCase):
    async def test_follow_up_search_uses_user_history_and_passes_dialogue_to_consult(self):
        service = _bare_service(MagicMock())
        history = (
            LlmMessage("user", "허리가 아파요"),
            LlmMessage("assistant", "두통도 있나요? 언제부터 아프셨나요?"),
        )
        fake_result = message_module.ConsultationResult(answer="답변", department="정형외과", confidence="중간")
        with (
            patch.object(message_module, "consult", return_value=fake_result) as mock_consult,
            patch.object(message_module.rag_search_service, "search", return_value=[]) as mock_search,
        ):
            await service._generate_reply("어제부터요", MagicMock(), history=history)
        self.assertEqual(mock_consult.call_args.args[1], "어제부터요")
        self.assertEqual(mock_consult.call_args.kwargs["history"], history)
        mock_search.assert_called_once_with(service.db, "허리가 아파요\n어제부터요", department="정형외과")

    async def test_new_explicit_symptom_takes_priority_over_previous_department(self):
        service = _bare_service(MagicMock())
        history = (LlmMessage("user", "허리가 아파요"), LlmMessage("assistant", "언제부터인가요?"))
        fake_result = message_module.ConsultationResult(answer="답변", department="피부과", confidence="중간")
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]) as mock_search,
        ):
            await service._generate_reply("다른 질문인데 피부가 가려워요", MagicMock(), history=history)
        mock_search.assert_called_once_with(service.db, "다른 질문인데 피부가 가려워요", department="피부과")

    async def test_send_message_snapshots_owned_conversation_before_saving_current_question(self):
        service = _bare_service(MagicMock())
        service.conversations_service = MagicMock()
        service.messages = MagicMock()
        conversation = SimpleNamespace(id=uuid4(), is_title_custom=False)
        service.conversations_service.get_owned.return_value = conversation
        previous = [LlmMessage("user", "허리가 아파요"), LlmMessage("assistant", "언제부터인가요?")]
        service.messages.list_by_conversation.return_value = previous

        def create(conversation_id, role, content):
            previous.append(LlmMessage(role, content))
            return SimpleNamespace(id=uuid4(), role=role, content=content)

        service.messages.create.side_effect = create
        user = SimpleNamespace(id=uuid4(), auth_provider="email")
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        with (
            patch.object(message_module, "consult", return_value=fake_result) as mock_consult,
            patch.object(message_module.rag_search_service, "search", return_value=[]),
            patch.object(message_module, "to_message_response", side_effect=lambda m: m),
        ):
            response = await service.send_message(str(conversation.id), user, "어제부터요")
        service.conversations_service.get_owned.assert_called_once_with(str(conversation.id), user.id)
        service.messages.list_by_conversation.assert_called_once_with(conversation.id)
        self.assertEqual(len(mock_consult.call_args.kwargs["history"]), 2)
        self.assertEqual(mock_consult.call_args.kwargs["history"][1].content, "언제부터인가요?")
        self.assertEqual(response.content, "답변")

    async def test_short_reply_after_topic_change_uses_most_recent_symptom(self):
        service = _bare_service(MagicMock())
        history = (
            LlmMessage("user", "허리와 무릎 관절이 아파요"),
            LlmMessage("assistant", "언제부터인가요?"),
            LlmMessage("user", "다른 질문인데 피부가 가려워요"),
            LlmMessage("assistant", "가려움은 언제부터인가요?"),
        )
        fake_result = message_module.ConsultationResult(answer="답변", department="피부과", confidence="중간")
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]) as mock_search,
        ):
            await service._generate_reply("어제부터요", MagicMock(), history=history)
        mock_search.assert_called_once_with(
            service.db, "다른 질문인데 피부가 가려워요\n어제부터요", department="피부과"
        )

    async def test_empty_content_returns_canned_text_without_touching_rag_or_llm(self) -> None:
        service = _bare_service(MagicMock())
        with (
            patch.object(message_module, "consult") as mock_consult,
            patch.object(message_module.rag_search_service, "search") as mock_search,
        ):
            reply, result = await service._generate_reply("", conversation=MagicMock())

        self.assertIn("첨부해주신 파일", reply)
        self.assertIsNone(result)  # 실제 상담이 아니므로 대시보드 로그 대상이 아님
        mock_consult.assert_not_called()
        mock_search.assert_not_called()

    async def test_model_id_is_forwarded_to_consult_when_given(self) -> None:
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        with (
            patch.object(message_module, "consult", return_value=fake_result) as mock_consult,
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("질문", conversation=MagicMock(), model_id="qwen")

        self.assertEqual(mock_consult.call_args.kwargs.get("model_id"), "qwen")

    async def test_no_model_id_does_not_pass_model_id_kwarg(self) -> None:
        # model_id를 안 보내면 consult()의 기본값(DEFAULT_MODEL_ID)이 그대로 적용돼야
        # 한다 — 여기서 None을 넘기면 consult()가 "model_id=None"으로 오해할 수 있다.
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        with (
            patch.object(message_module, "consult", return_value=fake_result) as mock_consult,
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("질문", conversation=MagicMock())

        self.assertNotIn("model_id", mock_consult.call_args.kwargs)

    async def test_department_result_sets_category_if_unset(self) -> None:
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department="내과", confidence="높음")
        conversation = MagicMock()
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("질문", conversation=conversation)

        service.conversations.set_category_if_unset.assert_called_once_with(conversation, "내과")

    async def test_no_department_result_sets_category_to_etc(self) -> None:
        # 분류기가 진료과를 특정 못해도(department=None) 카테고리를 비워두지 않고
        # "기타"로 채운다 — 사이드바 "진료과별" 그룹에서 미분류로 남지 않게 한다.
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        conversation = MagicMock()
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("질문", conversation=conversation)

        service.conversations.set_category_if_unset.assert_called_once_with(conversation, "기타")

    async def test_classified_department_is_forwarded_to_rag_search(self) -> None:
        # RAG 검색의 진료과 소프트 부스트(rag_search_service.search의 department=)가
        # 실제로 값을 받으려면, _generate_reply가 미리 분류해서 넘겨줘야 한다.
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]) as mock_search,
        ):
            await service._generate_reply("허리가 아파요", conversation=MagicMock())

        self.assertEqual(mock_search.call_args.kwargs.get("department"), "정형외과")

    async def test_classified_department_result_is_forwarded_to_consult(self) -> None:
        # consult()가 다시 분류하지 않고 같은 결과를 재사용하도록(pipeline.py의
        # department_result=) 넘겨야 한다.
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")
        with (
            patch.object(message_module, "consult", return_value=fake_result) as mock_consult,
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("허리가 아파요", conversation=MagicMock())

        forwarded = mock_consult.call_args.kwargs.get("department_result")
        self.assertIsNotNone(forwarded)
        self.assertEqual(forwarded.department, "정형외과")

    async def test_fallback_result_does_not_touch_category(self) -> None:
        # LLM 호출 자체가 실패한 경우(is_fallback=True)는 실제 상담이 아니므로 카테고리를
        # "기타"로 확정해버리면 안 된다 — 다음 정상 응답이 영영 반영 안 될 수 있다.
        service = _bare_service(MagicMock())
        fake_result = message_module.ConsultationResult(
            answer="대체 응답", department=None, confidence="낮음", is_fallback=True
        )
        conversation = MagicMock()
        with (
            patch.object(message_module, "consult", return_value=fake_result),
            patch.object(message_module.rag_search_service, "search", return_value=[]),
        ):
            await service._generate_reply("질문", conversation=conversation)

        service.conversations.set_category_if_unset.assert_not_called()


class LogConsultationTest(unittest.TestCase):
    def test_success_writes_log_via_repository(self) -> None:
        db = MagicMock()
        service = _bare_service(db)
        result = message_module.ConsultationResult(answer="답변", department="내과", confidence="높음")
        user_id, conversation_id, message_id = uuid4(), uuid4(), uuid4()

        service._log_consultation(user_id, conversation_id, message_id, result)

        service.consultation_logs.create.assert_called_once_with(
            user_id=user_id, conversation_id=conversation_id, message_id=message_id, result=result
        )
        db.rollback.assert_not_called()

    def test_failure_is_swallowed_and_rolls_back_without_raising(self) -> None:
        # 대시보드 로그 저장이 실패해도(DB 오류 등) 이미 사용자에게 나갈 응답은
        # 정해진 뒤라 — 절대 예외를 밖으로 던지면 안 된다(채팅 자체가 깨짐).
        db = MagicMock()
        service = _bare_service(db)
        service.consultation_logs.create.side_effect = RuntimeError("DB unavailable")
        result = message_module.ConsultationResult(answer="답변", department=None, confidence="낮음")

        try:
            service._log_consultation(uuid4(), uuid4(), uuid4(), result)
        except Exception:  # noqa: BLE001 - 여기서 예외가 나오면 테스트 자체가 실패해야 함
            self.fail("_log_consultation이 예외를 밖으로 던지면 안 됨")

        db.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
