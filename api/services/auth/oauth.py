from fastapi import Request
import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from api.config import GOOGLE_CLIENT_SECRET_FILE, GOOGLE_OAUTH_REDIRECT_URL
from api.schema.internal.errors import BadRequestError

def initiate_google_oauth() -> tuple[str, str, str]:
    SCOPES = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid"
    ]

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRET_FILE,
        scopes=SCOPES,
    )

    flow.redirect_uri = GOOGLE_OAUTH_REDIRECT_URL

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
    )

    return authorization_url, state, flow.code_verifier

def google_callback_handler(request: Request):
    state = request.session.pop("google_state", None)
    code_verifier = request.session.pop("google_code_verifier", None)

    if not state or not code_verifier:
        raise BadRequestError(detail="Invalid OAuth session")

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRET_FILE,
        scopes=[
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid",
        ],
        state=state,
    )

    flow.redirect_uri = GOOGLE_OAUTH_REDIRECT_URL
    flow.code_verifier = code_verifier

    flow.fetch_token(
        authorization_response=str(request.url),
    )

    user_info = id_token.verify_oauth2_token(
        flow.credentials.id_token,
        google_requests.Request(),
        flow.credentials.client_id,
    )

    user_email = user_info["email"]
    user_name = user_info.get("name")

    return {
        "email": user_email,
        "name": user_name
    }
