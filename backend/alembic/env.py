from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models.base import Base
from app.models import audit_log, boq, boq_item, boq_revision, contract, contractor, department, project, role, user  # noqa: F401

config = context.config
import os
from sqlalchemy.engine import make_url

db_name = make_url(str(settings.DATABASE_URL)).database
is_test_migration = os.environ.get("ALEMBIC_TEST_MIGRATION") == "1"

if is_test_migration and db_name != "infra_pm_test_db":
    raise RuntimeError(f"FATAL: ALEMBIC_TEST_MIGRATION is set, but resolved DB is {db_name}")
if db_name == "infra_pm_test_db" and not is_test_migration:
    raise RuntimeError("FATAL: Target is test database, but ALEMBIC_TEST_MIGRATION is not set")

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
