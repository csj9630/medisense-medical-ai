import unittest

from ai.rag.ingestion.cleaning import (
    clean_content,
    has_broken_unicode,
    has_html_garbage,
    is_context_broken,
    is_empty_or_too_short,
    is_prompt_template_wrapper,
)


class CleaningTest(unittest.TestCase):
    def test_normal_medical_text_survives_untouched(self) -> None:
        text = (
            "아스피린 100mg을 하루 2회(식후) 복용하며, AST 85U/L, ALT 92U/L로 상승했다. "
            "2024-01-01 검사 결과를 참고하세요."
        )
        self.assertEqual(clean_content(text), text)

    def test_numbers_units_percent_and_parens_are_not_stripped(self) -> None:
        text = "정상 혈당은 70~100mg/dL이며, 목표 체중 감량률은 5~10%(초기 6개월 기준)입니다."
        self.assertEqual(clean_content(text), text)

    def test_rejects_too_short(self) -> None:
        self.assertTrue(is_empty_or_too_short("짧음"))
        self.assertIsNone(clean_content("짧음"))

    def test_rejects_empty(self) -> None:
        self.assertIsNone(clean_content("   "))

    def test_rejects_broken_unicode(self) -> None:
        self.assertTrue(has_broken_unicode("정상적인 문장인데 중간에 �가 있습니다 진짜입니다"))

    def test_rejects_html_garbage(self) -> None:
        self.assertTrue(has_html_garbage('<div class="x">본문입니다 실제로 유효한 긴 문장입니다</div>'))
        self.assertTrue(has_html_garbage("본문에 &nbsp; 같은 html entity가 섞여있는 긴 문장입니다"))

    def test_rejects_prompt_template_wrapper(self) -> None:
        self.assertTrue(is_prompt_template_wrapper("assistant: 안녕하세요 반갑습니다 이것은 테스트 문장입니다"))
        self.assertTrue(is_prompt_template_wrapper("### Instruction\n환자의 증상을 설명하세요 반갑습니다"))

    def test_rejects_context_broken_garbled_text(self) -> None:
        garbled = "ㅁㄴㅇㄻ@#$%^&*()_+{}[]|<>?~ㅁㄴㅇㄹjklasdf!@#$asdf1234!@#$"
        self.assertTrue(is_context_broken(garbled))

    def test_does_not_false_positive_on_greek_medical_symbols(self) -> None:
        text = "γ-GT와 α-fetoprotein 수치는 간 질환 진단에 사용되는 표지자입니다."
        self.assertEqual(clean_content(text), text)


if __name__ == "__main__":
    unittest.main()
