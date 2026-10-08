import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config.config import app_settings

# auto_error=False: свою ошибку отдаём сами, а Swagger всё равно показывает кнопку Authorize
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_admin(api_key: Annotated[str | None, Security(_api_key_header)]) -> None:
    expected = app_settings.admin_api_key
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Админ-API выключено: не задан APP_ADMIN_API_KEY")
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный X-API-Key")


AdminDep = Depends(require_admin)
