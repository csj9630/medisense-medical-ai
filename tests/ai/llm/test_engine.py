"""base model 다운로드/추론 없이 캐싱·GPU 가드 로직만 검증한다. 실제 로드가 필요한
테스트는 GPU 없는 CI/로컬에서 돌릴 수 없어 루트 CLAUDE.md 규칙대로 여기 포함하지
않는다(smoke test로 별도 분리 대상)."""

import unittest

from ai.llm.engine import LoraAdapterEngine, get_lora_engine


class GetLoraEngineTest(unittest.TestCase):
    def test_same_base_model_id_returns_same_instance(self) -> None:
        first = get_lora_engine("some/base-model")
        second = get_lora_engine("some/base-model")
        self.assertIs(first, second)

    def test_different_base_model_id_returns_different_instance(self) -> None:
        engine_a = get_lora_engine("family-a/base")
        engine_b = get_lora_engine("family-b/base")
        self.assertIsNot(engine_a, engine_b)


class LoraAdapterEngineGuardTest(unittest.TestCase):
    def test_generate_raises_before_touching_gpu_only_apis_when_torch_missing(self) -> None:
        # torch/transformers가 없는 환경(이 프로젝트의 기본 개발 환경)에서는 ImportError를
        # 감싼 명확한 RuntimeError로 실패해야 한다 — 조용히 죽거나 이상한 스택트레이스를
        # 남기지 않는다. (이 프로젝트는 peft/bitsandbytes/accelerate가 선택 의존성이라
        # torch 자체도 없을 수 있음.)
        engine = LoraAdapterEngine("some/base-model")
        try:
            import torch  # noqa: F401

            self.skipTest("이 환경엔 torch가 설치돼 있어 ImportError 경로를 검증할 수 없음")
        except ImportError:
            pass

        with self.assertRaises(RuntimeError):
            engine.generate("adapter-a", "some/adapter-repo", [{"role": "user", "content": "안녕"}])

    def test_is_base_loaded_false_before_first_generate(self) -> None:
        engine = LoraAdapterEngine("some/base-model")
        self.assertFalse(engine.is_base_loaded())
        self.assertEqual(engine.loaded_adapter_ids(), set())


if __name__ == "__main__":
    unittest.main()
