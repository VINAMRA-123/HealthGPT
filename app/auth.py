
import logging
import os
from functools import lru_cache
from uuid import UUID

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is missing. Check your .env file."
    )

SUPABASE_ISSUER = f"{SUPABASE_URL}/auth/v1"
SUPABASE_JWKS_URL = f"{SUPABASE_ISSUER}/.well-known/jwks.json"

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient:
    return PyJWKClient(SUPABASE_JWKS_URL)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> UUID:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=SUPABASE_ISSUER,
            options={
                "require": ["exp", "iat", "sub", "iss", "aud"],
            },
        )

        if claims.get("role") != "authenticated":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = UUID(claims["sub"])
        return user_id

    except HTTPException:
        raise

    except PyJWKClientError as exc:
        logger.error(
            "Supabase JWKS lookup failed: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc

    except jwt.ExpiredSignatureError as exc:
        logger.warning("Supabase access token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    except PyJWTError as exc:
        logger.warning(
            "Supabase JWT verification failed: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "Supabase token claims are invalid: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
