"""회귀 방지 테스트 - backend/app(실제 요청을 처리하는 런타임 코드) 전체에
사용자 입력이 SQL 문자열에 직접 섞여 들어갈 수 있는 패턴이 없는지 정적으로
검사한다.

**지금은 실제로 위반이 0건이다**(전부 SQLAlchemy ORM의 select()/.where() 파라미터
바인딩만 씀, backend/app/main.py의 text('SELECT 1')이 유일한 raw SQL이고 이건
고정 문자열이라 안전함, 2026-09-03 확인). 이 테스트의 목적은 새 취약점을 찾는 게
아니라, **앞으로 이 상태가 깨지지 않게 지키는 것**이다 - f-string이나 문자열
결합으로 SQL을 만드는 코드가 새로 추가되면 여기서 바로 걸린다.

**검사 범위를 backend/app으로만 좁힌 이유**: backend/migrations/의 마이그레이션
파일들은 개발자가 직접 실행하는 스키마 변경 스크립트라, f-string으로 상수(예:
벡터 컬럼 폭 숫자)를 SQL에 넣는 게 정상이고 사용자 입력과 무관하다 - 여기까지
검사하면 안전한 코드를 오탐으로 걸러내게 된다.
"""
import re
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# text(f"...") / text(f'...') / .execute(f"...") 처럼 SQL을 만드는 함수에
# f-string을 직접 넘기는 패턴 - 문자열 안의 {변수}가 사용자 입력이면 그대로
# SQL 인젝션이 된다. 여러 줄 f-string(""" 로 시작)도 잡는다.
_FSTRING_SQL_PATTERN = re.compile(r'(?:text|execute)\(\s*f["\']')

# text("..." + 뭔가) / text("..." % 뭔가) 처럼 문자열 결합/포맷으로 SQL을 만드는
# 패턴 - f-string은 아니지만 위와 같은 위험이 있다.
_CONCAT_SQL_PATTERN = re.compile(r'(?:text|execute)\(\s*["\'][^"\']*["\']\s*[%+]')


class NoRawSqlInjectionRiskTest(unittest.TestCase):
    def test_no_fstring_or_concatenated_sql_in_app_code(self) -> None:
        violations: list[str] = []
        for path in APP_DIR.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for pattern in (_FSTRING_SQL_PATTERN, _CONCAT_SQL_PATTERN):
                for match in pattern.finditer(content):
                    line_no = content.count("\n", 0, match.start()) + 1
                    violations.append(f"{path.relative_to(APP_DIR.parent)}:{line_no}: {match.group(0)!r}")

        self.assertEqual(
            violations,
            [],
            "backend/app에 사용자 입력이 섞일 수 있는 SQL 문자열 조합이 발견됐습니다 - "
            "SQLAlchemy의 select()/.where() 파라미터 바인딩을 쓰세요 (필요하면 "
            "text('...').bindparams(...)로 안전하게 바인딩):\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
