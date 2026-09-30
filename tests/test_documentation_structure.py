"""Regressions for the audience-oriented documentation structure.

Until 0.14.0.dev6 installation steps were spread over the README, the GUI guide, the
Python vignette and the documentation index; the README mixed GUI and developer
downloads in one table and advised keeping SVG unless a raster image was required.
Since 0.14.0.dev7 docs/INSTALLATION.md is the only page with installation steps, the
README addresses GUI users first and developers second, and the GUI guide recommends
PNG or JPG for slides and SVG for editing in a vector graphics program.
"""

from __future__ import annotations

import fnmatch
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RELEASE_DOWNLOAD = "https://github.com/rsivth/EPG-Renderer/releases/download/"
WHEEL_URL = RELEASE_DOWNLOAD + "vX.Y.Z/epg_renderer-X.Y.Z-py3-none-any.whl"
README = ROOT / "README.md"
INSTALLATION = DOCS / "INSTALLATION.md"
# Contributor setup in DEVELOPMENT.md is not user installation and may repeat commands.
USER_PAGES = tuple(
    path
    for path in (README, *sorted(DOCS.glob("*.md")))
    if path.name not in {"INSTALLATION.md", "DEVELOPMENT.md"}
)
# Since 0.14.0.dev10 the package is installed from the release wheel address.
INSTALLATION_ONLY = (
    '"epg-renderer @ ',
    '"epg-renderer[raster] @ ',
    '".[raster]"',
    "pip install .",
    "Get-FileHash",
    "launch_gui.py",
    "-m tkinter",
    "epg-render-gui",
    "-m epg_renderer.gui",
    "SmartScreen",
    "Run anyway",
)
GUI_SECTION = "## Create a figure without programming"
DEVELOPER_SECTION = "## Use EPG-Renderer in your software"


def _section(text: str, heading: str) -> str:
    return text.split(heading + "\n", 1)[1].split("\n## ", 1)[0]


def _github_anchor(heading: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", heading.strip().lower()).replace(" ", "-")


class InstallationGuideTests(unittest.TestCase):
    def test_installation_steps_live_only_in_the_installation_guide(self) -> None:
        guide = INSTALLATION.read_text(encoding="utf-8")
        for phrase in INSTALLATION_ONLY:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guide)
                pages = [p.name for p in USER_PAGES if phrase in p.read_text("utf-8")]
                self.assertEqual(pages, [])

    def test_user_entry_points_link_the_installation_guide(self) -> None:
        readme = README.read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/rsivth/EPG-Renderer/blob/main/docs/INSTALLATION.md", readme
        )
        for name in ("index.md", "GETTING_STARTED.md", "PYTHON.md", "CLI.md"):
            with self.subTest(page=name):
                self.assertIn("](INSTALLATION.md", (DOCS / name).read_text("utf-8"))

    def test_links_into_the_installation_guide_name_existing_sections(self) -> None:
        anchors = {
            _github_anchor(line.lstrip("#"))
            for line in INSTALLATION.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        }
        for page in (README, *DOCS.glob("*.md")):
            for anchor in re.findall(r"INSTALLATION\.md#([a-z0-9-]+)", page.read_text("utf-8")):
                with self.subTest(page=page.name, anchor=anchor):
                    self.assertIn(anchor, anchors)


class AudienceStructureTests(unittest.TestCase):
    def test_readme_addresses_gui_users_before_developers(self) -> None:
        readme = README.read_text(encoding="utf-8")
        self.assertLess(readme.index(GUI_SECTION), readme.index(DEVELOPER_SECTION))
        gui = _section(readme, GUI_SECTION)
        self.assertIn("docs/GETTING_STARTED.md", gui)
        self.assertIn("docs/INSTALLATION.md", gui)
        developer = _section(readme, DEVELOPER_SECTION)
        for target in ("docs/INSTALLATION.md", "docs/CLI.md", "docs/PYTHON.md", "docs/API.md"):
            with self.subTest(target=target):
                self.assertIn(target, developer + readme.split(DEVELOPER_SECTION, 1)[1])

    def test_format_advice_matches_the_purpose_of_each_format(self) -> None:
        guide = (DOCS / "GETTING_STARTED.md").read_text(encoding="utf-8")
        formats = _section(guide, "## Choose the output format")
        for phrase in ("PowerPoint", "PNG", "JPG", "SVG", "Inkscape"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, formats)
        readme = README.read_text(encoding="utf-8")
        self.assertNotIn("Keep SVG selected unless", readme + guide)
        self.assertIn("PNG or JPG", _section(readme, GUI_SECTION))

    def test_index_routes_to_the_installation_guide(self) -> None:
        index = (DOCS / "index.md").read_text(encoding="utf-8")
        self.assertIn("](INSTALLATION.md)", index)


class ReleaseWheelInstallationTests(unittest.TestCase):
    """Since 0.14.0.dev10 the Python package is installed from the GitHub Release.

    Until 0.14.0.dev9 the README and the installation guide told developers to run
    ``pip install epg-renderer`` and called the package available on PyPI. The project
    has never been published there and the name is unregistered: anyone could publish
    a package under it, and readers following our instructions would install that code.
    """

    PAGES = (README, *sorted(DOCS.glob("*.md")))

    def test_no_page_installs_the_package_by_bare_name(self) -> None:
        findings = [
            f"{page.name}: {line.strip()}"
            for page in self.PAGES
            for line in page.read_text(encoding="utf-8").splitlines()
            if "pip install" in line
            and re.search(r"\bepg-renderer\b", line)
            and f" @ {RELEASE_DOWNLOAD}" not in line
        ]
        self.assertEqual(findings, [])

    def test_no_page_claims_the_package_is_on_pypi(self) -> None:
        for page in self.PAGES:
            text = " ".join(page.read_text(encoding="utf-8").split())
            for claim in ("is on PyPI", "from PyPI"):
                with self.subTest(page=page.name, claim=claim):
                    self.assertNotIn(claim, text)

    def test_installation_guide_installs_the_release_wheel(self) -> None:
        guide = INSTALLATION.read_text(encoding="utf-8")
        section = _section(guide, "## Python package")
        self.assertIn(f'python -m pip install "epg-renderer @ {WHEEL_URL}"', section)
        self.assertIn(f'python -m pip install "epg-renderer[raster] @ {WHEEL_URL}"', section)
        self.assertIn("not on PyPI", section)

    def test_documented_wheel_address_matches_the_release_assets(self) -> None:
        # release.yml requires the tag v<version>; github_release.py uploads the wheel
        # under its built name, which must match the documented file name.
        version = "1.2.3"
        tag, wheel = WHEEL_URL.removeprefix(RELEASE_DOWNLOAD).split("/")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
        self.assertIn('"$GITHUB_REF_NAME" != "v$version"', workflow)
        self.assertEqual(tag.replace("X.Y.Z", version), f"v{version}")
        assembler = (ROOT / "tools" / "github_release.py").read_text(encoding="utf-8")
        pattern = 'f"epg_renderer-{version}-*.whl"'
        self.assertIn(pattern, assembler)
        self.assertTrue(
            fnmatch.fnmatchcase(wheel.replace("X.Y.Z", version), f"epg_renderer-{version}-*.whl")
        )
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "epg-renderer"', pyproject)


if __name__ == "__main__":
    unittest.main()
