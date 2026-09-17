import unittest

from ai.consultation.response_validator import extract_mentioned_department, validate


class ValidateTest(unittest.TestCase):
    def test_leaves_safe_answer_unchanged(self) -> None:
        answer = "충분한 휴식과 수분 섭취가 도움이 될 수 있습니다."
        self.assertEqual(validate(answer), answer)

    def test_returns_empty_string_for_non_answer_meta_instructions(self) -> None:
        # 실제 관찰된 사례(2026-09, 라이브 테스트) - 의료 답변 없이 모델 스스로에게
        # 주는 것 같은 메타 지시문만 출력했다. 잘라낼 정상 앞부분이 없으므로
        # 빈 문자열을 반환해서 pipeline.py가 FALLBACK_ANSWER로 대체하게 한다.
        answer = (
            "안녕하세요! 답변 완료 후에는 새로운 프롬프트와 함께 다시 시작하십시오. "
            "감사합니다! (아무것도 없으므로 그냥 넘어갈게요.) 입니다."
        )
        self.assertEqual(validate(answer), "")

    def test_appends_warning_for_mg_dosage(self) -> None:
        answer = "타이레놀 500mg을 복용하세요."
        result = validate(answer)
        self.assertIn(answer, result)
        self.assertIn("[안전 안내]", result)

    def test_appends_warning_for_tablet_count(self) -> None:
        result = validate("하루 3정씩 드세요.")
        self.assertIn("[안전 안내]", result)

    def test_does_not_false_positive_on_unrelated_text(self) -> None:
        answer = "정확한 진단을 위해 의료진과 상담하는 것이 좋습니다."
        self.assertEqual(validate(answer), answer)

    def test_strips_trailing_repeated_short_tokens(self) -> None:
        # 일부 원격 모델이 정상 답변 뒤에 종료 토큰 처리를 잘못해서 같은 줄을
        # 반복하는 현상이 관찰됐다 — 답변 본문은 지키고 반복 꼬리만 잘라야 한다.
        good_answer = "충분한 휴식과 수분 섭취가 도움이 될 수 있습니다."
        noisy = good_answer + "\n" + "\n".join(["[]"] * 6)
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_trailing_repeated_lines_with_blank_lines_between(self) -> None:
        good_answer = "가능하다면 내과에서 진료를 받아보시는 것을 추천드립니다."
        noisy = good_answer + "\n\ndisplay comment\n\n\n\ndisplay comment\n\ndisplay comment"
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_trailing_repeated_two_line_pattern(self) -> None:
        # 실제로 관찰된 사례: "caution/indicator" 두 줄이 번갈아 반복.
        good_answer = "내과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        noisy = good_answer + "\n" + "\n".join(
            ["caution: 이 정보는 일반적인 내용입니다.", "indicator: medical"] * 3
        )
        self.assertEqual(validate(noisy), good_answer)

    def test_does_not_strip_below_minimum_repeat_threshold(self) -> None:
        # 반복이 2번뿐이면(우연의 일치일 수 있음) 그대로 둔다 — 오탐으로 실제 내용을
        # 지우면 안 되기 때문.
        answer = "괜찮습니다.\n괜찮습니다."
        self.assertEqual(validate(answer), answer)

    def test_strips_special_tokens_even_when_not_repeated(self) -> None:
        good_answer = "내과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        self.assertEqual(validate(good_answer + "</s></s>"), good_answer)

    def test_strips_self_generated_disclaimer_paragraph(self) -> None:
        # 실제 관찰된 사례 — 면책 문구는 프론트엔드 배너가 담당하는데, 모델이 자기
        # 나름의 면책 문구를 답변 끝에 또 붙였다.
        good_answer = "내과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        noisy = (
            good_answer
            + "\n\n**면책 조항:** 저는 의료 전문가가 아니므로, 이 정보는 의료적인 조언으로 해석될 수 없습니다."
        )
        self.assertEqual(validate(noisy), good_answer)

    def test_does_not_strip_paragraph_without_disclaimer_signal(self) -> None:
        answer = "충분한 휴식을 취하세요.\n\n증상이 지속되면 병원을 방문하세요."
        self.assertEqual(validate(answer), answer)

    def test_strips_bold_markers_but_keeps_text(self) -> None:
        # 실제 관찰된 사례 — 진료과 이름을 굵게 강조("**이비인후과**에서...").
        result = validate("**이비인후과**에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")
        self.assertEqual(result, "이비인후과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")

    def test_strips_bullet_list_markers_but_keeps_lines(self) -> None:
        # 실제 관찰된 사례 — 자가관리 방법을 "*   " 마크다운 목록으로 냈다.
        noisy = "다음 사항에 유의하세요.\n*   충분한 수분을 섭취하세요.\n*   카페인 섭취를 줄이세요."
        result = validate(noisy)
        self.assertNotIn("*", result)
        self.assertIn("충분한 수분을 섭취하세요.", result)
        self.assertIn("카페인 섭취를 줄이세요.", result)

    def test_strips_bold_labels_inside_bullet_items(self) -> None:
        # 실제 관찰된 사례 — 목록 항목 안에 굵게 표시된 소제목까지 섞였다.
        noisy = "*   **탈수:** 충분한 수분 섭취 부족으로 인해 나타날 수 있습니다."
        result = validate(noisy)
        self.assertEqual(result, "탈수: 충분한 수분 섭취 부족으로 인해 나타날 수 있습니다.")

    def test_does_not_touch_multiplication_asterisk_in_normal_sentence(self) -> None:
        # 일반 문장에 별표가 하나만 있으면(짝이 없으면) 그대로 둔다 — 오탐 방지.
        answer = "3 * 2 = 6 같은 계산은 이 답변과 무관합니다."
        self.assertEqual(validate(answer), answer)

    def test_strips_trailing_json_block(self) -> None:
        # 실제 관찰된 사례 — 정상 답변 뒤에 반복 없이 JSON 조각을 한 번 덧붙였다.
        good_answer = "머리가 계속 지끈거리거나 어지럼증이 심해지면 반드시 병원에 방문하시기 바랍니다."
        noisy = good_answer + '\n라벨: 0.8\n\n{\n"진료과": "내과",\n"경고": "즉시 병원 방문이 필요합니다."\n}'
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_trailing_label_line(self) -> None:
        good_answer = "이비인후과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        noisy = good_answer + "\nDisplayName: MediSense Medical Assistant Chatbot"
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_trailing_russian_language_leak(self) -> None:
        # 실제 관찰된 사례 - 정상 한국어 답변 뒤에 모델이 러시아어 문장을 이어 붙였다.
        good_answer = (
            "만약 통증이 계속되거나 악화된다면 병원 방문을 고려해보시는 것이 좋습니다. "
            "특히 통증이 심하거나 다른 증상(붓기, 열감 등)이 동반된다면 더욱 그렇습니다."
        )
        noisy = (
            good_answer
            + "\n\nЕщё неясно.\nМожете помочь мне с этим?\n"
            "Давайте начнем с того, что вы спросили меня о симптомах и причинах боли в пальцах рук."
        )
        self.assertEqual(validate(noisy), good_answer)

    def test_does_not_strip_korean_answer_with_english_medical_terms(self) -> None:
        # 영문 약어/단위(MRI, CT, mg 등)가 섞여도 정상 문장은 안 지워야 한다 - 오탐 방지.
        answer = "MRI나 CT 검사를 통해 정확한 원인을 확인하는 것이 좋습니다."
        self.assertEqual(validate(answer), answer)

    def test_english_question_allows_full_english_answer(self) -> None:
        # "사용자가 입력한 언어로 답변" 정책 - 사용자가 영어로 물으면 답변 전체가
        # 영어여도 "외국어 유출"로 오탐하면 안 된다.
        answer = "Sufficient rest and hydration may help relieve your symptoms."
        result = validate(answer, user_question="What should I do for a headache?")
        self.assertEqual(result, answer)

    def test_english_question_still_catches_korean_language_leak(self) -> None:
        # 반대 방향 - 사용자가 영어로 물었는데 답변 끝에 한국어가 새면(디코더 붕괴)
        # 여전히 잡아야 한다. 허용 문자를 무조건 넓히면 이 보호가 사라진다.
        good_answer = "Sufficient rest and hydration may help relieve your symptoms."
        noisy = good_answer + "\n\n이건 관련 없는 한국어 문장이 갑자기 섞인 경우입니다."
        result = validate(noisy, user_question="What should I do for a headache?")
        self.assertEqual(result, good_answer)

    def test_japanese_question_allows_japanese_answer_with_kanji(self) -> None:
        # 일본어는 가나+한자를 섞어 쓰므로 둘 다 허용해야 한다.
        answer = "十分な休息と水分補給が症状の緩和に役立つ場合があります。"
        result = validate(answer, user_question="頭痛がひどいです。どうすればいいですか？")
        self.assertEqual(result, answer)

    def test_chinese_question_allows_chinese_answer(self) -> None:
        answer = "充分的休息和补水可能有助于缓解症状。"
        result = validate(answer, user_question="我头疼得厉害，应该怎么办？")
        self.assertEqual(result, answer)

    def test_empty_user_question_falls_back_to_korean_baseline(self) -> None:
        # user_question을 안 넘기는 기존 호출부(테스트 등)는 그대로 한국어 기준으로
        # 동작해야 한다 - 하위호환.
        answer = "충분한 휴식과 수분 섭취가 도움이 될 수 있습니다."
        self.assertEqual(validate(answer), answer)

    def test_unwraps_trailing_department_mention_wrapped_in_parentheses(self) -> None:
        # 실제 관찰된 사례 - 프롬프트의 진료과 힌트가 괄호로 감싸져 있다 보니, 모델이
        # 그 스타일을 그대로 따라 해서 답변 마지막 문장 전체를 괄호로 감쌌다.
        answer = (
            "충분한 휴식을 취하시고 통증이 지속되면 병원을 방문해보세요.\n\n"
            "(정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.)"
        )
        result = validate(answer)
        self.assertNotIn("(", result)
        self.assertNotIn(")", result)
        self.assertIn("정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.", result)

    def test_unwraps_trailing_department_mention_wrapped_in_curly_braces(self) -> None:
        # 실제 관찰된 변형 - 괄호 대신 중괄호로 감싸는 경우도 있었다.
        answer = (
            "충분한 휴식을 취하시고 통증이 지속되면 병원을 방문해보세요.\n\n"
            "{정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.}"
        )
        result = validate(answer)
        self.assertNotIn("{", result)
        self.assertNotIn("}", result)
        self.assertIn("정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.", result)

    def test_strips_trailing_inline_token_repetition_loop(self) -> None:
        # 실제 관찰된 사례 - 정상 답변 뒤에 같은 짧은 조각을 줄바꿈 없이 한 줄 안에서
        # 수십 번 이어붙였다("라벨_end{라벨_end{라벨_end{...").
        good_answer = "만약 통증이 심하거나 일상생활에 불편함을 느낀다면, 빠른 시일 내에 병원을 방문하여 진료를 받으시기 바랍니다."
        noisy = good_answer + "\n\n라벨_end{}\n" + "라벨_end{" * 24
        result = validate(noisy)
        self.assertEqual(result, good_answer)

    def test_strips_unclosed_trailing_code_fence_with_truncated_json(self) -> None:
        # 실제 관찰된 사례 - "라벨```json"으로 시작해서 답변을 JSON으로 다시 요약하다가
        # 토큰 한도에 걸려 중간에 끊겼다(닫는 "```"도, 닫는 중괄호도 없음).
        good_answer = (
            "충분한 휴식을 취하고, 통증이 심할 경우 냉찜질을 해주시면 도움이 될 수 있습니다."
        )
        noisy = (
            good_answer
            + '\n라벨```json\n{\n "응답": "'
            + good_answer
            + '\\n\\n   충'
        )
        result = validate(noisy)
        self.assertEqual(result, good_answer)

    def test_does_not_strip_properly_closed_code_fence_content(self) -> None:
        # 정상적으로 닫힌 코드펜스는 markdown stripper가 처리 대상이라 여기서 안 건드림
        # (내용까지 통째로 지우면 안 됨 - 다른 필터가 처리하는지 확인).
        answer = "설명입니다.\n```\n정상적으로 닫힌 블록\n```\n마지막 문장입니다."
        result = validate(answer)
        self.assertIn("마지막 문장입니다.", result)

    def test_does_not_unwrap_normal_medical_parenthetical_in_the_middle(self) -> None:
        # "고열(38도 이상)"처럼 문장 중간의 정상적인 의학 부연설명 괄호는 안 건드려야 한다.
        answer = "고열(38도 이상)이 지속되면 병원을 방문하세요."
        self.assertEqual(validate(answer), answer)

    def test_does_not_unwrap_trailing_parenthetical_without_department_name(self) -> None:
        # 진료과 이름이 없는 일반적인 마지막 괄호 부연설명은 그대로 둔다 - 오탐 방지.
        answer = "충분히 휴식을 취해보세요. (특히 밤에 잘 주무시는 것이 중요합니다.)"
        self.assertEqual(validate(answer), answer)

    def test_does_not_strip_json_like_text_inside_normal_answer(self) -> None:
        # 답변 본문에 중괄호가 등장해도 유효한 JSON으로 안 끝나면 안 지운다 — 오탐 방지.
        answer = "증상을 설명할 때 {예시}처럼 괄호를 쓰는 경우가 있어요."
        self.assertEqual(validate(answer), answer)

    def test_strips_trailing_hallucinated_dialogue_turn_korean(self) -> None:
        # 팀원 작업지시서가 지적한 실패 모드 - 정상 답변 뒤에 모델이 스스로 새 대화
        # 턴을 만들어낸다.
        good_answer = "충분한 휴식을 취하고 증상이 지속되면 병원을 방문하세요."
        noisy = good_answer + "\n\n환자: 감사합니다.\n의사: 별말씀을요."
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_trailing_hallucinated_dialogue_turn_role_tokens(self) -> None:
        good_answer = "충분한 휴식을 취하고 증상이 지속되면 병원을 방문하세요."
        noisy = good_answer + "\n\nuser: thanks\nassistant: You're welcome."
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_system_prompt_echo_after_normal_answer(self) -> None:
        # 실제 관찰된 사례(2026-09-02, 실 RAG 데이터로 라이브 테스트) - 정상 답변을
        # 마친 뒤 모델이 자신에게 입력된 system prompt 내용을 그대로 이어 붙였다.
        good_answer = (
            "오른쪽 어깨 통증이 있으시고, 회전근개 미세파열일 가능성에 대해 궁금하신 것으로 이해했습니다. "
            "참고용 진료과 정보: 정형외과에서 평가가 필요할 수 있습니다."
        )
        noisy = (
            good_answer
            + "\nDisplayName\n\nExample Response\n"
            "저는 MediSense의 의료 상담 보조 챗봇입니다. 의료진을 대체하지 않으며, "
            "증상만으로 특정 질환을 확정 진단하지 않습니다.\n\n절대 규칙\n"
            "특정 질환을 확정 진단하거나 특정 치료·검사·수술의 필요성을 단정하지 마세요."
        )
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_self_repeated_answer_with_garbage_and_truncated_tail(self) -> None:
        # 실제 관찰된 사례 - 첫 문단을 낸 뒤 그 문단을 "모델 답변:" 라벨과 함께,
        # 사이에 아랍어 가비지까지 섞어가며 여러 번 반복했고, max_output_tokens에
        # 걸려 마지막 반복은 중간에 잘렸다(이전 반복들과 글자 수가 다름) - 끝에서부터
        # "완전히 같은 줄"만 찾는 기존 필터로는 못 잡는 패턴.
        good_answer = (
            "손가락이 갑자기 쿵쾅쿵쾅 아프다고 말씀하셨네요. 어떤 종류의 통증인가요? "
            "(예: 찌르는 듯한 통증, 욱신거리는 통증 등) 그리고 통증이 발생하는 손가락은 어디인가요?"
        )
        noisy = (
            good_answer
            + "\n المختص هـنأ\n"
            + good_answer
            + "\n\n\n모델 답변:\n\n"
            + good_answer
            + "\n\n모델 답변:\n\n"
            + good_answer[:30]  # max_output_tokens에 걸려 잘린 마지막 반복
        )
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_leading_label_glued_to_normal_sentence(self) -> None:
        # 실제 관찰된 사례 - "Display comment " 같은 라벨이 정상 문장 맨 앞에
        # 그대로 들러붙어 나왔다. 문장 자체(뒷부분)는 살리고 라벨만 제거해야 한다.
        answer = "Display comment 정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        self.assertEqual(validate(answer), "정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")

    def test_does_not_strip_legitimate_medical_abbreviation_prefix(self) -> None:
        # "Display comment" 같은 라벨만 정확히 지워야지, "MRI 검사를"처럼 정당한
        # 의학 약어가 문장 맨 앞에 오는 경우까지 건드리면 안 된다 - 오탐 방지.
        answer = "MRI 검사를 통해 정확한 원인을 확인하는 것이 좋습니다."
        self.assertEqual(validate(answer), answer)

    def test_strips_short_orphan_latin_word_after_complete_sentence(self) -> None:
        # 실제 관찰된 사례 - 완결된 문장 뒤에 뜬금없는 라틴 문자 단어 하나가
        # 새 줄로 덧붙었다("...고려해볼 수 있습니다.\n Hakim"). 의학 약어 허용
        # 때문에 기존 외국어 유출 필터는 라틴 문자를 무조건 통과시켜서 못 잡는다.
        good_answer = "정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        noisy = good_answer + "\n Hakim"
        self.assertEqual(validate(noisy), good_answer)

    def test_does_not_strip_legitimate_short_korean_closing_line(self) -> None:
        # 짧고 한국어 종결어미로 끝나는 정상적인 마지막 줄(감사 인사 등)은 지우면
        # 안 된다 - 오탐 방지.
        answer = "궁금하신 점이 있으면 언제든 다시 문의해주세요.\n감사합니다."
        self.assertEqual(validate(answer), answer)

    def test_does_not_strip_orphan_tail_when_previous_line_is_incomplete(self) -> None:
        # 바로 앞 문장이 마침표로 끝나지 않았다면(문장이 원래 진행 중이었을
        # 수도 있으므로) 손대지 않는다 - 오탐 방지.
        answer = "확인이 필요한 부분이 있습니다\nMRI"
        self.assertEqual(validate(answer), answer)

    def test_strips_short_orphan_korean_word_unrelated_to_context(self) -> None:
        # 실제 관찰된 사례 - 완결된 문장 뒤에 맥락과 무관한 한국어 단어 하나가
        # 새 줄로 붙었다("...등)\n견적" - "견적"은 종결어미로 안 끝나는 명사 조각).
        good_answer = (
            "손가락이 갑자기 쿵쾅쿵쾅 하는 듯한 통증이 있다고 말씀하셨습니다. 어떤 종류의 통증인가요? "
            "(예: 찌르는 듯한 통증, 쑤시는 듯한 통증 등)"
        )
        noisy = good_answer + "\n견적"
        self.assertEqual(validate(noisy), good_answer)

    def test_strips_department_hint_label_wrapped_and_glued_to_sentence(self) -> None:
        # 실제 관찰된 사례 - 진료과 힌트 라벨 자체("참고용 진료과 정보")를 중괄호로
        # 감싸서 문장 맨 앞에 붙였다("{참고용 진료과 정보} 정형외과에서...").
        answer = "{참고용 진료과 정보} 정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        self.assertEqual(validate(answer), "정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다.")

    def test_does_not_strip_multi_paragraph_answer_without_any_repeat(self) -> None:
        # 여러 문단으로 된 정상 답변인데 서로 겹치는 문단이 하나도 없으면 그대로
        # 둬야 한다 - 오탐 방지(회전근개 실사용 테스트의 정상 부분과 같은 구조).
        answer = (
            "오른쪽 어깨 통증이 있으시고, 회전근개 미세파열일 가능성에 대해 궁금하신 것으로 이해했습니다.\n\n"
            "회전근개 미세파열은 어깨를 돌리는 데 사용하는 근육에 작은 손상이 생긴 것을 말합니다.\n\n"
            "하지만 다른 가능성도 있어 정확한 진단을 위해 병원을 방문하시는 것이 좋습니다."
        )
        self.assertEqual(validate(answer), answer)

    def test_does_not_strip_normal_sentence_starting_with_role_like_word(self) -> None:
        # "의사소통"처럼 역할 이름으로 시작하지만 콜론이 없는 정상 단어/문장은
        # 지우면 안 된다 - 오탐 방지.
        answer = "의사소통이 원활하면 진료에 도움이 됩니다."
        self.assertEqual(validate(answer), answer)


class ExtractMentionedDepartmentTest(unittest.TestCase):
    def test_returns_the_single_department_mentioned(self) -> None:
        answer = "정형외과에서 진료를 받아보시는 것도 고려해볼 수 있습니다."
        self.assertEqual(extract_mentioned_department(answer), "정형외과")

    def test_returns_none_when_no_department_is_mentioned(self) -> None:
        answer = "충분히 휴식을 취하시고 증상이 지속되면 병원을 방문해보세요."
        self.assertIsNone(extract_mentioned_department(answer))

    def test_returns_none_when_multiple_different_departments_are_mentioned(self) -> None:
        # 실제 관찰된 사례 - 모델이 헷갈려서 서로 무관한 진료과를 여러 개 나열했다.
        # 잘못된 확신보다 미분류가 나으므로 None을 반환한다.
        answer = "신경과 진료센터를 추천드립니다. 비뇨의학과에서도 관련 검사가 필요합니다."
        self.assertIsNone(extract_mentioned_department(answer))

    def test_repeated_mention_of_the_same_department_still_counts_as_one(self) -> None:
        answer = "정형외과에서 진료를 받아보세요. 정형외과는 근골격계를 전문적으로 봅니다."
        self.assertEqual(extract_mentioned_department(answer), "정형외과")


if __name__ == "__main__":
    unittest.main()
