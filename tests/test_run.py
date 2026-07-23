"""Tests for src.pipeline.run resilience behaviour.

These cover the 2026-07 failure modes: a run that published nothing because
its first dataset could not connect, and a run that hung forever mid-dataset.
"""

import sys
import threading
from contextlib import contextmanager

import pytest

from src.pipeline import run as run_mod


class _FakeConn:
    def execute(self, *_args, **_kwargs):
        return None


class _FakeEngine:
    @contextmanager
    def connect(self):
        yield _FakeConn()


DATASETS_STUB = {
    "ds_rept_a": {"db_section": "rept"},
    "ds_rept_b": {"db_section": "rept"},
    "ds_dwh_a": {"db_section": "dwhdb"},
}


@pytest.fixture
def stub_datasets(monkeypatch):
    monkeypatch.setattr(run_mod, "DATASETS", DATASETS_STUB)
    return DATASETS_STUB


def _run(monkeypatch, argv, *, disable_watchdog=True):
    """Invoke main() with argv.

    Watchdog off by default: tests that are not about the watchdog would
    otherwise each leak a real thread sleeping for DEFAULT_TIMEOUT_SECONDS.
    """
    if disable_watchdog:
        argv = [*argv, "--timeout", "0"]
    monkeypatch.setattr(sys, "argv", ["run", *argv])
    return run_mod.main()


# --- _brief -----------------------------------------------------------------

def test_brief_keeps_only_the_first_line():
    exc = Exception("ORA-12545: Connect failed\nHelp: https://example\nmore noise")
    assert run_mod._brief(exc) == "ORA-12545: Connect failed"


def test_brief_falls_back_to_class_name_when_message_empty():
    assert run_mod._brief(ValueError("")) == "ValueError"


# --- failure isolation (fix 1) ----------------------------------------------

@pytest.mark.usefixtures("stub_datasets")
def test_one_dataset_failure_does_not_abort_the_rest(monkeypatch, capsys):
    """The 12 zero-publish days: first dataset raised, all 27 others were skipped."""
    attempted = []

    def fake_extract(name):
        attempted.append(name)
        if name == "ds_rept_a":
            raise RuntimeError("ORA-12545: Connect failed because target host does not exist")
        return f"/tmp/{name}.hyper"

    monkeypatch.setattr(run_mod, "get_engine", lambda _section: _FakeEngine())
    monkeypatch.setattr(run_mod, "extract_dataset", fake_extract)

    code = _run(monkeypatch, ["--extract-only"])

    # Every dataset was attempted despite the first one raising.
    assert attempted == ["ds_rept_a", "ds_rept_b", "ds_dwh_a"]
    assert code == run_mod.EXIT_INCOMPLETE
    out = capsys.readouterr()
    assert "2 succeeded, 1 failed" in out.out
    assert "ORA-12545" in out.out


@pytest.mark.usefixtures("stub_datasets")
def test_all_datasets_succeeding_returns_exit_ok(monkeypatch):
    monkeypatch.setattr(run_mod, "get_engine", lambda _section: _FakeEngine())
    monkeypatch.setattr(run_mod, "extract_dataset", lambda name: f"/tmp/{name}.hyper")
    assert _run(monkeypatch, ["--extract-only"]) == run_mod.EXIT_OK


# --- preflight (fix 4) ------------------------------------------------------

@pytest.mark.usefixtures("stub_datasets")
def test_unreachable_section_skips_only_its_own_datasets(monkeypatch, capsys):
    """REPT down but DWHDB up should still refresh the DWHDB dataset."""
    def fake_get_engine(section):
        if section == "rept":
            raise RuntimeError("ORA-12545: Connect failed because target host does not exist")
        return _FakeEngine()

    extracted = []
    monkeypatch.setattr(run_mod, "get_engine", fake_get_engine)
    monkeypatch.setattr(run_mod, "extract_dataset", lambda n: extracted.append(n) or f"/tmp/{n}.hyper")

    code = _run(monkeypatch, ["--extract-only"])

    assert extracted == ["ds_dwh_a"]
    assert code == run_mod.EXIT_INCOMPLETE
    out = capsys.readouterr().out
    assert "rept: UNREACHABLE" in out
    assert "dwhdb: reachable" in out


@pytest.mark.usefixtures("stub_datasets")
def test_every_section_unreachable_exits_without_extracting(monkeypatch, capsys):
    """Off-VPN noon runs: exit cleanly, not with 28 stack traces."""
    def fake_get_engine(_section):
        raise RuntimeError("ORA-12545: Connect failed because target host does not exist")

    def fail_if_called(_name):
        raise AssertionError("extract must not run when nothing is reachable")

    monkeypatch.setattr(run_mod, "get_engine", fake_get_engine)
    monkeypatch.setattr(run_mod, "extract_dataset", fail_if_called)

    assert _run(monkeypatch, ["--extract-only"]) == run_mod.EXIT_UNREACHABLE
    assert "nothing to do" in capsys.readouterr().out


@pytest.mark.usefixtures("stub_datasets")
def test_no_preflight_flag_skips_the_probe(monkeypatch):
    def fail_if_called(_section):
        raise AssertionError("preflight must not connect when --no-preflight is set")

    monkeypatch.setattr(run_mod, "get_engine", fail_if_called)
    monkeypatch.setattr(run_mod, "extract_dataset", lambda name: f"/tmp/{name}.hyper")
    assert _run(monkeypatch, ["--extract-only", "--no-preflight"]) == run_mod.EXIT_OK


# --- watchdog (fix 3) -------------------------------------------------------

def test_watchdog_runs_as_a_daemon_thread():
    """Daemon, so a healthy run is never held open by the pending timer."""
    before = sum(1 for t in threading.enumerate() if t.name == "pipeline-watchdog")
    run_mod._start_watchdog(3600)
    watchdogs = [t for t in threading.enumerate() if t.name == "pipeline-watchdog"]
    assert len(watchdogs) == before + 1
    assert all(t.daemon for t in watchdogs)


@pytest.mark.usefixtures("stub_datasets")
def test_timeout_zero_disables_the_watchdog(monkeypatch):
    started = []
    monkeypatch.setattr(run_mod, "_start_watchdog", lambda s: started.append(s))
    monkeypatch.setattr(run_mod, "get_engine", lambda _section: _FakeEngine())
    monkeypatch.setattr(run_mod, "extract_dataset", lambda name: f"/tmp/{name}.hyper")

    _run(monkeypatch, ["--extract-only", "--timeout", "0"], disable_watchdog=False)
    assert started == []

    _run(monkeypatch, ["--extract-only"], disable_watchdog=False)
    assert started == [run_mod.DEFAULT_TIMEOUT_SECONDS]
