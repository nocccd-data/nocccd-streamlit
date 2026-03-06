import logging
from sqlalchemy import create_engine
from .oracle_db_connector_dwh import read_config, init_oracle_client


def get_engine(section: str = "user", **engine_kwargs):
    """Create and return a SQLAlchemy engine for the given config section.

    The engine uses the oracledb dialect. Reads credentials from
    libs/config.ini via read_config(), ensures the Oracle client is
    initialized (thick mode) via init_oracle_client(), and returns the
    SQLAlchemy engine. Any additional keyword args are forwarded to
    SQLAlchemy's create_engine.
    """
    user, password, dsn = read_config(section)
    # Try to initialize thick client if available — safe to call repeatedly
    init_oracle_client()

    connect_args = {"user": user, "password": password, "dsn": dsn}
    engine = create_engine("oracle+oracledb://", connect_args=connect_args, **engine_kwargs)
    logging.info(f"Created SQLAlchemy engine for section '{section}'")
    return engine
