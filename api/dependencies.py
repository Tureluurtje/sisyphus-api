from fastapi import Request
from fastapi.templating import Jinja2Templates

def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates
