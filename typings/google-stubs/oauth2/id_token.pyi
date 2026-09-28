from typing import Any, Mapping


def verify_oauth2_token(
    id_token: str,
    request: Any,
    audience: str | None = None,
    clock_skew_in_seconds: int = 0,
) -> Mapping[str, Any]: ...
