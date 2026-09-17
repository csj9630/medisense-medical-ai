"""데이터셋별 어댑터의 공통 인터페이스. 새 데이터셋을 추가할 때 이 클래스만
상속하면 되고, pipeline.py/CLI/backend 쪽은 구체 어댑터를 몰라도 된다.
"""
from abc import ABC, abstractmethod
from collections.abc import Iterator
from itertools import islice
from typing import Any

from ..schema import NormalizedRecord


class DatasetAdapter(ABC):
    source: str
    source_type: str
    hf_path: str
    hf_config: str | None = None
    hf_split: str = "train"

    def __init__(self) -> None:
        # 어댑터별 품질 필터가 무엇을 했는지 집계하는 선택적 카운터 - 행을
        # 통째로 걸렀으면("rejected_...") to_normalized()가 None을 반환하기 전에,
        # 내용 일부만 고쳤으면("stripped_...") 고친 뒤에 `self._record(key)`를
        # 부른다(komed_instruct.py 참고). pipeline.py가 실행 끝에 이걸 읽어서
        # IngestionPipelineResult.filter_stats에 담아 보고서에 낸다. 아무 필터도
        # 없는 어댑터는 그냥 빈 dict로 남는다(무해).
        self.filter_stats: dict[str, int] = {}

    def _record(self, key: str) -> None:
        self.filter_stats[key] = self.filter_stats.get(key, 0) + 1

    def load_raw(
        self, limit: int | None = None, *, shuffle_seed: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """streaming=True로 연다 - dry-run이나 소량 샘플에서 데이터셋 전체를 내려받지
        않기 위함. limit이 있으면 그만큼만 스트리밍해서 읽는다.

        shuffle_seed: limit과 같이 쓰면 "앞에서부터 N개"가 아니라 전체 스트림에서
        고르게 뽑은 N개가 된다 - 원본 순서가 우연히 주제/카테고리별로 묶여 있으면
        앞부분만 잘랐을 때 특정 분야가 과도하게 들어갈 수 있어서(실제로 이런 편향이
        있는지는 데이터셋마다 다르므로, 필요하다고 판단되면 호출부가 켠다).
        스트리밍 데이터셋이라 완전한 셔플은 아니고 buffer_size만큼의 지역적
        셔플이다(datasets 라이브러리의 표준 방식) - 매번 같은 seed를 쓰면 재실행해도
        idempotency에 필요한 동일 샘플이 재현된다."""
        from datasets import load_dataset

        ds = load_dataset(self.hf_path, self.hf_config, split=self.hf_split, streaming=True)
        if shuffle_seed is not None:
            ds = ds.shuffle(seed=shuffle_seed, buffer_size=10_000)
        return iter(islice(ds, limit)) if limit is not None else iter(ds)

    @abstractmethod
    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        """스키마가 안 맞거나 필수 내용이 비어있으면 예외 대신 None을 반환해서 그
        행만 건너뛴다 - 데이터셋 전체 처리를 멈추지 않는다.

        index: load_raw()가 내놓은 순서(0부터). 원본에 진짜 id 필드가 있으면 그걸
        우선 쓰고(question_id, idx 등), 없는 데이터셋(Asan-AMC-Healthinfo,
        GenMedGPT-5k-ko)은 이 index로 original_id를 만든다 - 모든 어댑터가 항상
        안정적인 original_id를 갖도록 보장하기 위함(idempotency 키의 일부)."""
        raise NotImplementedError


class GatedDatasetAdapter(DatasetAdapter):
    """접근 권한이 없는(gated) 데이터셋을 위한 자리 표시자. load_raw를 호출하면
    바로 명확한 에러를 낸다 - 그냥 조용히 빈 결과를 내는 것보다, 다른 어댑터들과
    나란히 CLI에서 --source로 골랐을 때 "왜 아무 것도 안 나오지"로 헷갈리지
    않도록 명시적으로 알린다."""

    reason: str = "접근 권한이 없는 데이터셋입니다."

    def load_raw(
        self, limit: int | None = None, *, shuffle_seed: int | None = None
    ) -> Iterator[dict[str, Any]]:
        raise PermissionError(f"{self.hf_path}: {self.reason}")

    def to_normalized(self, raw_row: dict[str, Any], index: int) -> NormalizedRecord | None:
        raise PermissionError(f"{self.hf_path}: {self.reason}")
