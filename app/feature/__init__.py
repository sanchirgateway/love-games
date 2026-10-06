# Импорт всех моделей, чтобы они попали в Base.metadata (нужно Alembic'у и для связей между моделями)
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.reviews.models import DatePhoto, DateReview
from app.feature.user.models import User

__all__ = ["DateEvent", "DatePhoto", "DateReview", "DateStatus", "User"]
