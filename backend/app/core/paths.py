"""실행 위치와 무관하게 사용하는 프로젝트 공통 경로를 정의합니다."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV_FILE = PROJECT_ROOT / ".env"
BACKEND_ENV_FILE = PROJECT_ROOT / "backend" / ".env"

# 프로젝트 공용 .env를 우선 사용하되, 아직 공용 파일을 만들지 않은 로컬 개발 환경은
# 기존 backend/.env를 그대로 사용할 수 있게 한다.
ENV_FILE = ROOT_ENV_FILE if ROOT_ENV_FILE.exists() else BACKEND_ENV_FILE
