"""Run Python regressions in a virtual environment and save a truthful verification record."""
from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
import unittest

from apology.paths import ROOT
from apology.schema import new_run, write_json


def main():
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Run this command with the project's virtual-environment Python.")
    paths = [p for folder in ("apology", "experiments", "tests") for p in (ROOT / folder).glob("*.py")] + [ROOT / "app.py"]
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "successful": result.wasSuccessful(), "python_files_parsed": len(paths),
              "virtual_environment": True, "python_executable": sys.executable,
              "lean_executable_on_path": shutil.which("lean"),
              "marimo_installed_in_venv": importlib.util.find_spec("marimo") is not None,
              "live_lean_checks": "not_executed_by_this_command",
              "marimo_runtime": "not_executed_by_this_command",
              "mocked_execution_tests": "control flow only; not Lean proof validation", "actual_api_usd": 0}
    folder, manifest = new_run(ROOT, "python_regression_verification", {})
    write_json(folder / "verification.json", report)
    write_json(folder / "manifest.json", manifest)
    write_json(ROOT / "results" / "evaluation" / "verification.json", report)
    print(f"Verification record: {folder}")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
