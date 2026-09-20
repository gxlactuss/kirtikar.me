"""Remember the studio image the Vision Station produced for each photo.

The image stage graded, cut out and composited every upload and wrote the
result to disk, but nothing recorded where. The media endpoint kept serving
`storage_path` - the raw camera frame - so the polished photo informed the fact
sheet and was then thrown away: review, preview and publish all showed the
artisan's original picture, clutter and all.

Revision ID: 0005_media_processed_path
Revises: 0004_listing_results
Create Date: 2026-09-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_media_processed_path"
down_revision: Union[str, None] = "0004_listing_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media", sa.Column("processed_path", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "processed_path")
