"""
로컬 전용 로그 설정. (CLAUDE.md 로그 규칙: 함수 실패 시 함수명+시각+에러내용을
최소 필드로, 각자 로컬 파일/DB에 남긴다 — 공유 저장소엔 안 올림)

logs/ 폴더는 .gitignore에 걸려 있어 커밋되지 않는다. 각 모듈에서는
`from app.core.logging import get_logger` 후 `logger = get_logger(__name__)`로 쓰면 된다.
"""
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

_configured = False


def _configure_once() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger("app")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    _configure_once()
    return logging.getLogger(f"app.{name}")
