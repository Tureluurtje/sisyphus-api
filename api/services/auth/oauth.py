from typing import Optional

from fastapi import Request
import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from oauthlib.oauth2 import MismatchingStateError
from sqlalchemy.orm import Session as DbSession

from api.config import GOOGLE_CLIENT_SECRET_FILE, GOOGLE_OAUTH_REDIRECT_URL
from api.models.auth import OAuthAccount, OauthProviders, User
from api.schema.internal.auth import AuthTokens
from api.schema.internal.errors import BadRequestError
from api.services.auth.tokens import issue_auth_tokens

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

def google_callback_handler(request: Request, db: DbSession):
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

    try:
        flow.fetch_token(
            authorization_response=str(request.url),
        )

        user_info = id_token.verify_oauth2_token( # type: ignore
            flow.credentials.id_token,
            google_requests.Request(),
            flow.credentials.client_id,
        )
    except MismatchingStateError:
        raise BadRequestError()

    provider_user_id = user_info["sub"]
    provider_user_email = user_info["email"]
    provider_user_name = user_info.get("name")

    return authenticate_google_callback(provider_user_id, provider_user_email, provider_user_name, db)

def authenticate_google_callback(provider_user_id: str, provider_user_email: str, provider_user_name: Optional[str], db: DbSession) -> AuthTokens:
    OAuth_user_account = db.query(OAuthAccount).filter(
        OAuthAccount.provider == OauthProviders.GOOGLE,
        OAuthAccount.provider_user_id == provider_user_id
    ).scalar()

    if not OAuth_user_account:
        # Try to link google account to user
        existing_user_account = db.query(User).filter(User.email == provider_user_email).scalar()
        if not existing_user_account:
            # No account to link to, register as new user
            return register_google_account(provider_user_id, provider_user_email, provider_user_name, db)

        # Overwrite for issue_auth_tokens() function, this is allowed since it was previously unbound
        OAuth_user_account = OAuthAccount(
            user_id=existing_user_account.id,
            provider=OauthProviders.GOOGLE,
            provider_user_id=provider_user_id
        )

        db.add(OAuth_user_account)
        db.flush()

    # User verified successfully: Create tokens
    new_tokens = issue_auth_tokens(user_id=OAuth_user_account.user_id, db=db)

    return new_tokens

def register_google_account(provider_user_id: str, provider_user_email: str, provider_user_name: Optional[str], db: DbSession) -> AuthTokens:
    # Create a new User instance
    new_user = User(
        username=provider_user_name,
        grade=1, # TODO: Make user able to select grade
        email=provider_user_email,
        verified=True
    )

    # Add and commit to the database
    db.add(instance=new_user)
    db.flush()  # Get the generated user ID

    new_tokens = issue_auth_tokens(user_id=new_user.id, db=db)

    return new_tokens
