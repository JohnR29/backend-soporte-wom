import secrets

from app.core.config import get_settings

# TODO: fixed test token until the real token issuing system is integrated.
_STATIC_USER_ID = "static-token-user"


def get_user(token: str) -> str | None:
    if not secrets.compare_digest(get_settings().backend_static_token, token):
        return None
    return _STATIC_USER_ID