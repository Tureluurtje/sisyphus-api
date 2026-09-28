import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests

from api.config import GOOGLE_CLIENT_SECRET_FILE, GOOGLE_OAUTH_REDIRECT_URL

def initiate_google_oauth():
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
