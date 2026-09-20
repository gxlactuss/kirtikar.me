"""Authentication service managing Firebase token verification, seller identity resolution, and JWT issuance."""
from typing import Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.firebase import (
    FirebaseAuthenticationError,
    verify_firebase_id_token,
)
from app.core.security import create_access_token
from app.models.seller import Seller


def authenticate_firebase_user(id_token: str, db: Session) -> Tuple[str, Seller]:
    """Verify Firebase ID token, resolve or create the application Seller entity, and issue an application JWT.

    Enforces strict identity conflict safety:
    - Never overwrites existing Firebase UID with a different user.
    - Never merges disparate seller records silently.
    - Rejects tokens with conflicting phone numbers or accounts.
    - Resolves existing sellers by UID first, then verified phone number.
    - Automatically creates a fresh Seller on first verified phone login.
    """
    try:
        identity = verify_firebase_id_token(id_token)
    except FirebaseAuthenticationError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    firebase_uid = identity["uid"]
    phone_number = identity["phone_number"]

    # 1. Look up seller by Firebase UID
    seller_by_uid = db.query(Seller).filter(Seller.firebase_uid == firebase_uid).first()

    # 2. Look up seller by Phone Number
    seller_by_phone = db.query(Seller).filter(Seller.phone_number == phone_number).first()

    # Conflict Safety Check A:
    # Firebase UID belongs to seller A, but verified phone differs from seller A's stored phone.
    if seller_by_uid is not None:
        if seller_by_uid.phone_number and seller_by_uid.phone_number != phone_number:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identity conflict: verified phone number does not match registered phone number.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Conflict Safety Check B:
        # Phone number already belongs to another seller record (with a different ID).
        if seller_by_phone is not None and seller_by_phone.id != seller_by_uid.id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identity conflict: phone number is registered to a different seller identity.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # If UID seller exists but phone was not yet set, update it safely
        if not seller_by_uid.phone_number:
            seller_by_uid.phone_number = phone_number
            db.commit()
            db.refresh(seller_by_uid)

        seller = seller_by_uid

    elif seller_by_phone is not None:
        # Firebase UID not found, but phone exists on an existing seller.
        # Conflict Safety Check: That seller must not already be bound to another Firebase UID.
        if seller_by_phone.firebase_uid and seller_by_phone.firebase_uid != firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identity conflict: seller phone is already associated with another Firebase account.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Safely associate Firebase UID with existing seller
        seller_by_phone.firebase_uid = firebase_uid
        db.commit()
        db.refresh(seller_by_phone)
        seller = seller_by_phone

    else:
        # Case C: Neither Firebase UID nor phone exists -> Create new Seller
        seller = Seller(
            firebase_uid=firebase_uid,
            phone_number=phone_number,
            name="",
            language="hi",
            cluster=None,
            ondc_seller_id=None,
        )
        db.add(seller)
        db.commit()
        db.refresh(seller)

    # Issue application JWT
    access_token = create_access_token(seller_id=seller.id)
    return access_token, seller
