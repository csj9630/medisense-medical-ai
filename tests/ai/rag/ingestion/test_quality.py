import unittest

from ai.rag.ingestion.quality import detect_needs_review


class QualityTest(unittest.TestCase):
    def test_dosage_keyword_triggers_review(self) -> None:
        self.assertTrue(detect_needs_review("이 약물의 권장 용량은 하루 500mg입니다."))

    def test_emergency_keyword_triggers_review(self) -> None:
        self.assertTrue(detect_needs_review("응급 상황에서는 즉시 병원을 방문해야 합니다."))

    def test_diagnosis_confirmation_keyword_triggers_review(self) -> None:
        self.assertTrue(detect_needs_review("검사 결과 위암으로 확진되었습니다."))

    def test_plain_informational_text_does_not_trigger_review(self) -> None:
        self.assertFalse(detect_needs_review("충수염은 맹장 끝에 달린 충수에 염증이 생기는 질환입니다."))


if __name__ == "__main__":
    unittest.main()
