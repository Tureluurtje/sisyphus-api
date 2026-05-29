from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi import Request, Depends

from uuid import UUID
from api.services.auth_service import get_user_id

limiter = Limiter(key_func=get_remote_address)


def user_id_key(request: Request):
    return getattr(request.state, "user_id", get_remote_address(request))


async def set_user_id(request: Request, user_id: UUID = Depends(get_user_id)):
    request.state.user_id = str(user_id)


def email_key(request: Request):
    """
    Uses the email from the login request body for rate limiting.
    Falls back to IP if email is missing or parsing fails.
    """
    try:
        # FastAPI already parsed the body into request._json if you use Pydantic
        # Otherwise you can fallback to IP
        body = request._json
        if isinstance(body, dict):
            email = body.get("email")
            if isinstance(email, str) and email:
                return email.lower()
    except Exception:
        pass
    return get_remote_address(request)
