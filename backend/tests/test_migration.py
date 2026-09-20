"""Tests for Alembic migration integrity, metadata discovery, and SQL generation."""
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command


def test_migration_file_exists_and_discoverable():
    """Verify Alembic detects all migrations in the chain up to the current head."""
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    script = ScriptDirectory.from_config(config)
    head_revision = script.get_current_head()

    assert head_revision == "0007_listing_origin"

    rev_head = script.get_revision(head_revision)
    assert rev_head.down_revision == "0006_expected_photo_count"

    # Verify 0001_domain_tables
    rev_0001 = script.get_revision("0001_domain_tables")
    assert rev_0001 is not None
    assert rev_0001.module is not None
    assert callable(rev_0001.module.upgrade)
    assert callable(rev_0001.module.downgrade)

    # Verify 0002_firebase_authentication
    rev_0002 = script.get_revision("0002_firebase_authentication")
    assert rev_0002 is not None
    assert rev_0002.down_revision == "0001_domain_tables"
    assert rev_0002.module is not None
    assert callable(rev_0002.module.upgrade)
    assert callable(rev_0002.module.downgrade)


def test_migration_sql_generation_offline(capsys, monkeypatch):
    """Verify that Alembic can render the offline SQL for the entire migration chain."""
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    # The assertions below are PostgreSQL DDL, so pin the dialect rather than
    # inheriting whatever DATABASE_URL this machine happens to have in .env.
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        "postgresql+psycopg2://user:pass@localhost:5432/listing_factory",
    )

    # Run upgrade in offline mode
    command.upgrade(config, "head", sql=True)
    captured = capsys.readouterr()
    sql_output = captured.out

    # Verify 0001 migration elements
    assert "CREATE TABLE sellers" in sql_output
    assert "CREATE TABLE listings" in sql_output
    assert "CREATE TABLE media" in sql_output
    assert "CREATE TABLE listing_consents" in sql_output
    assert "CREATE TABLE suggestions" in sql_output
    assert "CREATE TABLE listing_approvals" in sql_output
    assert "CREATE TYPE listing_state" in sql_output
    assert "CREATE TYPE media_type" in sql_output
    assert "uq_sellers_ondc_seller_id" in sql_output
    assert "uq_listings_seller_client_item" in sql_output
    assert "uq_listing_consents_listing_id" in sql_output
    assert "uq_listing_approvals_listing_id" in sql_output
    assert "0001_domain_tables" in sql_output

    # Verify 0002 migration elements
    assert "ALTER TABLE sellers ADD COLUMN firebase_uid" in sql_output
    assert "ALTER TABLE sellers ADD COLUMN phone_number" in sql_output
    assert "uq_sellers_firebase_uid" in sql_output
    assert "uq_sellers_phone_number" in sql_output
    assert "0002_firebase_authentication" in sql_output
