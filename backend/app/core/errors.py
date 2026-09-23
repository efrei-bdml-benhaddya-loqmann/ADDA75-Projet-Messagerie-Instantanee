"""Gestion homogène des erreurs de l'API."""

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Schéma standard d'une réponse d'erreur."""

    detail: str
    code: str | None = None


class AppException(HTTPException):
    """Exception de base de l'application avec code d'erreur textuel optionnel."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


class UnauthorizedException(AppException):
    """Erreur 401 Unauthorized (JWT manquant, invalide ou expiré)."""

    def __init__(self, detail: str = "Jeton d'authentification invalide ou expiré") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code="UNAUTHORIZED",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ConflictException(AppException):
    """Erreur 409 Conflict (ex: nom d'utilisateur déjà pris)."""

    def __init__(self, detail: str = "Cette ressource existe déjà") -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            code="CONFLICT",
        )


class NotFoundException(AppException):
    """Erreur 404 Not Found."""

    def __init__(self, detail: str = "Ressource introuvable") -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            code="NOT_FOUND",
        )


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    """Gestionnaire global pour les AppException."""
    content: dict[str, Any] = {"detail": exc.detail}
    if exc.code:
        content["code"] = exc.code
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)
