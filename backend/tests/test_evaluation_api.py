import unittest

from fastapi.testclient import TestClient

from app.main import app


class EvaluationApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_parses_csv_ground_truth_upload(self) -> None:
        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            files={
                "file": (
                    "ground-truth.csv",
                    "question,answer\n두통이 있을 때?,휴식하고 지속되면 진료받습니다.\n",
                    "text/csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sourceName"], "ground-truth.csv")
        self.assertEqual(len(payload["cases"]), 1)
        self.assertEqual(payload["cases"][0]["question"], "두통이 있을 때?")
        self.assertEqual(payload["cases"][0]["expectedAnswer"], "휴식하고 지속되면 진료받습니다.")

    def test_parses_json_jsonl_and_txt_uploads(self) -> None:
        cases = (
            (
                "answers.json",
                '[{"question":"질문 JSON","expected_answer":"정답 JSON"}]',
                "질문 JSON",
                "정답 JSON",
            ),
            (
                "answers.jsonl",
                '{"query":"질문 JSONL","ground_truth":"정답 JSONL"}\n',
                "질문 JSONL",
                "정답 JSONL",
            ),
            ("answers.txt", "질문: 질문 TXT\n정답: 정답 TXT", "질문 TXT", "정답 TXT"),
        )
        for file_name, content, question, answer in cases:
            with self.subTest(file_name=file_name):
                response = self.client.post(
                    "/api/evaluations/ground-truth/parse",
                    files={"file": (file_name, content.encode("utf-8"), "text/plain")},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["cases"][0]["question"], question)
                self.assertEqual(response.json()["cases"][0]["expectedAnswer"], answer)

    def test_rejects_unsupported_ground_truth_file(self) -> None:
        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            files={"file": ("answers.xlsx", b"not-a-spreadsheet", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 422)

    def test_parses_direct_labelled_text(self) -> None:
        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            data={
                "text": "질문: 감기 증상은?\n정답: 기침과 콧물 등이 나타날 수 있습니다."
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cases"][0]["question"], "감기 증상은?")

    def test_plain_text_becomes_single_ground_truth_answer(self) -> None:
        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            data={"text": "충분히 휴식하고 증상이 지속되면 진료를 받습니다."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["cases"]), 1)
        self.assertEqual(response.json()["cases"][0]["question"], "직접 입력 항목")

    def test_file_between_1mb_and_2mb_is_accepted_not_rejected_by_framework(self) -> None:
        # 2026-09-09 통합테스트에서 실제로 재현된 버그(TC-EVAL-004): FastAPI의
        # File()/Form() 자동 주입이 Starlette의 기본 max_part_size(1MB)를 그대로
        # 써서, 앱이 의도한 2MB 한도(GroundTruthTooLargeError, 413)에 도달하기도
        # 전에 1MB~2MB 사이 파일이 400 "Field exceeded maximum size of 1024KB"로
        # 거부됐다. 1MB보다 크지만 2MB보다는 작은 실제 파일로 재현/검증한다.
        # 정답 하나를 거대하게 만들면 20,000자 항목별 상한(app/services/evaluation.py
        # _validate_cases)에 걸려버리므로, 실제 대용량 CSV처럼 여러 줄로 나눠서
        # 총합만 1MB~2MB 사이가 되게 만든다(각 줄은 상한보다 훨씬 작음).
        row_answer = "지속되면 진료를 받으세요. " * 200  # 약 3KB, 20,000자 한도보다 훨씬 작음
        rows = "\n".join(f"두통이 있을 때 {i}?,{row_answer}" for i in range(150))  # 약 1.2MB, 최대 200개 이하
        content = f"question,answer\n{rows}\n"
        self.assertGreater(len(content.encode("utf-8")), 1024 * 1024)
        self.assertLess(len(content.encode("utf-8")), 2 * 1024 * 1024)

        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            files={"file": ("large.csv", content.encode("utf-8"), "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cases"][0]["question"], "두통이 있을 때 0?")

    def test_file_over_2mb_gets_app_413_not_framework_400(self) -> None:
        padding = "x" * (2_200_000)  # 앱 한도(2MB)를 실제로 넘김
        content = f"question,answer\n질문,{padding}\n"

        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            files={"file": ("too_large.csv", content.encode("utf-8"), "text/csv")},
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("2MB", response.json()["detail"])

    def test_rejects_text_and_file_at_the_same_time(self) -> None:
        response = self.client.post(
            "/api/evaluations/ground-truth/parse",
            data={"text": "정답"},
            files={"file": ("answers.txt", "정답", "text/plain")},
        )

        self.assertEqual(response.status_code, 422)

    def test_answer_evaluation_returns_average_and_case_metrics(self) -> None:
        response = self.client.post(
            "/api/evaluations/answers/run",
            json={
                "cases": [
                    {
                        "id": "case-1",
                        "question": "질문 1",
                        "expectedAnswer": "충분한 휴식",
                        "predictedAnswer": "충분한 휴식",
                    },
                    {
                        "id": "case-2",
                        "question": "질문 2",
                        "expectedAnswer": "고혈압 관리",
                        "predictedAnswer": "고혈압 약물 관리",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["caseCount"], 2)
        self.assertEqual(payload["exactMatch"], 0.5)
        self.assertAlmostEqual(payload["tokenF1"], 0.9)
        self.assertEqual(payload["results"][0]["exactMatch"], 1.0)

    def test_rejects_empty_predicted_answer(self) -> None:
        response = self.client.post(
            "/api/evaluations/answers/run",
            json={
                "cases": [
                    {
                        "id": "case-1",
                        "expectedAnswer": "정답",
                        "predictedAnswer": " ",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
