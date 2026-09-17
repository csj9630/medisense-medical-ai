"""risk_detector.detect_emergency()의 실제 동작을 라벨링된 문장 집합으로 측정한다.

측정 기준: "의학적으로 정답인가"가 아니라 "이 결정론적 키워드 필터가 의도대로
동작하는가"다 — 정답 라벨은 상식적으로 명백한 응급/비응급 구분(가슴 통증 vs 콧물)이라
LLM이나 의료 자문 없이도 객관적으로 채점 가능하다. GPU/DB 불필요, 로컬에서 즉시 실행.
"""

from ai.consultation.risk_detector import detect_emergency

# (문장, 실제 라벨: True=응급, False=비응급) — 기존 키워드 목록의 각 항목별 변형 표현+
# 키워드 리스트에 없는 응급 신호(재현율 한계 확인용) + 키워드가 우연히 매칭될 수 있는
# 비응급 문장(오탐 확인용)을 섞었다.
CASES: list[tuple[str, bool]] = [
    # --- 응급: 키워드 목록에 있는 카테고리의 자연스러운 변형 ---
    ("숨쉬기가 너무 힘들어요", True),
    ("갑자기 숨이 안 쉬어져요", True),
    ("계단만 올라가도 숨차서 죽을 것 같아요", True),
    ("호흡곤란이 심해서 응급실에 가야 할 것 같아요", True),
    ("가슴이 답답하고 통증이 있어요", True),
    ("가슴을 쥐어짜는 듯한 느낌이 들어요", True),
    ("갑자기 흉통이 생겼어요", True),
    ("정신을 잃고 그 자리에서 쓰러졌어요", True),
    ("갑자기 의식이 흐려졌어요", True),
    ("어지럽더니 실신했어요", True),
    ("피를 토했어요", True),
    ("기침을 하다가 각혈을 했어요", True),
    ("상처에서 심한 출혈이 멈추지 않아요", True),
    ("갑자기 온몸에 경련이 일어났어요", True),
    ("발작을 일으켜서 놀랐어요", True),
    ("한쪽 팔다리에 마비가 왔어요", True),
    ("얼굴이 마비된 것처럼 안 움직여요", True),
    ("말이 어눌해지고 발음이 이상해요", True),
    # --- 응급이지만 키워드 목록에 없어서 놓칠 것으로 예상되는 표현 (재현율 한계) ---
    ("망치로 맞은 것처럼 머리가 갑자기 심하게 아파요", True),  # 뇌졸중/뇌출혈 red flag(두통)
    ("입술이 붓고 두드러기가 나면서 숨쉬기가 이상해요", True),  # 아나필락시스
    ("갑자기 시야가 반쪽만 안 보여요", True),  # 뇌졸중 시야 이상
    ("아이가 고열에 축 처지고 반응이 없어요", True),  # 소아 응급
    ("살고 싶지 않다는 생각이 계속 들어요", True),  # 자해/자살 위험
    # --- 비응급: 평범한 증상 ---
    ("어제부터 콧물이 나요", False),
    ("무릎이 좀 아파요", False),
    ("가벼운 두통이 있어요", False),
    ("소화가 잘 안 돼요", False),
    ("허리 디스크 수술 후 다리가 저려요", False),
    ("생리통이 심해요", False),
    ("3일 전에 넘어져서 발목을 삐었어요", False),
    ("속이 울렁거리고 어지러워요", False),
    ("피부가 가렵고 발진이 조금 있어요", False),
    ("잠을 잘 못 자서 피곤해요", False),
    # --- 비응급인데 키워드가 우연히 부분 매칭될 수 있는 표현 (오탐 확인용) ---
    ("예전에 아버지가 심장마비로 돌아가셨어요, 저도 걱정돼요", False),  # "마비" 부분 매칭
    ("운동을 격하게 했더니 숨차네요", False),  # "숨차" 부분 매칭이지만 정상 운동 반응
    ("영화를 보다가 너무 무서워서 숨이 막히는 줄 알았어요", False),  # 비유적 표현
]


def main() -> None:
    true_emergency = [c for c in CASES if c[1] is True]
    true_normal = [c for c in CASES if c[1] is False]

    tp = sum(1 for text, _ in true_emergency if detect_emergency(text))
    fn_cases = [text for text, _ in true_emergency if not detect_emergency(text)]
    fp_cases = [text for text, _ in true_normal if detect_emergency(text)]
    tn = len(true_normal) - len(fp_cases)

    recall = tp / len(true_emergency) if true_emergency else float("nan")
    fpr = len(fp_cases) / len(true_normal) if true_normal else float("nan")

    print(f"총 문항: {len(CASES)}개 (응급 {len(true_emergency)} / 비응급 {len(true_normal)})")
    print(f"응급 인지율(Recall): {tp}/{len(true_emergency)} = {recall:.1%}")
    print(f"오탐률(False Positive Rate): {len(fp_cases)}/{len(true_normal)} = {fpr:.1%}")
    print()
    print("[놓친 응급 문장 — 키워드 목록에 없는 표현]")
    for text in fn_cases:
        print(f"  - {text}")
    print()
    print("[오탐된 비응급 문장 — 키워드가 의도와 다르게 매칭됨]")
    for text in fp_cases:
        print(f"  - {text}")


if __name__ == "__main__":
    main()
