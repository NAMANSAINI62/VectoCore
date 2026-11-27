"""Custom authentication exceptions."""

from fastapi import HTTPException, status


class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "Invalid authentication credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidCredentialsError(AuthenticationError):
    def __init__(self):
        super().__init__(detail="Incorrect email or password")


class InactiveUserError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )


class TokenExpiredError(AuthenticationError):
    def __init__(self):
        super().__init__(detail="Token has expired")


class SessionRevokedError(AuthenticationError):
    def __init__(self):
        super().__init__(detail="Session has been revoked or reused")


class UserAlreadyExistsError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists",
        )
