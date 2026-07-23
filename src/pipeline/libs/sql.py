import logging
from sqlalchemy import create_engine
from .oracle_db_connector import read_config, init_oracle_client

# Bound how long a *new* connection may spend on an unreachable host, and ask
# the server to keep the socket probed once established.
#
# CAVEAT -- these only bind in thin mode. This project runs THICK (an Oracle
# Instant Client is present, see oracle_db_connector.init_oracle_client), and
# in thick mode the Oracle client owns the connect descriptor: a measured probe
# against an unroutable host (192.0.2.1, RFC 5737) with tcp_connect_timeout=5
# still failed at exactly 60.0s -- the client's own default -- proving the
# Python-level value is ignored. They are set anyway so the bound applies if
# this ever runs thin, and because 60s is itself a bound: a *connect* to a dead
# route cannot hang forever in either mode.
#
# What is NOT bounded in thick mode is a read on an already-established socket.
# That is the 2026-07-18 failure: the connection succeeded, the VPN dropped
# mid-query, and the client blocked in recv() for 93 hours because Oracle sets
# no receive timeout by default. Fixing that at the driver layer needs
# SQLNET.RECV_TIMEOUT in a sqlnet.ora, which is machine config outside this
# repo and risks killing legitimate long queries (bot_goal4_xfer_ready alone
# runs 11-12 min between round trips). The run-level watchdog in run.py is the
# guard that actually covers this case.
CONNECT_TIMEOUT_SECONDS = 30
KEEPALIVE_MINUTES = 2


def get_engine(section: str = "dwhdb", **engine_kwargs):
    """Create and return a SQLAlchemy engine for the given config section."""
    user, password, dsn = read_config(section)
    init_oracle_client()

    connect_args = {
        "user": user,
        "password": password,
        "dsn": dsn,
        "tcp_connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "expire_time": KEEPALIVE_MINUTES,
    }
    engine = create_engine("oracle+oracledb://", connect_args=connect_args, **engine_kwargs)
    logging.info(f"Created SQLAlchemy engine for section '{section}'")
    return engine
