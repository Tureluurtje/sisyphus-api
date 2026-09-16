from api.database import get_db_session
from uuid import UUID
from api.services.auth.email import send_verification_email, send_password_reset_email


def test_send_verification_email():
    with get_db_session() as db:
        # Tureluurtje.1@gmail.com
        send_verification_email(UUID("9a1b4961-ffbc-4187-8758-92d75703773e"), db)
        db.commit()

def test_send_password_reset_email():
    with get_db_session() as db:
        # Tureluurtje.1@gmail.com
        send_password_reset_email("tureluurtje.1@gmail.com", db)
        db.commit()
