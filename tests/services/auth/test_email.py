from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from psycopg import InternalError

from api.schema.internal.auth import EmailData
from api.services.auth import email


def test_send_email_success_and_failure():
    email_data = EmailData(to="one@example.com", subject="hello", message="<p>hi</p>")
    with patch(
        "api.services.auth.email.resend.Emails.send", return_value={"status": "queued"}
    ):
        email._send_email(email_data)

    with pytest.raises(InternalError):
        with patch(
            "api.services.auth.email.resend.Emails.send", side_effect=Exception("boom")
        ):
            email._send_email(email_data)


def test_send_verification_email_and_password_reset_email():
    db = MagicMock()
    with patch(
        "api.services.auth.email.get_email_from_user_id", return_value="one@example.com"
    ), patch(
        "api.services.auth.email.create_verification_token", return_value="abc123"
    ), patch(
        "api.services.auth.email._send_email"
    ) as send_email_mock:
        email.send_verification_email(uuid4(), db)
    assert send_email_mock.called

    db = MagicMock()
    with patch(
        "api.services.auth.email.get_user_id_from_email", return_value=uuid4()
    ), patch(
        "api.services.auth.email.create_verification_token", return_value="reset-token"
    ), patch(
        "api.services.auth.email._send_email"
    ) as send_email_mock:
        email.send_password_reset_email("user@example.com", db)
    assert send_email_mock.called
