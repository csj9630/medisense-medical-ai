import unittest

from ai.rag.chunking import chunk_text, count_tokens, is_garbage


class ChunkingTest(unittest.TestCase):
    def test_count_tokens_uses_generic_tokenizer(self) -> None:
        self.assertEqual(count_tokens(""), 0)
        self.assertGreater(count_tokens("두통이 계속 있어요"), 0)

    def test_is_garbage_detects_symbol_only_text(self) -> None:
        self.assertTrue(is_garbage("   "))
        self.assertTrue(is_garbage("---***///"))
        self.assertFalse(is_garbage("두통"))

    def test_short_text_becomes_single_chunk(self) -> None:
        chunks = chunk_text("환자는 3일 전부터 두통을 호소하고 있습니다.")
        self.assertEqual(len(chunks), 1)
        self.assertGreater(chunks[0].token_count, 0)

    def test_long_text_is_split_within_token_budget(self) -> None:
        sentence = "환자는 두통과 어지럼증을 호소하고 있습니다. "
        long_text = sentence * 100
        chunks = chunk_text(long_text, max_tokens=50, overlap_tokens=10)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(chunk.token_count, 60)  # overlap 붙어도 살짝 여유

    def test_paragraph_boundary_is_never_merged_across(self) -> None:
        text = "첫 번째 단락 내용입니다.\n\n두 번째 단락 내용입니다."
        chunks = chunk_text(text, max_tokens=300, overlap_tokens=0)

        joined = " ".join(c.text for c in chunks)
        self.assertIn("첫 번째", joined)
        self.assertIn("두 번째", joined)

    def test_overlap_never_leaves_a_replacement_character(self) -> None:
        # 실제 관찰된 사례 - overlap이 토큰 경계에서 한글 글자 중간을 자르면
        # "�물 부작용(B)은..." 처럼 대체 문자(U+FFFD)가 청크 맨 앞에 남았다.
        # 여러 실제 문장으로 overlap을 강제로 유발해서 재현한다.
        sentences = [
            "이 환자는 전신 가려움증, 체중 감소, 피로감을 호소하며 검사실 소견에서 담즙정체성 간기능 이상이 관찰됩니다.",
            "이러한 소견은 원발성 담즙성 담관염을 강하게 시사합니다.",
            "약물 부작용은 항고혈압제 등이 원인일 수 있으나, 간기능 이상을 동반한 전신 가려움증은 설명하기 어렵습니다.",
            "만성 신부전은 요독증으로 인한 가려움증을 유발할 수 있으나, 환자의 신기능 검사는 정상입니다.",
            "건조피부증은 노인에서 흔한 가려움증의 원인이지만, 이 환자의 간기능 이상과 전신 증상을 설명할 수 없습니다.",
        ]
        text = " ".join(sentences * 4)  # 여러 청크로 나뉘도록 충분히 길게
        chunks = chunk_text(text, max_tokens=80, overlap_tokens=30)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertNotIn("�", chunk.text)

    def test_force_split_never_leaves_a_replacement_character(self) -> None:
        # 문장부호 없는 한글 덩어리(표/양식 OCR 텍스트 흉내)로 _force_split_by_tokens
        # 경로를 강제로 태운다.
        no_punctuation_korean = "간기능수치상승담즙정체성황달원발성담즙성담관염자가면역성간질환중년여성호발" * 30
        chunks = chunk_text(no_punctuation_korean, max_tokens=40, overlap_tokens=15)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertNotIn("�", chunk.text)

    def test_garbage_only_input_returns_no_chunks(self) -> None:
        self.assertEqual(chunk_text("   ...---   "), [])


if __name__ == "__main__":
    unittest.main()
