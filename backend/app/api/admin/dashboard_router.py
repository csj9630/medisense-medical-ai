"""관리자 대시보드 지표 API. 다른 /api/admin/* 엔드포인트와 달리 여기는 신규
엔드포인트라 `require_admin` 의존성을 처음부터 붙였다 — 확인해보니 기존
/api/admin/* 엔드포인트들은 서버 쪽 인증 검사가 전혀 없고(프론트 라우트
가드로만 막혀있음, 토큰 없이 curl로 바로 호출 가능한 상태) 별도로 고쳐야
할 기존 이슈다."""
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth.dependencies import require_admin
from app.core.database import get_db
from app.models.generated import Users
from app.schemas.dashboard import DashboardOverviewResponse
from app.services import dashboard_service

router = APIRouter()


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    current_user: Annotated[Users, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: int = 14,
) -> DashboardOverviewResponse:
    """KPI + 최근 `days`일 추이/모델별 통계/사용자 사용량 분포를 한 번에 반환한다.
    consultation_logs가 아직 안 쌓였으면(막 배포한 직후 등) 전부 0/빈 배열로
    나온다 — 에러가 아니라 정상적인 빈 상태다."""
    del current_user  # 인증/인가 목적으로만 주입, 값 자체는 안 씀
    days = max(1, min(days, 90))
    overview = dashboard_service.get_overview(db, days=days)
    # dashboard_service는 순수 dataclass만 반환한다(backend/app 밖에서도 재사용 가능하게) —
    # 여기서 Pydantic 응답 스키마로 변환한다. populate_by_name=True라 snake_case
    # dict 키 그대로 넘기면 camelCase alias 필드에 채워진다.
    return DashboardOverviewResponse.model_validate(asdict(overview))
