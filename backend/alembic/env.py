import os
import sys
from os.path import abspath, dirname
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add parent directory to path so application modules can be imported
sys.path.insert(0, dirname(dirname(abspath(__file__))))

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401 - ensure domain models are registered on Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL dynamically from app settings.
#
# ALEMBIC_DATABASE_URL overrides it, so a caller can render or apply migrations
# for a particular dialect without editing .env. Offline `--sql` rendering needs
# this: batch mode cannot run without a live connection, so SQL for a PostgreSQL
# deployment has to be generated against a PostgreSQL URL explicitly.
config.set_main_option(
    "sqlalchemy.url", os.environ.get("ALEMBIC_DATABASE_URL") or settings.DATABASE_URL
)

# Model metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER a constraint in place. Batch mode rebuilds the
            # table instead, so the same migrations run on a laptop's SQLite file
            # and on PostgreSQL. Without it `alembic upgrade head` dies on 0002.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
