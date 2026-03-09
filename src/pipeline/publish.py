"""Publish Hyper files to Tableau Cloud and download them back."""

import tempfile
import zipfile
from pathlib import Path

import tableauserverclient as TSC

from .config import HYPER_DIR


def _sign_in(server_url: str, site_name: str, pat_name: str, pat_value: str) -> tuple:
    """Create a Tableau Server client and sign-in context manager."""
    auth = TSC.PersonalAccessTokenAuth(pat_name, pat_value, site_id=site_name)
    server = TSC.Server(server_url, use_server_version=True)
    return server, auth


_TARGET_PROJECT = "Streamlit Data"


def _find_project(server: TSC.Server, project_name: str) -> str:
    """Return the project ID for the given project name."""
    for proj in TSC.Pager(server.projects):
        if proj.name == project_name:
            return proj.id
    raise ValueError(f"Project '{project_name}' not found on Tableau Cloud")


def publish_hyper(name: str, hyper_path: Path, server_url: str, site_name: str,
                  pat_name: str, pat_value: str) -> None:
    """Publish a .hyper file to the Streamlit Data project on Tableau Cloud."""
    server, auth = _sign_in(server_url, site_name, pat_name, pat_value)
    with server.auth.sign_in(auth):
        project_id = _find_project(server, _TARGET_PROJECT)
        ds = TSC.DatasourceItem(project_id, name=name)
        server.datasources.publish(ds, str(hyper_path), TSC.Server.PublishMode.Overwrite)
        print(f"  Published {name} to Tableau Cloud")


def download_hyper(name: str, dest_dir: Path, server_url: str, site_name: str,
                   pat_name: str, pat_value: str) -> Path:
    """Download a datasource from Tableau Cloud and extract the .hyper file."""
    server, auth = _sign_in(server_url, site_name, pat_name, pat_value)
    with server.auth.sign_in(auth):
        # Find the datasource by name
        ds_item = None
        for ds in TSC.Pager(server.datasources):
            if ds.name == name:
                ds_item = ds
                break
        if ds_item is None:
            raise FileNotFoundError(f"Datasource '{name}' not found on Tableau Cloud")

        # Download returns a .tdsx file (ZIP containing .hyper)
        with tempfile.TemporaryDirectory() as tmp:
            tdsx_path = server.datasources.download(ds_item.id, filepath=tmp)
            tdsx_path = Path(tdsx_path)

            dest_dir.mkdir(parents=True, exist_ok=True)
            hyper_path = dest_dir / f"{name}.hyper"

            with zipfile.ZipFile(tdsx_path) as zf:
                for member in zf.namelist():
                    if member.endswith(".hyper"):
                        with zf.open(member) as src, open(hyper_path, "wb") as dst:
                            dst.write(src.read())
                        break
                else:
                    raise FileNotFoundError(f"No .hyper file found inside {tdsx_path.name}")

    print(f"  Downloaded {name}.hyper from Tableau Cloud")
    return hyper_path
