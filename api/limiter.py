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
