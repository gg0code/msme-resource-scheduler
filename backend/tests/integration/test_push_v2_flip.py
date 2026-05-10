# tests/integration/test_push_v2_flip.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 slice 2D-flip — integration test for the
# scripts/push_v2_flip.py CLI. Verifies the flag-flip mechanism
# without exercising the actual production .env: each test passes
# --env-file pointing to a tempfile.
#
# WHO CALLS THIS FILE
# - pytest, marked @pytest.mark.integration. Runs explicitly via
#   `pytest tests/integration/test_push_v2_flip.py -v`.
#
# WHAT THIS FILE CALLS
# - scripts/push_v2_flip.py (imported as a module via importlib so
#   the file's hyphen-free filename works as a Python module name).

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _import_flip_module():
    """Load scripts/push_v2_flip.py as a module.

    Called by:    every test in this file.
    Calls into:   importlib.util.spec_from_file_location.
    Side effects: registers the module under the name push_v2_flip in
                  sys.modules so subsequent imports are cached.
    """
    if "push_v2_flip" in sys.modules:
        return sys.modules["push_v2_flip"]
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "push_v2_flip.py"
    spec = importlib.util.spec_from_file_location("push_v2_flip", script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["push_v2_flip"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def flip(tmp_path):
    """Yield (module, env_path) for a per-test temp env file.

    Called by:    every test in this file.
    Calls into:   _import_flip_module, tmp_path (pytest builtin).
    Side effects: creates a temp file under tmp_path; pytest cleans up.
    """
    module = _import_flip_module()
    env_path = tmp_path / ".env"
    return module, env_path


def test_enable_writes_true_to_empty_file(flip):
    """`--enable` against a missing .env creates it and writes
    PUSH_V2_ENABLED=true."""
    module, env_path = flip
    assert not env_path.exists()

    rc = module.main_cli(["--enable", "--env-file", str(env_path)])

    assert rc == 0
    assert env_path.exists()
    assert "PUSH_V2_ENABLED=true" in env_path.read_text(encoding="utf-8")


def test_disable_writes_false(flip):
    """`--disable` writes PUSH_V2_ENABLED=false."""
    module, env_path = flip

    rc = module.main_cli(["--disable", "--env-file", str(env_path)])

    assert rc == 0
    assert "PUSH_V2_ENABLED=false" in env_path.read_text(encoding="utf-8")


def test_enable_replaces_existing_line(flip):
    """`--enable` on an .env already carrying the flag replaces the
    line in place (does NOT append a duplicate)."""
    module, env_path = flip
    env_path.write_text(
        "OTHER=value\nPUSH_V2_ENABLED=false\nMORE=stuff\n",
        encoding="utf-8",
    )

    module.main_cli(["--enable", "--env-file", str(env_path)])

    text = env_path.read_text(encoding="utf-8")
    # Exactly one PUSH_V2_ENABLED line.
    occurrences = sum(1 for line in text.splitlines() if "PUSH_V2_ENABLED=" in line)
    assert occurrences == 1
    assert "PUSH_V2_ENABLED=true" in text
    # Other lines preserved.
    assert "OTHER=value" in text
    assert "MORE=stuff" in text


def test_status_round_trip(flip, capsys):
    """`--status` reads back the value `--enable` / `--disable` wrote."""
    module, env_path = flip

    module.main_cli(["--enable", "--env-file", str(env_path)])
    capsys.readouterr()  # drain enable's stdout

    rc = module.main_cli(["--status", "--env-file", str(env_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "PUSH_V2_ENABLED=true" in out

    module.main_cli(["--disable", "--env-file", str(env_path)])
    capsys.readouterr()
    module.main_cli(["--status", "--env-file", str(env_path)])
    out2 = capsys.readouterr().out
    assert "PUSH_V2_ENABLED=false" in out2


def test_status_on_missing_file_reports_implicit_default(flip, capsys):
    """`--status` against a missing .env prints the implicit-false note
    (does not crash)."""
    module, env_path = flip
    # env_path is the path; tmp_path itself exists, but env_path does not.
    assert not env_path.exists()

    rc = module.main_cli(["--status", "--env-file", str(env_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "implicit default: false" in out


def test_set_flag_function_returns_literal(flip):
    """The library-level `set_flag(True | False, env_path)` returns the
    written literal string. Useful for callers driving the flip from
    Python rather than the CLI."""
    module, env_path = flip

    written_true = module.set_flag(True, env_path)
    assert written_true == "true"
    assert module.read_flag(env_path) == "true"

    written_false = module.set_flag(False, env_path)
    assert written_false == "false"
    assert module.read_flag(env_path) == "false"


def test_atomic_write_leaves_no_temp_files(flip):
    """After --enable + --disable + --enable, the .env directory should
    contain only the .env file plus pytest's tmp_path internals — no
    stray .env.flip.* tempfiles."""
    module, env_path = flip
    module.main_cli(["--enable", "--env-file", str(env_path)])
    module.main_cli(["--disable", "--env-file", str(env_path)])
    module.main_cli(["--enable", "--env-file", str(env_path)])

    leftovers = [
        p for p in env_path.parent.iterdir()
        if p.name.startswith(".env.flip.")
    ]
    assert leftovers == [], (
        f"Atomic write left temp files behind: {leftovers}"
    )
