from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import database  # noqa: E402
from app.evaluator import store  # noqa: E402
from app.evaluator.official_seed import seed_official_eval_suites  # noqa: E402


@contextmanager
def isolated_eval_database():
    old_data_dir = database.DATA_DIR
    old_db_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "toograph.db"
        try:
            yield
        finally:
            database.DATA_DIR = old_data_dir
            database.DB_PATH = old_db_path


def validate_suite(suite_id: str) -> list[str]:
    errors: list[str] = []
    try:
        suite = store.load_eval_suite(suite_id)
    except KeyError:
        return [f"Eval suite '{suite_id}' was not seeded."]

    cases = store.list_eval_cases(suite_id)
    if not cases:
        errors.append(f"Eval suite '{suite_id}' has no cases.")
    for case in cases:
        case_id = str(case.get("case_id") or "").strip()
        if not case_id:
            errors.append(f"Eval suite '{suite_id}' contains a case without case_id.")
        checks = case.get("checks")
        if not isinstance(checks, list) or not checks:
            errors.append(f"Eval case '{suite_id}/{case_id or '<missing>'}' has no checks.")
    return errors


def main(argv: list[str]) -> int:
    suite_ids = [item.strip() for item in argv if item.strip()]
    if not suite_ids:
        print("Usage: python scripts/official_eval_suite_gate.py <suite_id> [suite_id...]", file=sys.stderr)
        return 2

    with isolated_eval_database():
        seed_official_eval_suites()
        errors: list[str] = []
        for suite_id in suite_ids:
            errors.extend(validate_suite(suite_id))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    for suite_id in suite_ids:
        print(f"official eval suite ok: {suite_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
