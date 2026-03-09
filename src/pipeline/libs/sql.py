import logging
from sqlalchemy import create_engine
from .oracle_db_connector_dwh import read_config, init_oracle_client


def get_engine(section: str = "dwh", **engine_kwargs):
    """Create and return a SQLAlchemy engine for the given config section."""
    user, password, dsn = read_config(section)
    init_oracle_client()

    connect_args = {"user": user, "password": password, "dsn": dsn}
    engine = create_engine("oracle+oracledb://", connect_args=connect_args, **engine_kwargs)
    logging.info(f"Created SQLAlchemy engine for section '{section}'")
    return engine
