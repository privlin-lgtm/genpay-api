"""
Architecture rules that import-linter can't express (see [tool.importlinter]
in pyproject.toml for the import-level contracts).

Every check is an AST scan, not a text grep, so comments and docstrings that
mention commit() or execute() don't count. Each failure message says the rule
and the reason, because that message is what tells whoever broke it (often an
agent running the suite) how to fix the code.

Each scanner also has a self-test against a known-bad snippet, and every
scanned directory must actually contain files: a check that silently scans
nothing would pass forever, which is the failure mode this file guards against.
"""

import ast
import tomllib
from importlib.util import find_spec
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "app"

# get_db() is the one place a request commits. seed_data.seed() runs once at
# startup with its own SessionLocal (no request, no get_db), so it commits for
# itself. Anything else that needs to commit is a design change, not an entry here.
COMMIT_ALLOWED = {
    "app/database/db.py",
    "app/database/seed_data.py",
}

# Packages that must talk to GenPay over HTTP only and never import the app.
# mcp_server/ doesn't exist yet; the read-only MCP server PR adds it and is held
# to this from its first commit.
HTTP_ONLY_PACKAGES = ["mcp_server"]


def _py_files(*dirs: Path) -> list[Path]:
    files = sorted(f for d in dirs for f in d.rglob("*.py"))
    assert files, f"No .py files found under {[str(d) for d in dirs]}: the check would scan nothing"
    return files


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- scanners -------------------------------------------------------------


def find_commit_calls(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    ]


def find_raw_sql(tree: ast.AST) -> list[tuple[int, str]]:
    """sqlalchemy.text imports/uses and any .execute(...) call."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy"):
            hits += [(node.lineno, f"from {node.module} import text") for a in node.names if a.name == "text"]
        elif isinstance(node, ast.Attribute) and node.attr == "text":
            base = node.value
            if isinstance(base, ast.Name) and base.id in {"sqlalchemy", "sa"}:
                hits.append((node.lineno, f"{base.id}.text"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            hits.append((node.lineno, ".execute(...)"))
    return hits


def find_app_imports(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [(node.lineno, a.name) for a in node.names if a.name == "app" or a.name.startswith("app.")]
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and (node.module == "app" or node.module.startswith("app."))
        ):
            hits.append((node.lineno, node.module))
    return hits


# --- the rules ------------------------------------------------------------


def test_only_get_db_commits():
    offenders = [
        f"{_rel(f)}:{line}"
        for f in _py_files(APP, REPO_ROOT / "scripts")
        if _rel(f) not in COMMIT_ALLOWED
        for line in find_commit_calls(_parse(f))
    ]
    assert not offenders, (
        "Only get_db() in app/database/db.py may commit: one request = one transaction, so any "
        "exception rolls back the whole request and a purchase or ledger posting is never left "
        "half-applied. Repositories flush(); get_db() commits. Remove the commit() at: "
        + ", ".join(offenders)
    )


def test_commit_allowlist_is_current():
    stale = [p for p in COMMIT_ALLOWED if not (REPO_ROOT / p).is_file()]
    assert not stale, f"COMMIT_ALLOWED names files that no longer exist, remove them: {stale}"


def test_no_raw_sql_in_api_or_services():
    offenders = [
        f"{_rel(f)}:{line} {what}"
        for f in _py_files(APP / "api", APP / "services")
        for line, what in find_raw_sql(_parse(f))
    ]
    assert not offenders, (
        "api and services must not run raw SQL (sqlalchemy.text or session.execute): repositories "
        "are the only layer that talks to the database, which keeps queries in one place and lets "
        "ledger_account_repository keep its atomic balance UPDATE. Move the query into a "
        "repository function at: " + ", ".join(offenders)
    )


@pytest.mark.parametrize("package", HTTP_ONLY_PACKAGES)
def test_http_only_packages_never_import_app(package):
    pkg_dir = REPO_ROOT / package
    if not pkg_dir.is_dir():
        pytest.skip(f"{package}/ doesn't exist yet; this check starts enforcing when it's added")
    offenders = [
        f"{_rel(f)}:{line} imports {mod}"
        for f in _py_files(pkg_dir)
        for line, mod in find_app_imports(_parse(f))
    ]
    assert not offenders, (
        f"{package} must not import app.*: it is a client of GenPay and may only call the API over "
        "HTTP, so it can't bypass auth, the api -> services -> repositories layering, or "
        "get_db()'s one-commit-per-request rule. Call the HTTP route instead at: " + ", ".join(offenders)
    )


# --- guards against checks that silently pass -----------------------------


def test_scanners_catch_known_bad_code():
    bad = ast.parse(
        "from sqlalchemy import text\n"
        "import sqlalchemy\n"
        "db.commit()\n"
        "db.execute(text('select 1'))\n"
        "sqlalchemy.text('x')\n"
        "from app.services import payment_service\n"
        "import app.models\n"
    )
    assert find_commit_calls(bad) == [3]
    assert [line for line, _ in find_raw_sql(bad)] == [1, 4, 5]
    assert [line for line, _ in find_app_imports(bad)] == [6, 7]


def test_scanners_ignore_comments_docstrings_and_lookalikes():
    ok = ast.parse(
        '"""Repositories never call db.commit() or db.execute(text(...))."""\n'
        "# db.commit()\n"
        "from apparatus import thing\n"
        "from . import app\n"
        "from sqlalchemy import select\n"
    )
    assert find_commit_calls(ok) == []
    assert find_raw_sql(ok) == []
    assert find_app_imports(ok) == []


def test_importlinter_contracts_name_real_modules():
    """
    import-linter can pass a contract whose module name is misspelled or was
    renamed, because nothing then imports the module it forbids. Fail here
    instead if any module a contract names can't be found.
    """
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["importlinter"]
    contracts = config["contracts"]
    assert contracts, "No import-linter contracts configured"

    names: set[str] = set(config["root_packages"])
    for contract in contracts:
        for key in ("layers", "source_modules", "forbidden_modules"):
            names.update(contract.get(key, []))

    missing = sorted(n for n in names if find_spec(n) is None)
    assert not missing, f"import-linter contracts name modules that don't exist: {missing}"
