from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from ai.consultation import ConsultationResult
from app.models.generated import ConsultationLogs


class ConsultationLogRepository:
    """관리자 대시보드 지표(모델별 성공률, 폴백 비율, RAG 0건 비율 등)의 데이터
    원천을 쌓기만 하는 저장소 — 조회/집계 쿼리는 대시보드 쪽에서 별도로 만든다."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        result: ConsultationResult,
    ) -> ConsultationLogs:
        log = ConsultationLogs(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            model_id=result.model_id,
            provider_key=result.provider_key,
            is_fallback=result.is_fallback,
            is_emergency=result.is_emergency,
            department=result.department,
            confidence=result.confidence,
            rag_hit_count=result.rag_hit_count,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            response_time_ms=result.response_time_ms,
            error_type=result.error_type,
            finish_reason=result.finish_reason,
        )
        self.db.add(log)
        self.db.commit()
        return log

    def reassign_owner(self, *, from_user_id: UUID, to_user_id: UUID) -> int:
        """게스트 → 로그인 이관 시 관리자 대시보드 집계용 로그도 같이 옮긴다
        (안 옮기면 대시보드에서 이 대화의 과거 로그가 게스트 계정 명의로 남는다)."""
        result = self.db.execute(
            update(ConsultationLogs)
            .where(ConsultationLogs.user_id == from_user_id)
            .values(user_id=to_user_id)
        )
        self.db.commit()
        return result.rowcount or 0
