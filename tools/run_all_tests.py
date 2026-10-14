"""Discover and run the complete current EPG-Renderer test suite."""

from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator
from pathlib import Path


class TestDiscoveryError(RuntimeError):
    """Raised when test discovery produces duplicate identifiers."""


def iter_tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield every test case from a possibly nested unittest suite."""

    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def discover_tests(
    root: Path,
    loader: unittest.TestLoader | None = None,
) -> tuple[unittest.TestSuite, tuple[str, ...]]:
    """Discover every current ``test*.py`` module without exclusions."""

    selected_loader = loader or unittest.defaultTestLoader
    suite = selected_loader.discover(str(root / "tests"), pattern="test*.py")
    tests = tuple(iter_tests(suite))
    test_ids = tuple(test.id() for test in tests)
    if len(test_ids) != len(set(test_ids)):
        duplicates = sorted({test_id for test_id in test_ids if test_ids.count(test_id) > 1})
        raise TestDiscoveryError(f"Duplicate discovered test IDs: {duplicates}")
    return unittest.TestSuite(tests), test_ids


def _base_id(test: object) -> str:
    """Return the identifier of a test, or of the test that owns a sub-test."""

    owner = getattr(test, "test_case", test)
    return str(owner.id()) if hasattr(owner, "id") else str(owner)


def main() -> int:
    """Discover and run every current test exactly once."""

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tests"))

    try:
        suite, test_ids = discover_tests(root)
    except TestDiscoveryError as exc:
        print(f"Test discovery error: {exc}", file=sys.stderr)
        return 2

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print()
    failed = {_base_id(test) for test, _ in result.failures}
    errored = {_base_id(test) for test, _ in result.errors} - failed
    skipped = {_base_id(test) for test, _ in result.skipped} - failed - errored
    print(f"Tests run: {len(test_ids)}")
    print(f"Passed: {len(test_ids) - len(failed | errored | skipped)}")
    print(f"Failed: {len(failed)}")
    print(f"Errors: {len(errored)}")
    print(f"Skipped: {len(skipped)}")
    for test, reason in result.skipped:
        print(f"  skipped {test.id()}: {reason}")
    print(f"Result: {'PASSED' if result.wasSuccessful() else 'FAILED'}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
