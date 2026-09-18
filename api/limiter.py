from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi import Request


limiter = Limiter(key_func=get_remote_address)


def user_id_key(request: Request):
    return getattr(request.state, "user_id", get_remote_address(request))


async def set_user_id(request: Request):
    # Import lazily so the auth dependency module can import the limiter safely.
    from api.services.auth.dependencies import get_user_id

    user_id = get_user_id(request)
    request.state.user_id = str(user_id)
