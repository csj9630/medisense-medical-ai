import unittest

from ai.consultation.classifier import KeywordDepartmentClassifier


class KeywordDepartmentClassifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = KeywordDepartmentClassifier()

    def test_clear_single_match_returns_high_confidence(self) -> None:
        result = self.classifier.classify("얼굴에 발진이랑 두드러기가 났어요")
        self.assertEqual(result.department, "피부과")
        self.assertEqual(result.confidence, "높음")

    def test_ambiguous_match_returns_medium_confidence(self) -> None:
        # "두통" 하나만 있으면 신경과/내과 둘 다 후보라 확정하지 않는다.
        result = self.classifier.classify("두통이 있어요")
        self.assertIsNotNone(result.department)
        self.assertIn(result.confidence, ("중간", "높음"))

    def test_matches_keyword_without_spacing(self) -> None:
        # 실제 사용자 입력에서 자주 관찰된 실패 사례 — "배가 아"(키워드)에는 공백이
        # 있는데 "배가아파서"(실제 문장)는 붙여 써서 매칭이 안 됐다.
        result = self.classifier.classify(
            "배가아파서 화장실을 갔다왔는데, 그래도 계속 배가아프네.. 이런경우에는 어떤 진료과로 진료롤 봐야해?"
        )
        self.assertEqual(result.department, "내과")

    def test_matches_eye_pressure_keyword(self) -> None:
        # 실제 오분류 사례 — "안압"이 안과 키워드 목록에 없어서 "기타"로 빠졌다.
        result = self.classifier.classify(
            "안압이 올라가는 듯한 느낌이드는데, 피곤해서 그런건가? 일시적인현상인거겠지? "
            "이럴땐 어느 병원으로 가서 진료를 받아야해?"
        )
        self.assertEqual(result.department, "안과")

    def test_matches_eye_fatigue_and_eye_pain_phrasing(self) -> None:
        # 실제 오분류 사례 — "눈에 통증"/"눈이 피로한"이 목록에 없어서 "기타"로 빠졌다.
        result = self.classifier.classify(
            "눈이 피로한건지 눈에 통증이 살짝 있는데 어느병원으로 진료를 받으러 가야할지 "
            "잘모르겠는데 어떤 진료과의 병원으로 진료를 받으러 가야해?"
        )
        self.assertEqual(result.department, "안과")

    def test_matches_shoulder_pain_and_neck_stiffness_phrasing(self) -> None:
        # 실제 오분류 사례 — "어깨 통증"/"목 통증"이 붙어있는 형태로만 키워드에
        # 있어서 "어깨에 통증이", "고개도 잘 안 돌아가고"처럼 조사가 낀 자연스러운
        # 문장은 매칭이 안 되고 "기타"로 빠졌다. "어깨"/"고개"를 단독 키워드로 바꿈.
        result = self.classifier.classify(
            "아침에 일어나니 어깨에 통증이 있네 고개도 잘안돌아가고 이럴땐 어느 진료과로 진료를 봐야해?"
        )
        self.assertEqual(result.department, "정형외과")

    def test_matches_colloquial_muscle_stiffness_wording(self) -> None:
        # "결리다"/"뻐근하다" 계열도 실제로 자주 쓰이는 표현인데 목록에 없었다.
        result = self.classifier.classify("어깨가 결려서 병원에 가야할지 고민이에요")
        self.assertEqual(result.department, "정형외과")

    def test_matches_cardiac_symptom_phrasing(self) -> None:
        # 실제 오분류 사례(2026-09 라이브 테스트) — 순환기내과 카테고리 자체가 없어서
        # "두근거림"/"가슴 답답" 같은 흉부 증상이 어디에도 안 걸리고 "기타"로 빠졌다.
        result = self.classifier.classify("요즘 두근거림이 심하고 가슴이 답답한 느낌이 자주 들어요")
        self.assertEqual(result.department, "순환기내과")

    def test_no_match_returns_low_confidence_and_no_department(self) -> None:
        result = self.classifier.classify("안녕하세요")
        self.assertIsNone(result.department)
        self.assertEqual(result.confidence, "낮음")

    def test_empty_query_returns_low_confidence(self) -> None:
        result = self.classifier.classify("   ")
        self.assertIsNone(result.department)
        self.assertEqual(result.confidence, "낮음")


if __name__ == "__main__":
    unittest.main()
