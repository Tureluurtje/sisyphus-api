from fastapi import Request
from fastapi.templating import Jinja2Templates

def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

def get_user_id():
    ...

def get_user_id_skip_csrf():
    ...

def get_user_id_from_refresh():
    ...

def get_user_id_from_refresh_body():
    ...

def validate_user_service():
    ...
