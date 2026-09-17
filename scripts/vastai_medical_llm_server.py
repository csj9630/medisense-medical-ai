"""Vast.ai 2× Tesla V100용 5개 의료 LLM FastAPI 서버.

모델 파일은 Notebook이 프로젝트의 ``models/`` 아래에 먼저 내려받습니다.
작은 모델 하나를 두 GPU로 분할하지 않고, 모델 단위로 GPU에 배치해 PCIe 통신을
피하면서 서로 다른 GPU의 요청 두 개를 동시에 처리합니다. V100에서 FP16 logits가
불안정한 MedGemma만 FP32로 실행합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from fastapi import FastAPI, Header, HTTPException
from peft import PeftModel
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


logger = logging.getLogger("vastai-medical-llm")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "").strip()
MODEL_ROOT = Path(os.environ.get("MODEL_ROOT", Path.cwd() / "models")).resolve()
MODEL_PRECISION = os.environ.get("MODEL_PRECISION", "fp16").strip().lower()
MAX_INPUT_TOKENS = max(256, int(os.environ.get("MAX_INPUT_TOKENS", "4096")))

if not MODEL_API_KEY:
    raise RuntimeError("MODEL_API_KEY 환경변수가 비어 있습니다.")
if MODEL_PRECISION not in {"fp16", "4bit"}:
    raise RuntimeError("MODEL_PRECISION은 fp16 또는 4bit여야 합니다.")
if not torch.cuda.is_available():
    raise RuntimeError("CUDA GPU를 찾지 못했습니다.")
if torch.cuda.device_count() < 2:
    raise RuntimeError("이 서버 구성은 CUDA GPU 2개가 필요합니다.")


ADAPTER_DIRS = {
    "gemma": MODEL_ROOT / "adapters" / "gemma",
    "medgemma-final": MODEL_ROOT / "adapters" / "medgemma-final",
    "medgemma-dataset": MODEL_ROOT / "adapters" / "medgemma-dataset",
    "qwen": MODEL_ROOT / "adapters" / "qwen",
    "llama": MODEL_ROOT / "adapters" / "llama",
}
BASE_DIRS = {
    "gemma": MODEL_ROOT / "base" / "gemma",
    "medgemma": MODEL_ROOT / "base" / "medgemma",
    "qwen": MODEL_ROOT / "base" / "qwen",
    "llama": MODEL_ROOT / "base" / "llama",
}


@dataclass(frozen=True)
class LoadedModel:
    model: PeftModel
    tokenizer: object
    gpu_index: int
    adapter_name: str | None = None
    fold_system_message: bool = False
    disable_thinking: bool = False


def _require_model_directories() -> None:
    missing = [
        str(path)
        for path in (*ADAPTER_DIRS.values(), *BASE_DIRS.values())
        if not (path / "config.json").exists()
        and not (path / "adapter_config.json").exists()
    ]
    if missing:
        raise RuntimeError(
            "모델 파일이 없습니다. Notebook의 다운로드 셀을 먼저 실행하세요: "
            + ", ".join(missing)
        )


def _model_load_kwargs(
    gpu_index: int,
    *,
    dtype: torch.dtype = torch.float16,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "device_map": {"": gpu_index},
        "torch_dtype": dtype,
        "low_cpu_mem_usage": True,
        "local_files_only": True,
    }
    if MODEL_PRECISION == "4bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
    return kwargs


def _load_tokenizer(adapter_dir: Path, base_dir: Path):
    # 일부 학습 Adapter의 tokenizer_config.json에는 최신 Transformers가 허용하지
    # 않는 list 형태의 extra_special_tokens가 저장되어 있다. 어휘/Token ID는 Base와
    # 같으므로 Base tokenizer를 사용하고, 학습 시 저장된 채팅 템플릿만 덮어쓴다.
    tokenizer = AutoTokenizer.from_pretrained(
        base_dir,
        local_files_only=True,
        use_fast=True,
    )
    adapter_chat_template = adapter_dir / "chat_template.jinja"
    if adapter_chat_template.exists():
        tokenizer.chat_template = adapter_chat_template.read_text(encoding="utf-8")
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    tokenizer.clean_up_tokenization_spaces = False
    return tokenizer


def _load_single_model(
    *,
    model_id: str,
    base_id: str,
    gpu_index: int,
    fold_system_message: bool = False,
    disable_thinking: bool = False,
) -> LoadedModel:
    print(f"[load] {model_id} -> cuda:{gpu_index} ({MODEL_PRECISION})", flush=True)
    base_dir = BASE_DIRS[base_id]
    adapter_dir = ADAPTER_DIRS[model_id]
    tokenizer = _load_tokenizer(adapter_dir, base_dir)
    base_model = AutoModelForCausalLM.from_pretrained(
        base_dir,
        **_model_load_kwargs(gpu_index),
    )
    model = PeftModel.from_pretrained(
        base_model,
        adapter_dir,
        local_files_only=True,
        is_trainable=False,
    )
    model.eval()
    model.config.use_cache = True
    return LoadedModel(
        model=model,
        tokenizer=tokenizer,
        gpu_index=gpu_index,
        fold_system_message=fold_system_message,
        disable_thinking=disable_thinking,
    )


def _load_medgemma_adapters(gpu_index: int) -> tuple[LoadedModel, LoadedModel]:
    medgemma_dtype = torch.float32 if MODEL_PRECISION == "fp16" else torch.float16
    medgemma_precision = "fp32" if medgemma_dtype == torch.float32 else MODEL_PRECISION
    print(
        f"[load] medgemma-final + medgemma-dataset -> cuda:{gpu_index} "
        f"(shared base, {medgemma_precision})",
        flush=True,
    )
    base_dir = BASE_DIRS["medgemma"]
    final_dir = ADAPTER_DIRS["medgemma-final"]
    dataset_dir = ADAPTER_DIRS["medgemma-dataset"]
    tokenizer = _load_tokenizer(final_dir, base_dir)
    base_model = AutoModelForCausalLM.from_pretrained(
        base_dir,
        **_model_load_kwargs(gpu_index, dtype=medgemma_dtype),
    )
    model = PeftModel.from_pretrained(
        base_model,
        final_dir,
        adapter_name="medgemma-final",
        local_files_only=True,
        is_trainable=False,
    )
    model.load_adapter(
        dataset_dir,
        adapter_name="medgemma-dataset",
        local_files_only=True,
        is_trainable=False,
    )
    model.eval()
    model.config.use_cache = True
    common = {
        "model": model,
        "tokenizer": tokenizer,
        "gpu_index": gpu_index,
        "fold_system_message": True,
    }
    return (
        LoadedModel(**common, adapter_name="medgemma-final"),
        LoadedModel(**common, adapter_name="medgemma-dataset"),
    )


def _load_all_models() -> dict[str, LoadedModel]:
    _require_model_directories()
    # GPU 0: Qwen 4B + Llama 3B + Gemma 2B (FP16).
    # GPU 1: 두 API 모델이 공유하는 MedGemma 4B base (FP32).
    qwen = _load_single_model(
        model_id="qwen",
        base_id="qwen",
        gpu_index=0,
        disable_thinking=True,
    )
    llama = _load_single_model(
        model_id="llama",
        base_id="llama",
        gpu_index=0,
    )
    gemma = _load_single_model(
        model_id="gemma",
        base_id="gemma",
        gpu_index=0,
        fold_system_message=True,
    )
    medgemma_final, medgemma_dataset = _load_medgemma_adapters(gpu_index=1)
    return {
        "gemma": gemma,
        "medgemma-final": medgemma_final,
        "medgemma-dataset": medgemma_dataset,
        "qwen": qwen,
        "llama": llama,
    }


print(
    "GPUs:",
    [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
    flush=True,
)
MODELS = _load_all_models()
GPU_LOCKS = {0: threading.Lock(), 1: threading.Lock()}
app = FastAPI(title="MediSense Vast.ai Medical LLM")


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=30_000)


class GenerateRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1, max_length=50)
    max_output_tokens: int = Field(default=256, ge=1, le=512)


def _authorize(authorization: str | None) -> None:
    expected = f"Bearer {MODEL_API_KEY}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="인증에 실패했습니다.")


@app.get("/health")
def health(authorization: Annotated[str | None, Header()] = None):
    _authorize(authorization)
    return {
        "status": "ok",
        "models": list(MODELS),
        "precision": MODEL_PRECISION,
        "placements": {
            model_id: f"cuda:{loaded.gpu_index}"
            for model_id, loaded in MODELS.items()
        },
    }


def _prepare_messages(request: GenerateRequest, loaded: LoadedModel) -> list[dict[str, str]]:
    messages = [message.model_dump() for message in request.messages]
    if not loaded.fold_system_message:
        return messages

    system_text = "\n\n".join(
        message["content"] for message in messages if message["role"] == "system"
    )
    messages = [message for message in messages if message["role"] != "system"]
    if not system_text:
        return messages

    prefix = f"[시스템 지침]\n{system_text}\n\n[사용자 요청]\n"
    for message in messages:
        if message["role"] == "user":
            message["content"] = prefix + message["content"]
            return messages
    return [{"role": "user", "content": prefix.rstrip()}] + messages


def _render_prompt(loaded: LoadedModel, messages: list[dict[str, str]]) -> str:
    kwargs: dict[str, object] = {
        "tokenize": False,
        "add_generation_prompt": True,
    }
    if loaded.disable_thinking:
        kwargs["enable_thinking"] = False
    return loaded.tokenizer.apply_chat_template(messages, **kwargs)


def _generate_sync(request: GenerateRequest):
    loaded = MODELS.get(request.model)
    if loaded is None:
        raise HTTPException(status_code=404, detail="로드되지 않은 모델입니다.")

    messages = _prepare_messages(request, loaded)
    rendered = _render_prompt(loaded, messages)
    inputs = loaded.tokenizer(
        rendered,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_INPUT_TOKENS,
    ).to(f"cuda:{loaded.gpu_index}")
    input_tokens = inputs["input_ids"].shape[1]

    generation_kwargs: dict[str, object] = {
        "max_new_tokens": request.max_output_tokens,
        "do_sample": True,
        "temperature": 0.7,
        "top_p": 0.9,
        "repetition_penalty": 1.12,
        "use_cache": True,
        "pad_token_id": loaded.tokenizer.pad_token_id,
        "eos_token_id": loaded.tokenizer.eos_token_id,
    }
    if request.model.startswith("medgemma-"):
        # V100은 BF16을 지원하지 않으며 MedGemma의 FP16 sampling logits가 NaN/Inf가
        # 될 수 있다. FP32 로드와 함께 남은 비정상 값을 생성 전에 안전하게 제거한다.
        generation_kwargs.update(
            remove_invalid_values=True,
            renormalize_logits=True,
        )

    with GPU_LOCKS[loaded.gpu_index], torch.inference_mode():
        if loaded.adapter_name is not None:
            loaded.model.set_adapter(loaded.adapter_name)
        output = loaded.model.generate(
            **inputs,
            **generation_kwargs,
        )

    output_tokens = output.shape[1] - input_tokens
    answer = loaded.tokenizer.decode(
        output[0, input_tokens:],
        skip_special_tokens=True,
    ).strip()
    if not answer:
        raise HTTPException(status_code=502, detail="모델이 빈 답변을 반환했습니다.")
    return {
        "answer": answer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "finish_reason": (
            "length" if output_tokens >= request.max_output_tokens else "stop"
        ),
        "gpu": loaded.gpu_index,
    }


@app.post("/v1/generate")
async def generate(
    request: GenerateRequest,
    authorization: Annotated[str | None, Header()] = None,
):
    _authorize(authorization)
    try:
        return await asyncio.to_thread(_generate_sync, request)
    except torch.cuda.OutOfMemoryError as exc:
        for gpu_index in range(torch.cuda.device_count()):
            with torch.cuda.device(gpu_index):
                torch.cuda.empty_cache()
        raise HTTPException(status_code=503, detail="GPU 메모리가 부족합니다.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("모델 생성 실패: model=%s", request.model)
        raise HTTPException(
            status_code=500,
            detail=f"모델 생성 중 내부 오류가 발생했습니다: {request.model}",
        ) from exc
