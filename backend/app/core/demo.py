"""The shared seller that every unauthenticated demo request resolves to.

The public demo at kirtikar.me has no sign-in. A judge opens the site,
photographs something and records a sentence; there is nobody to log in as.
So when DEMO_MODE is on, a request that carries no Authorization header is
resolved to this one seller instead of being rejected.

That is also what makes the processed photos loadable. A listing's
`image_urls` are served from an authenticated route, and the review screen
renders them with a plain `<img src>` — an `<img>` cannot carry a bearer
token. Without a seller to resolve an anonymous request to, every photo in
the demo would render as a broken image.

The id is fixed rather than random so the row is recognisable in a database
dump and so repeated boots of the same volume converge on one seller rather
than accumulating a new one per restart.
"""
import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.seller import Seller

logger = logging.getLogger("app.core.demo")

DEMO_SELLER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def get_or_create_demo_seller(db: Session) -> Seller:
    """The shared demo seller, created on first use.

    Two visitors can arrive at once on a freshly started Space, so the insert
    races with itself. The loser of that race gets an IntegrityError on the
    primary key, rolls back and reads the row the winner committed — which is
    the same seller either way.
    """
    seller = db.query(Seller).filter(Seller.id == DEMO_SELLER_ID).first()
    if seller is not None:
        return seller

    seller = Seller(
        id=DEMO_SELLER_ID,
        name=settings.DEMO_SELLER_NAME,
        language="en",
        cluster="Demo",
    )
    try:
        db.add(seller)
        db.commit()
        db.refresh(seller)
        logger.info("created the shared demo seller %s", DEMO_SELLER_ID)
        return seller
    except IntegrityError:
        db.rollback()
        existing = db.query(Seller).filter(Seller.id == DEMO_SELLER_ID).first()
        if existing is None:
            # The insert failed for a reason other than losing the race.
            raise
        return existing
