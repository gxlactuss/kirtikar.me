"""Application JWT management and authenticated seller FastAPI dependency."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.demo import get_or_create_demo_seller
from app.db.session import get_db
from app.models.seller import Seller

# `auto_error=False` so a missing header reaches `get_current_seller` as None
# rather than being rejected by the scheme itself. DEMO_MODE has to be able to
# answer that case, and the rejection below keeps the same 401 it always had.
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    seller_id: Union[str, uuid.UUID],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed application JWT identifying a persistent Seller entity."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(seller_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and cryptographically validate an application JWT.

    Raises:
        HTTPException(401): If the token is invalid, expired, or malformed.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise credentials_exception


def get_current_seller(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Seller:
    """FastAPI security dependency for extracting and resolving the current authenticated seller.

    With DEMO_MODE on, a request with no Authorization header at all is
    resolved to the shared demo seller instead of being rejected — that is the
    whole of the public demo's "authentication". A header that is present but
    invalid is still a 401 either way: falling back to the demo seller there
    would turn an expired token into a silent identity swap.
    """
    if credentials is None:
        if settings.DEMO_MODE:
            return get_or_create_demo_seller(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    seller_id_str = payload.get("sub")
    if not seller_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        seller_uuid = uuid.UUID(seller_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject identifier in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    seller = db.query(Seller).filter(Seller.id == seller_uuid).first()
    if seller is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Seller not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return seller
