import os
import oracledb
import logging
import configparser
from pathlib import Path

# ==== LOGGING SETUP ====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_DEFAULT_ORACLE_CLIENT_PATH = r"C:\Oracle\client19\product\19.0.0\client_1\bin"  # fallback if ORA_HOME/ORACLE_HOME not set
CONFIG_PATH = Path(__file__).parent / "config.ini"


def _candidate_subdirs(base: str):
    """Yield plausible subdirectories under a base path that may contain Oracle client libs."""
    yield base
    yield os.path.join(base, "bin")
    yield os.path.join(base, "lib")
    yield os.path.join(base, "instantclient")
    try:
        if os.path.isdir(base):
            for name in os.listdir(base):
                if "instantclient" in name.lower():
                    yield os.path.join(base, name)
    except Exception:
        # ignore permission errors or similar
        return


def get_oracle_client_path():
    """
    Resolve Oracle client directory in this order:
      1. ORA_HOME (if set) -> check base, bin, lib, instantclient*
      2. ORACLE_HOME (if set) -> same checks
      3. fallback default path
    Returns a path string or None if nothing appropriate is found.
    """
    # Prefer ORA_HOME then ORACLE_HOME for actual client libraries
    for base in (os.environ.get("ORA_HOME"), os.environ.get("ORACLE_HOME")):
        if not base:
            continue
        for cand in _candidate_subdirs(base):
            try:
                if Path(cand).exists():
                    return str(Path(cand))
            except Exception:
                continue

    # fallback to original hard-coded path if it exists
    if Path(_DEFAULT_ORACLE_CLIENT_PATH).exists():
        return _DEFAULT_ORACLE_CLIENT_PATH

    # Nothing found — return None and let init_oracle_client fall back to thin mode
    return None


ORACLE_CLIENT_PATH = get_oracle_client_path()

def read_config(section="dwh"):
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    if section not in config:
        raise ValueError(f"Section [{section}] not found in config file.")
    return (
        config[section]["username"],
        config[section]["password"],
        config[section]["dsn"]
    )

def init_oracle_client():
    try:
        # Ensure TNS_ADMIN is passed through for network/admin files (tnsnames.ora, sqlnet.ora)
        tns = os.environ.get("TNS_ADMIN")
        if tns:
            if Path(tns).exists():
                logging.info(f"Using TNS_ADMIN={tns} for network/admin files")
            else:
                logging.warning(f"TNS_ADMIN is set to {tns} but the path does not exist")

        if ORACLE_CLIENT_PATH:
            oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
            logging.info(f"Oracle Client Loaded in Thick Mode from {ORACLE_CLIENT_PATH}")
        else:
            logging.info("No Oracle client path resolved from ORA_HOME/ORACLE_HOME; attempting thin mode (no lib_dir).")
    except oracledb.DatabaseError as e:
        err = str(e)
        # Common case: DPI-1047 / cannot locate Oracle Client -> give actionable guidance
        if "DPI-1047" in err or "Cannot locate" in err or "cannot locate" in err or "OCI" in err:
            logging.error(f"Thick mode initialization failed: {e}")
            logging.error("Some database features require the Oracle 'thick' client (OCI).\n"
                          "Install the 64-bit Oracle Instant Client that matches your Python/OS and set\n"
                          "the ORA_HOME or ORACLE_HOME environment variable to the client folder.\n"
                          "Download: https://www.oracle.com/database/technologies/instant-client.html\n"
                          "Init docs: https://python-oracledb.readthedocs.io/en/latest/user_guide/initialization.html\n"
                          "Example (PowerShell): [Environment]::SetEnvironmentVariable('ORA_HOME','C:\\\\oracle\\\\instantclient_19_11','User')")
        else:
            logging.warning(f"Running in Thin Mode. Error: {e}")

def get_connection(section="dwh", use_pool=False, pool_min=1, pool_max=5, pool_inc=1):
    """Get a direct connection or a pooled connection to Oracle using config.ini."""
    user, password, dsn = read_config(section)
    init_oracle_client()
    if use_pool:
        try:
            pool = oracledb.create_pool(
                user=user,
                password=password,
                dsn=dsn,
                min=pool_min,
                max=pool_max,
                increment=pool_inc,
            )
            logging.info("Connection pool created successfully.")
            return pool.acquire()
        except oracledb.DatabaseError as e:
            logging.error(f"Error creating connection pool: {e}")
            return None
    else:
        try:
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            logging.info(f"Connected to {dsn} as {user}")
            return conn
        except oracledb.DatabaseError as e:
            logging.error(f"Connection failed for {dsn}: {e}")
            return None

# Example usage:
if __name__ == "__main__":
    conn = get_connection()
    if conn:
        print("Connection successful!")
        conn.close()
