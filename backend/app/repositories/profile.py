from sqlalchemy.orm import Session

from app.models.generated import Users


class ProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save_image_url(self, user: Users, image_url: str) -> None:
        user.profile_image_url = image_url
        self.db.commit()
        self.db.refresh(user)
