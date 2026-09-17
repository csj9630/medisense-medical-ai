"""관리자 대시보드 API가 Frontend와 공유하는 응답 계약입니다."""
from pydantic import Field

from app.schemas.admin import AdminSchema


class DashboardKpisResponse(AdminSchema):
    today_consultations: int = Field(alias="todayConsultations")
    active_users_today: int = Field(alias="activeUsersToday")
    avg_response_time_ms: float | None = Field(alias="avgResponseTimeMs")
    rag_hit_rate: float | None = Field(alias="ragHitRate")
    emergency_count_today: int = Field(alias="emergencyCountToday")
    fallback_rate: float | None = Field(alias="fallbackRate")
    document_count: int = Field(alias="documentCount")
    chunk_count: int = Field(alias="chunkCount")


class DashboardDailyPointResponse(AdminSchema):
    date: str
    count: int


class DashboardModelUsageResponse(AdminSchema):
    model_id: str = Field(alias="modelId")
    total: int
    success: int
    success_rate: float = Field(alias="successRate")


class DashboardUserUsageBucketResponse(AdminSchema):
    label: str
    user_count: int = Field(alias="userCount")


class DashboardOverviewResponse(AdminSchema):
    kpis: DashboardKpisResponse
    daily_consultations: list[DashboardDailyPointResponse] = Field(alias="dailyConsultations")
    emergency_trend: list[DashboardDailyPointResponse] = Field(alias="emergencyTrend")
    model_usage: list[DashboardModelUsageResponse] = Field(alias="modelUsage")
    user_usage_distribution: list[DashboardUserUsageBucketResponse] = Field(alias="userUsageDistribution")
