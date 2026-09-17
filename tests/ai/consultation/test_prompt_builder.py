import unittest

from ai.consultation.classifier import DepartmentResult
from ai.consultation.prompt_builder import build_messages


class DepartmentBlockTest(unittest.TestCase):
    def test_no_department_result_omits_block(self) -> None:
        messages = build_messages("두통이 있어요")
        user_content = messages[1].content
        self.assertNotIn("참고용 진료과", user_content)

    def test_department_result_with_none_department_omits_block(self) -> None:
        result = DepartmentResult(department=None, confidence="낮음")
        messages = build_messages("애매한 증상이에요", department_result=result)
        self.assertNotIn("참고용 진료과", messages[1].content)

    def test_department_hint_is_not_wrapped_in_parentheses(self) -> None:
        # 실제 관찰된 사례 - 힌트 자체를 괄호로 감싸서 주면, 모델이 그 스타일을
        # 그대로 따라 해서 답변 마지막 문장 전체를 괄호로 감싸버렸다
        # ("(정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.)"). 힌트
        # 텍스트 자체에는 괄호가 없어야 한다(안에 "참고용 진료과 정보" 자체가
        # 괄호로 시작/끝나지 않는지 확인).
        result = DepartmentResult(department="정형외과", confidence="중간")
        messages = build_messages("어깨가 아파요", department_result=result)
        user_content = messages[1].content

        hint_line = next(line for line in user_content.split("\n\n") if "참고용 진료과" in line)
        self.assertFalse(hint_line.startswith("("))
        self.assertFalse(hint_line.rstrip().endswith(")"))

    def test_department_hint_explicitly_forbids_parenthetical_output(self) -> None:
        result = DepartmentResult(department="정형외과", confidence="중간")
        messages = build_messages("어깨가 아파요", department_result=result)
        user_content = messages[1].content
        self.assertIn("괄호", user_content)
        self.assertIn("정형외과", user_content)

    def test_department_and_reference_and_question_all_included(self) -> None:
        result = DepartmentResult(department="내과", confidence="높음")
        messages = build_messages(
            "배가 아파요", department_result=result, reference_info_block="[참고 의료 정보]\n내용"
        )
        user_content = messages[1].content
        self.assertIn("내과", user_content)
        self.assertIn("[참고 의료 정보]", user_content)
        self.assertIn("[사용자 질문]\n배가 아파요", user_content)

    def test_system_message_is_loaded_from_prompt_file(self) -> None:
        messages = build_messages("질문")
        self.assertEqual(messages[0].role, "system")
        self.assertIn("MediSense", messages[0].content)


if __name__ == "__main__":
    unittest.main()
