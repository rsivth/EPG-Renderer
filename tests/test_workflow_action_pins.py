"""Regressions for the external GitHub Actions used by the workflows.

Until 0.14.0.dev2, ci.yml referenced floating tags (``actions/checkout@v4``,
``actions/setup-python@v5``, ``actions/upload-artifact@v4``) whose releases target
Node.js 20, and every CI job warned about the deprecated runtime. publish-pypi.yml was
already pinned to full commits of Node.js 24 releases. Both workflows now follow one
rule: every external action is pinned to a full commit with its release tag as a
comment, and an action used by both workflows uses the same commit, so every CI run
exercises the action revisions a release will use.

Since 0.14.0.dev8 the rule covers every workflow file (ci.yml, release.yml and the
reusable windows-binaries.yml). References to local reusable workflows (``./...``) are
files of this repository at the same commit, not external actions.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = tuple(sorted((ROOT / ".github" / "workflows").glob("*.yml")))
PINNED = re.compile(r"^uses: [^@\s]+@[0-9a-f]{40} # v\d+(?:\.\d+)*$")
REFERENCE = re.compile(r"^uses: (?P<action>[^@\s]+)@(?P<ref>\S+)(?: # (?P<tag>\S+))?$")


def _action_lines(workflow: Path) -> list[str]:
    lines = [line.strip().removeprefix("- ") for line in workflow.read_text("utf-8").splitlines()]
    return [line for line in lines if line.startswith("uses:") and "uses: ./" not in line]


class WorkflowActionPinTests(unittest.TestCase):
    def test_all_three_workflows_are_checked(self) -> None:
        names = [workflow.name for workflow in WORKFLOWS]
        self.assertEqual(names, ["ci.yml", "release.yml", "windows-binaries.yml"])

    def test_every_external_action_in_every_workflow_is_pinned_to_a_tagged_commit(self) -> None:
        for workflow in WORKFLOWS:
            lines = _action_lines(workflow)
            self.assertGreaterEqual(len(lines), 1, workflow.name)
            for line in lines:
                with self.subTest(workflow=workflow.name, line=line):
                    self.assertRegex(line, PINNED)

    def test_workflows_use_one_revision_per_action(self) -> None:
        revisions: dict[str, set[tuple[str, str | None]]] = {}
        for workflow in WORKFLOWS:
            for line in _action_lines(workflow):
                match = REFERENCE.fullmatch(line)
                self.assertIsNotNone(match, line)
                assert match is not None
                revisions.setdefault(match["action"], set()).add((match["ref"], match["tag"]))
        for action, used in sorted(revisions.items()):
            with self.subTest(action=action):
                self.assertEqual(len(used), 1, sorted(used, key=str))

    def test_ci_no_longer_references_the_node20_releases_from_the_runner_warning(self) -> None:
        source = WORKFLOWS[0].read_text(encoding="utf-8")
        for reference in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/upload-artifact@v4",
        ):
            with self.subTest(reference=reference):
                self.assertNotIn(reference, source)


if __name__ == "__main__":
    unittest.main()
