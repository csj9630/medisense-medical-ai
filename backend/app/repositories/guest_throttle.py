from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated import GuestIpThrottle


class GuestThrottleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_and_increment(self, ip: str, *, limit: int, window_hours: int) -> bool:
        """허용되면 카운트를 늘리고 True, 한도를 넘겼으면 카운트를 안 늘리고
        False를 반환한다. `with_for_update()`로 행 잠금을 걸어서, 같은 IP에서
        동시에 여러 요청이 와도(동시성 경합) 카운트가 꼬이지 않게 한다."""
        now = datetime.now(UTC)
        row = self.db.execute(
            select(GuestIpThrottle).where(GuestIpThrottle.ip == ip).with_for_update()
        ).scalar_one_or_none()

        if row is None:
            self.db.add(GuestIpThrottle(ip=ip, window_started_at=now, request_count=1))
            self.db.commit()
            return True

        window_expired = row.window_started_at < now - timedelta(hours=window_hours)
        if window_expired:
            row.window_started_at = now
            row.request_count = 1
            self.db.commit()
            return True

        if row.request_count >= limit:
            self.db.rollback()  # with_for_update로 잡은 잠금을 바로 풀어준다.
            return False

        row.request_count += 1
        self.db.commit()
        return True
