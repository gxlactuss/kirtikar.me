"""The migration chain must run on SQLite, which is how the API is run locally.

SQLite cannot ALTER a constraint in place, so a migration written with plain
`op.create_unique_constraint` aborts half way and leaves a partly built schema
behind. That is not a loud failure: the tables that earlier migrations made are
still there, so the API starts and only falls over later, per request, on the
first column the aborted migration never added.
"""
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.db.base import Base
import app.models  # noqa: F401 - register every model on Base.metadata

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_upgrade_head(db_path: Path) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_migrations_run_to_head_on_sqlite(tmp_path):
    """`alembic upgrade head` must succeed end to end on a SQLite file."""
    db_path = tmp_path / "migration_check.db"

    result = _alembic_upgrade_head(db_path)

    assert result.returncode == 0, (
        "alembic upgrade head failed on SQLite:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_migrated_sqlite_schema_matches_the_models(tmp_path):
    """Every table and column the models declare must exist after migrating.

    This is what catches a chain that stops early: the database looks usable but
    is missing whatever the aborted migration was going to add.
    """
    db_path = tmp_path / "schema_check.db"
    result = _alembic_upgrade_head(db_path)
    assert result.returncode == 0, result.stderr

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    missing = []
    for name, table in sorted(Base.metadata.tables.items()):
        if not inspector.has_table(name):
            missing.append(f"table {name}")
            continue
        actual = {column["name"] for column in inspector.get_columns(name)}
        for column in table.columns:
            if column.name not in actual:
                missing.append(f"{name}.{column.name}")

    engine.dispose()
    assert not missing, f"migrated schema is missing: {missing}"
