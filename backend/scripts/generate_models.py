from pathlib import Path
from sys import argv, path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402


def main() -> None:
    if settings.database_url.startswith("sqlite"):
        raise SystemExit(".env의 DATABASE_URL을 Neon 연결 문자열로 설정해주세요.")

    output_path = PROJECT_ROOT / "app/models/generated.py"
    # pgvector import가 PostgreSQL의 vector 타입을 SQLAlchemy에 등록합니다.
    from pgvector.sqlalchemy import Vector  # noqa: F401
    from sqlacodegen.cli import main as generate

    argv[:] = [
        "sqlacodegen",
        settings.sqlalchemy_database_url,
        "--generator",
        "declarative",
        "--schemas",
        settings.model_schemas,
        "--outfile",
        str(output_path),
    ]
    generate()
    print(f"모델 생성 완료: {output_path}")


if __name__ == "__main__":
    main()
