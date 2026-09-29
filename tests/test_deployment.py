"""Tests for deployment configuration.

These guard two things that fail embarrassingly and late: a serverless
entry point that does not import, and a secret reaching a public
repository.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.pool import NullPool, QueuePool

from auction_portal.config import Settings
from auction_portal.db.session import build_engine

ROOT = Path(__file__).resolve().parents[1]

VALID = {
    "contact_email": "bot@example.com",
    "contact_url": "https://example.com/bot",
}


# --- the Vercel entry point ----------------------------------------------


@pytest.fixture(scope="module")
def vercel_app():
    """Import api/index.py exactly as Vercel would."""
    sys.path.insert(0, str(ROOT / "api"))
    try:
        from index import app  # noqa: PLC0415

        return app
    finally:
        sys.path.pop(0)


def test_vercel_entrypoint_imports(vercel_app):
    """If this breaks, the deploy fails at runtime rather than at build."""
    assert vercel_app.routes


def test_vercel_entrypoint_serves_pages(vercel_app):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    client = TestClient(vercel_app)
    for path in ("/robots.txt", "/bot"):
        assert client.get(path).status_code == 200


def test_vercel_config_is_valid_json():
    config = json.loads((ROOT / "vercel.json").read_text("utf-8"))
    assert config["builds"][0]["src"] == "api/index.py"


def test_vercel_config_bundles_templates_and_static():
    """Templates are not Python files, so they are only deployed if the
    build is told to include them."""
    config = json.loads((ROOT / "vercel.json").read_text("utf-8"))
    included = config["builds"][0]["config"]["includeFiles"]
    assert "web" in included


#: Runtime dependencies deliberately left out of the Vercel build, with
#: the reason. Anything else missing is drift and should fail.
VERCEL_EXCLUSIONS = {
    "uvicorn": "Vercel provides the ASGI server",
    "apscheduler": "the collector does not run on Vercel",
}


def requirements_packages() -> set[str]:
    """Package names from requirements.txt, ignoring comments."""
    names = set()
    for line in (ROOT / "requirements.txt").read_text("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line.split("==")[0].split("[")[0].strip().lower())
    return names


def pyproject_packages() -> set[str]:
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    # Split on a closing bracket at the start of a line. A plain "]" would
    # truncate at "psycopg[binary]" and silently check only half the list.
    block = re.split(r"\n\]", pyproject.split("dependencies = [", 1)[1], maxsplit=1)[0]
    names = set()
    for line in block.splitlines():
        line = line.split("#", 1)[0].strip().strip(",").strip('"')
        if line:
            names.add(line.split("==")[0].split("[")[0].strip().lower())
    return names


def test_requirements_matches_the_runtime_dependencies():
    """Vercel installs from requirements.txt; pyproject is the source of
    truth locally. Drift between them only shows up once deployed."""
    missing = pyproject_packages() - requirements_packages() - set(VERCEL_EXCLUSIONS)
    assert not missing, f"missing from requirements.txt: {sorted(missing)}"


def test_requirements_adds_nothing_unexpected():
    extra = requirements_packages() - pyproject_packages()
    assert not extra, f"in requirements.txt but not pyproject: {sorted(extra)}"


def test_scheduler_is_not_shipped_to_vercel():
    """The collector does not run there, so shipping apscheduler would
    only slow cold starts."""
    assert "apscheduler" not in requirements_packages()


# --- serverless database behaviour ---------------------------------------


def test_serverless_mode_avoids_connection_pooling():
    """Many short-lived instances each holding a pool would exhaust the
    database's connection limit."""
    engine = build_engine("postgresql+psycopg://u:p@h/db", serverless=True)
    assert isinstance(engine.pool, NullPool)


def test_normal_mode_still_pools():
    engine = build_engine("postgresql+psycopg://u:p@h/db", serverless=False)
    assert isinstance(engine.pool, QueuePool)


def test_serverless_defaults_to_off():
    assert Settings(**VALID).db_serverless is False


# --- nothing secret reaches the repository -------------------------------


@pytest.mark.parametrize("path", [".env", "data", ".pgsql", "logs", ".venv"])
def test_sensitive_paths_are_git_ignored(path):
    result = subprocess.run(
        ["git", "check-ignore", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{path} is NOT ignored and could be pushed"


def test_no_env_file_is_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()

    assert ".env" not in tracked
    assert ".env.example" in tracked  # the documented template is fine


# A real OpenAI key is a long run of key characters after the prefix.
# Test fixtures use obvious placeholders like 'sk-proj-THIS-MUST-NOT-APPEAR',
# which must not trip this check or it will be ignored.
_API_KEY = re.compile(r"sk-(?:proj|ant)-[A-Za-z0-9_\-]{40,}")


def test_no_api_key_in_tracked_files():
    """Guards against a key being committed and pushed to a public
    repository, where rotating it is the only remedy."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()

    offenders = []
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.suffix in {".pdf", ".png"}:
            continue
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        if _API_KEY.search(text):
            offenders.append(name)

    assert not offenders, f"API keys found in tracked files: {offenders}"


def test_the_api_key_check_would_catch_a_real_key():
    """A guard that cannot fail is worse than no guard."""
    real_looking = "sk-proj-" + "a1B2c3D4e5" * 6
    assert _API_KEY.search(real_looking)
    assert not _API_KEY.search("sk-proj-THIS-MUST-NOT-APPEAR")
