from uuid import UUID

from pathlib import Path
from jinja2 import Template
from psycopg import InternalError
import resend
from sqlalchemy.orm import Session as DbSession

from api.models.auth import VerificationTokenPurposes
from api.schema.internal.auth import EmailData
from api.logging_config import app_logger
from api.services.auth.dependencies import get_email_from_user_id, get_user_id_from_email
from api.services.auth.tokens import create_verification_token


def _send_email(email_data: EmailData) -> None:
    params: resend.Emails.SendParams = {
        "from": "Tureluurtje <no-reply@iteam.kwako.nl>",
        "to": [email_data.to],
        "subject": email_data.subject,
        "html": email_data.message,
    }
    try:
        email: resend.Emails.SendResponse = resend.Emails.send(params)
        if email:
            return
        else:
            raise
    except:
        app_logger.error("Email did not send correctly")
        raise InternalError()


def send_verification_email(user_id: UUID, db: DbSession) -> None:
    user_email = get_email_from_user_id(user_id, db)
    if not user_email:
        raise InternalError()

    verification_token = create_verification_token(
        user_id=user_id,
        purpose=VerificationTokenPurposes.EMAIL_VERIFICATION,
        db=db,
    )

    verification_url = (
        f"https://sisyphus.kwako.nl/api/auth/verify-account?token={verification_token}"
    )

    template_path = (
        Path(__file__).parents[2] / "public" / "templates" / "verification_email.html"
    )
    html_message = Template(template_path.read_text(encoding="utf-8")).render(
        verification_url=verification_url
    )

    email_data = EmailData(
        to=user_email,
        subject="Account verification",
        message=html_message,
    )
    _send_email(email_data=email_data)

def send_password_reset_email(email: str, db: DbSession) -> None:
    user_id = get_user_id_from_email(email, db)
    if not user_id:
        raise InternalError()

    password_reset_token = create_verification_token(
        user_id=user_id,
        purpose=VerificationTokenPurposes.PASSWORD_RESET,
        db=db,
    )

    password_reset_url = (
        f"https://sisyphus.kwako.nl/api/auth/reset-forgotten-password?token={password_reset_token}"
    )

    template_path = (
        Path(__file__).parents[2] / "public" / "templates" / "password_reset_email.html"
    )
    html_message = Template(template_path.read_text(encoding="utf-8")).render(
        password_reset_url=password_reset_url
    )

    email_data = EmailData(
        to=email,
        subject="Password reset",
        message=html_message,
    )
    _send_email(email_data=email_data)
