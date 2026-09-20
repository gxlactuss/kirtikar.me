"""Add Firebase UID and phone number identity fields to sellers table.

Revision ID: 0002_firebase_authentication
Revises: 0001_domain_tables
Create Date: 2026-09-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_firebase_authentication"
down_revision: Union[str, None] = "0001_domain_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode so this runs on SQLite too, which cannot add a constraint to an
    # existing table: it rebuilds the table instead. On PostgreSQL the batch
    # context emits the same plain ALTER statements as before.
    with op.batch_alter_table("sellers") as batch_op:
        batch_op.add_column(sa.Column("firebase_uid", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("phone_number", sa.String(length=32), nullable=True))
        batch_op.create_unique_constraint("uq_sellers_firebase_uid", ["firebase_uid"])
        batch_op.create_unique_constraint("uq_sellers_phone_number", ["phone_number"])

    op.create_index(op.f("ix_sellers_firebase_uid"), "sellers", ["firebase_uid"], unique=False)
    op.create_index(op.f("ix_sellers_phone_number"), "sellers", ["phone_number"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sellers_phone_number"), table_name="sellers")
    op.drop_index(op.f("ix_sellers_firebase_uid"), table_name="sellers")
    with op.batch_alter_table("sellers") as batch_op:
        batch_op.drop_constraint("uq_sellers_phone_number", type_="unique")
        batch_op.drop_constraint("uq_sellers_firebase_uid", type_="unique")
        batch_op.drop_column("phone_number")
        batch_op.drop_column("firebase_uid")
