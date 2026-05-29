from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
from uuid import UUID

from api.dependencies import get_templates
from api.services.auth_service import (
        validate_user_service,
        validate_user_service,
        response_cookies_generator,
        get_user_id
     )
from api.schema.internal.errors import (
    TokenMissingError,
    TokenInvalidError,
    ConflictError
)

from api.logging_config import app_logger, error_logger
from api.limiter import limiter

# IMPORTANT: Don't use a prefix for this router since it serves from origin
router = APIRouter(tags=["web"])

# TODO: Add limiters to this router


@router.get("/")
def index(request: Request):
    """Serve the dashboard page."""
    user_id, tokens = validate_user_service(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    try:
        ###############################################
        #######     BODY OF DASHBOARD LOGIC     #######
        ###############################################

        # Use user_id from validate_user (which may have refreshed tokens).
        # Don't call get_user_id again - it would fail on the old request without new access_token.
        app_logger.info(
            f"index: user_id from validate_user = {user_id}, tokens refreshed = {tokens is not None}"
        )

        from api.services.auth_service import get_user_data_service

        user_data = get_user_data_service(user_id=user_id)

        templates = get_templates(request)
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"user": user_data},
        )

        # If validate_user issued new tokens, set cookies on the response
        if tokens:
            app_logger.info(f"index: setting refreshed tokens on response")
            response = response_cookies_generator(tokens, response)

        return response
    except (TokenMissingError, TokenInvalidError) as e:
        error_logger.warning(f"Authentication error on index access: {e}")
        return RedirectResponse(url="/login", status_code=302)
    except Exception as e:
        error_logger.exception(f"Error loading index: {e}")
        return RedirectResponse(url="/login", status_code=302)


@router.get("/login")
def login_get(request: Request):
    """Serve the login page."""
    user_id, tokens = validate_user_service(request)
    if tokens:
        # If validate_user issued new tokens, set cookies on the response
        response = RedirectResponse(url="/", status_code=302)
        response = response_cookies_generator(tokens, response)
        return response
    if user_id:
        return RedirectResponse(url="/", status_code=302)
    templates = get_templates(request)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.post("/login")
async def login_post(request: Request):
    """Handle login form submission."""
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
        except ValueError:
            data = {}
        username = data.get("username") or data.get("email")
        password = data.get("password")
    else:
        form_data = await request.form()
        username = form_data.get("username") or form_data.get("email")
        password = form_data.get("password")

    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"error": "username/email and password are required"},
        )

    try:
        # Import here to avoid circular imports
        from api.services.auth_service import authenticate_user

        tokens = authenticate_user(email=username, password=password)
        response = response_cookies_generator(tokens)
        return response
    except Exception as e:
        error_logger.exception(f"Login error: {e}")
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})


@router.get("/register")
def register_get(request: Request):
    """Serve the registration page."""
    templates = get_templates(request)
    return templates.TemplateResponse(request=request, name="register.html", context={})


@router.post("/register")
async def register_post(request: Request):
    """Handle registration form submission."""
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
        except ValueError:
            data = {}
        first_name = data.get("firstName") or data.get("first_name")
        last_name = data.get("lastName") or data.get("last_name")
        username = data.get("username") or data.get("email")
        password = data.get("password")
    else:
        form_data = await request.form()
        first_name = form_data.get("first_name")
        last_name = form_data.get("last_name")
        username = form_data.get("username") or form_data.get("email")
        password = form_data.get("password")

    if not username or not password or not first_name or not last_name:
        return JSONResponse(
            status_code=400,
            content={"error": "email, password, first name and last name are required"},
        )

    try:
        # Import here to avoid circular imports
        from api.services.auth_service import register_user

        tokens = register_user(
            first_name=first_name,
            last_name=last_name,
            email=username,
            password=password,
        )
        response = response_cookies_generator(tokens)
        return response
    except Exception as e:
        error_logger.exception(f"Registration error: {e}")
        status_code = 422
        error_msg = "Registration failed"

        # Handle specific error types
        if "weak" in str(e).lower():
            status_code = 400
            error_msg = "Password too weak"
        elif (
            "already exists" in str(e).lower()
            or "409" in str(e)
            or isinstance(e, ConflictError)
        ):
            status_code = 409
            error_msg = "User already exists"

        return JSONResponse(status_code=status_code, content={"error": error_msg})


@router.post("/logout")
def logout(request: Request, user_id: Optional[UUID] = Depends(get_user_id)):
    """Handle user logout."""
    try:
        if user_id:
            from api.services.auth_service import revoke_refresh_token, revoke_access_token

            access_token = request.cookies.get("access_token")

            revoke_refresh_token(user_id=user_id)
            if access_token:
                revoke_access_token(access_token)

        response = JSONResponse(status_code=200, content={"success": True})
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        response.delete_cookie("csrf_token", path="/")
        return response
    except Exception as e:
        error_logger.exception(f"Logout error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
