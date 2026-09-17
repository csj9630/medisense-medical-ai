"""관리자 대시보드 지표 집계 — `consultation_logs`를 읽기만 한다(쓰기는
`message.py`가 담당). 전부 집계 쿼리라 개별 사용자 식별 정보(이메일 등)는
응답에 절대 포함하지 않는다 — 특히 "사용자별 사용량"은 구간별 사용자 수
분포로만 노출한다(개인정보 보관 정책이 아직 미정이라, 지금은 익명 집계만
안전하다고 보고 개별 사용자 리스트는 만들지 않았다).

사용자 만족도(좋아요/싫어요)는 아직 그 기능 자체가 없어서 이 모듈에 없다 —
근거 없는 수치를 만들어내지 않는다(루트 CLAUDE.md "근거 없는 성능·정확도
주장 금지"). "오류율"도 별도 HTTP 오류 로그가 없어서 만들지 않았고, 대신
`fallback_rate`(LLM 호출이 실패해서 안전한 대체 응답으로 넘어간 비율)를
가장 가까운 지표로 쓴다.
"""
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.generated import AdminDocuments, ConsultationLogs, DocumentChunks

DEFAULT_TREND_DAYS = 14

# 2026-09-09: 쿼리를 아무리 합쳐도(12회->5회 왕복) Neon(원격 DB)에 새로 연결하는
# 비용 자체가 지배적이다(실측: 완전히 새 연결은 컴퓨트가 깨어있어도 TLS 핸드셰이크
# +Postgres 인증만으로 ~2.5초, 컴퓨트까지 절전 상태였으면 ~7초 - 반면 이미 열려있는
# 연결을 그대로 재사용하면 쿼리 5개 다 합쳐 ~1초). 대시보드는 실시간성이 필요 없는
# 집계 지표라(오늘 하루 단위 통계), 짧은 TTL로 그대로 재사용해도 무리 없다 - 이렇게
# 하면 재방문/새로고침은 DB를 아예 안 타서 즉시 응답하고, "연결이 식어서 다시 느려지는"
# 문제도 캐시가 신선하게 유지되는 동안은 자연히 피하게 된다.
_OVERVIEW_CACHE_TTL_SECONDS = 30
_overview_cache: dict[int, tuple[float, "DashboardOverview"]] = {}
_overview_cache_lock = threading.Lock()


@dataclass
class DashboardKpis:
    today_consultations: int
    active_users_today: int
    avg_response_time_ms: float | None
    rag_hit_rate: float | None
    emergency_count_today: int
    fallback_rate: float | None
    document_count: int
    chunk_count: int


@dataclass
class DailyPoint:
    date: str
    count: int


@dataclass
class ModelUsageStat:
    model_id: str
    total: int
    success: int
    success_rate: float


@dataclass
class UserUsageBucket:
    label: str
    user_count: int


@dataclass
class DashboardOverview:
    kpis: DashboardKpis
    daily_consultations: list[DailyPoint]
    emergency_trend: list[DailyPoint]
    model_usage: list[ModelUsageStat]
    user_usage_distribution: list[UserUsageBucket]


def _today_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _sum_when(condition) -> object:
    return func.sum(case((condition, 1), else_=0))


def get_kpis(db: Session) -> DashboardKpis:
    """Neon(원격 DB)이라 쿼리 한 번마다 왕복 지연이 붙는다 - 예전엔 이 함수 하나가
    조건만 다른 count()를 6번 따로 날려서(오늘 통계 5개 + 응급 1개) 대시보드 로드가
    유독 느렸다(2026-09-09 실측: 다른 집계는 각 ~200ms인데 이 함수만 여러 초).
    `today_filter`를 공유하는 집계는 조건부 SUM/COUNT/AVG로 한 쿼리에 모아서 왕복을
    줄인다. document_count/chunk_count는 다른 테이블이라 GROUP BY로 합칠 수 없지만,
    스칼라 서브쿼리 두 개를 한 SELECT에 넣으면 그것도 왕복 한 번으로 끝난다."""
    today_start = _today_start()
    today_filter = ConsultationLogs.created_at >= today_start

    today_stats_stmt = select(
        func.count(ConsultationLogs.id),
        _sum_when(ConsultationLogs.rag_hit_count > 0),
        _sum_when(ConsultationLogs.is_fallback.is_(True)),
        _sum_when(ConsultationLogs.is_emergency.is_(True)),
        func.count(func.distinct(ConsultationLogs.user_id)),
        func.avg(ConsultationLogs.response_time_ms),
    ).where(today_filter)
    (
        total_today,
        rag_hits_today,
        fallback_today,
        emergency_today,
        active_users_today,
        avg_response_time_ms,
    ) = db.execute(today_stats_stmt).one()
    total_today = total_today or 0

    document_count, chunk_count = db.execute(
        select(
            select(func.count(AdminDocuments.id)).scalar_subquery(),
            select(func.count(DocumentChunks.id)).scalar_subquery(),
        )
    ).one()

    return DashboardKpis(
        today_consultations=total_today,
        active_users_today=active_users_today or 0,
        avg_response_time_ms=float(avg_response_time_ms) if avg_response_time_ms is not None else None,
        # total_today가 0이면 "0%"가 아니라 "아직 데이터 없음"이 정확하므로 None을 반환한다.
        rag_hit_rate=(int(rag_hits_today or 0) / total_today) if total_today else None,
        emergency_count_today=int(emergency_today or 0),
        fallback_rate=(int(fallback_today or 0) / total_today) if total_today else None,
        document_count=document_count or 0,
        chunk_count=chunk_count or 0,
    )


def _fill_days(counts: dict[str, int], *, since: datetime, days: int) -> list[DailyPoint]:
    """로그가 없는 날짜도 0으로 채워서 프론트 라인 차트의 x축이 안 끊기게 한다."""
    points: list[DailyPoint] = []
    for i in range(days):
        day = (since + timedelta(days=i)).date()
        points.append(DailyPoint(date=str(day), count=counts.get(str(day), 0)))
    return points


def _daily_series(db: Session, *extra_conditions, days: int) -> list[DailyPoint]:
    """최근 `days`일간 하루 단위 카운트."""
    since = _today_start() - timedelta(days=days - 1)
    day_expr = func.date(ConsultationLogs.created_at)
    stmt = (
        select(day_expr.label("day"), func.count(ConsultationLogs.id))
        .where(ConsultationLogs.created_at >= since, *extra_conditions)
        .group_by(day_expr)
    )
    counts = {str(day): count for day, count in db.execute(stmt).all()}
    return _fill_days(counts, since=since, days=days)


def get_daily_consultations(db: Session, days: int = DEFAULT_TREND_DAYS) -> list[DailyPoint]:
    return _daily_series(db, days=days)


def get_emergency_trend(db: Session, days: int = DEFAULT_TREND_DAYS) -> list[DailyPoint]:
    return _daily_series(db, ConsultationLogs.is_emergency.is_(True), days=days)


def _get_daily_consultations_and_emergency_trend(
    db: Session, days: int = DEFAULT_TREND_DAYS
) -> tuple[list[DailyPoint], list[DailyPoint]]:
    """get_daily_consultations() + get_emergency_trend()과 결과는 동일하지만, 같은
    테이블/기간을 조건만 다르게 두 번 왕복하는 대신 조건부 SUM으로 한 번에 묶어서
    가져온다 - Neon 왕복 지연이 커서(get_kpis 최적화와 같은 이유) get_overview가
    쓰는 전용 경로다. 개별적으로 하나만 필요하면 위 두 공개 함수를 그대로 쓴다."""
    since = _today_start() - timedelta(days=days - 1)
    day_expr = func.date(ConsultationLogs.created_at)
    stmt = (
        select(day_expr.label("day"), func.count(ConsultationLogs.id), _sum_when(ConsultationLogs.is_emergency.is_(True)))
        .where(ConsultationLogs.created_at >= since)
        .group_by(day_expr)
    )
    daily_counts: dict[str, int] = {}
    emergency_counts: dict[str, int] = {}
    for day, total, emergency in db.execute(stmt).all():
        daily_counts[str(day)] = total
        emergency_counts[str(day)] = int(emergency or 0)

    return (
        _fill_days(daily_counts, since=since, days=days),
        _fill_days(emergency_counts, since=since, days=days),
    )


def get_model_usage(db: Session, days: int = DEFAULT_TREND_DAYS) -> list[ModelUsageStat]:
    """모델별 호출 수/성공 수. is_fallback=False면 성공으로 센다(응급 하드필터로
    LLM을 아예 안 부른 요청은 model_id가 없어서 여기 안 잡힌다)."""
    since = _today_start() - timedelta(days=days - 1)
    success_expr = case((ConsultationLogs.is_fallback.is_(False), 1), else_=0)
    stmt = (
        select(
            ConsultationLogs.model_id,
            func.count(ConsultationLogs.id),
            func.sum(success_expr),
        )
        .where(ConsultationLogs.created_at >= since, ConsultationLogs.model_id.is_not(None))
        .group_by(ConsultationLogs.model_id)
        .order_by(func.count(ConsultationLogs.id).desc())
    )

    stats: list[ModelUsageStat] = []
    for model_id, total, success in db.execute(stmt).all():
        total = total or 0
        success = int(success or 0)
        stats.append(
            ModelUsageStat(
                model_id=model_id,
                total=total,
                success=success,
                success_rate=(success / total) if total else 0.0,
            )
        )
    return stats


_USER_USAGE_BUCKETS = (
    ("1~5", 1, 5),
    ("6~10", 6, 10),
    ("11~20", 11, 20),
    ("21+", 21, None),
)


def get_user_usage_distribution(db: Session, days: int = DEFAULT_TREND_DAYS) -> list[UserUsageBucket]:
    """사용자별 상담 횟수를 구간별 인원 수로만 집계한다 — 개별 사용자 식별 정보
    (이메일 등)는 절대 응답에 안 넣는다. 개인정보 보관 정책이 정해지기 전까지는
    이 익명 집계 형태가 안전하다고 보고 이렇게 설계했다."""
    since = _today_start() - timedelta(days=days - 1)
    per_user = (
        select(ConsultationLogs.user_id, func.count(ConsultationLogs.id).label("cnt"))
        .where(ConsultationLogs.created_at >= since)
        .group_by(ConsultationLogs.user_id)
        .subquery()
    )
    counts = [row[0] for row in db.execute(select(per_user.c.cnt)).all()]

    buckets = []
    for label, low, high in _USER_USAGE_BUCKETS:
        n = sum(1 for c in counts if c >= low and (high is None or c <= high))
        buckets.append(UserUsageBucket(label=label, user_count=n))
    return buckets


def _get_cached_overview(days: int) -> DashboardOverview | None:
    with _overview_cache_lock:
        entry = _overview_cache.get(days)
    if entry is None:
        return None
    cached_at, overview = entry
    if time.monotonic() - cached_at > _OVERVIEW_CACHE_TTL_SECONDS:
        return None
    return overview


def _set_cached_overview(days: int, overview: DashboardOverview) -> None:
    with _overview_cache_lock:
        _overview_cache[days] = (time.monotonic(), overview)


def get_overview(db: Session, days: int = DEFAULT_TREND_DAYS) -> DashboardOverview:
    cached = _get_cached_overview(days)
    if cached is not None:
        return cached

    daily_consultations, emergency_trend = _get_daily_consultations_and_emergency_trend(db, days)
    overview = DashboardOverview(
        kpis=get_kpis(db),
        daily_consultations=daily_consultations,
        emergency_trend=emergency_trend,
        model_usage=get_model_usage(db, days),
        user_usage_distribution=get_user_usage_distribution(db, days),
    )
    _set_cached_overview(days, overview)
    return overview
