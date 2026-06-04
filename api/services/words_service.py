from uuid import UUID
from api.database import get_db_session


def get_due_words_service(user_id: UUID): ...
