"""
Alembic environment configuration for Block E Chunking service.
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Block E models
from app.models.chunk_record import ChunkRecord
from app.models.embedding_job import EmbeddingJob

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata - combine metadata from all models
# Import the Base from each model and use their metadata
from app.models.chunk_record import Base as ChunkBase
from app.models.embedding_job import Base as EmbeddingBase

# Combine metadata from both bases
from sqlalchemy import MetaData
target_metadata = MetaData()
for table in ChunkBase.metadata.tables.values():
    table.tometadata(target_metadata)
for table in EmbeddingBase.metadata.tables.values():
    table.tometadata(target_metadata)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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
