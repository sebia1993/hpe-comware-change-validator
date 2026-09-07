from __future__ import annotations

import re
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile

from backbone_state_tracker.tools.verify_release_package import (
    COMMON_REQUIRED,
    FORBIDDEN_PATTERNS,
    SOURCE_REQUIRED,
    WINDOWS_EXE_REQUIRED,
    WINDOWS_REQUIRED,
    verify_release_package,
)
from backbone_state_tracker.tools.write_release_manifest import (
    file_sha256,
    write_package_checksum,
    write_release_manifest,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
CORE_ENTRY_PREFIX = "backbone_state_tracker/core/"
CORE_ENTRY_PATTERN = re.compile(r'"(backbone_state_tracker/core/[^"]+\.py)"')
CONFIG_ENTRY_PREFIX = "backbone_state_tracker/config/"
CONFIG_ENTRY_PATTERN = re.compile(r'"(backbone_state_tracker/config/[^"]+)"')
DOC_ENTRY_PREFIX = "backbone_state_tracker/docs/"
DOC_ENTRY_PATTERN = re.compile(r'"(backbone_state_tracker/docs/[^"]+)"')
TEST_ENTRY_PREFIX = "backbone_state_tracker/tests/"
TEST_ENTRY_PATTERN = re.compile(r'"(backbone_state_tracker/tests/test_[^"]+\.py)"')
TOOL_ENTRY_PREFIX = "backbone_state_tracker/tools/"
TOOL_ENTRY_PATTERN = re.compile(r'"(backbone_state_tracker/tools/[^"]+\.(?:py|ps1))"')


def _write_zip(path: Path, entries: dict[str, str | bytes]) -> None:
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def _write_zip_items(path: Path, entries: list[tuple[str, str | bytes]]) -> None:
    with ZipFile(path, "w") as archive:
        for name, content in entries:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(name, content)


def _common_entries() -> dict[str, str]:
    return {
        "backbone_state_tracker/PACKAGE_INFO.txt": "package",
        "backbone_state_tracker/README.md": "readme",
        "backbone_state_tracker/RELEASE_NOTES.md": "release notes policy",
        "backbone_state_tracker/CHANGELOG.md": "changelog",
        "backbone_state_tracker/config/analysis_rules.yaml": "analysis rules",
        "backbone_state_tracker/config/commands.yaml": "commands",
        "backbone_state_tracker/config/devices.example.yaml": "devices example",
        "backbone_state_tracker/config/known_hosts.example": "known hosts example",
        "backbone_state_tracker/config/mock_profiles.yaml": "mock profiles",
        "backbone_state_tracker/docs/ARCHITECTURE.md": "architecture",
        "backbone_state_tracker/docs/CHANGE_VALIDATION_LOGIC.md": "change validation logic",
        "backbone_state_tracker/docs/VALIDATION_REPORT.md": "validation report",
        "backbone_state_tracker/docs/PORTFOLIO_REVIEW_KO.md": "portfolio review",
        "backbone_state_tracker/docs/USER_GUIDE.md": "user md",
        "backbone_state_tracker/docs/USER_GUIDE.html": "user html",
        "backbone_state_tracker/docs/COMMAND_GUIDE.md": "command md",
        "backbone_state_tracker/docs/COMMAND_GUIDE.html": "command html",
        "backbone_state_tracker/docs/DEVELOPER_GUIDE_BEGINNER.md": "dev md",
        "backbone_state_tracker/docs/DEVELOPER_GUIDE_BEGINNER.html": "dev html",
        "backbone_state_tracker/docs/VERSION_HISTORY.md": "history md",
        "backbone_state_tracker/docs/VERSION_HISTORY.html": "history html",
        "backbone_state_tracker/docs/RELEASE_CHECKLIST.md": "release checklist md",
        "backbone_state_tracker/docs/RELEASE_CHECKLIST.html": "release checklist html",
        "backbone_state_tracker/docs/DIAGNOSTIC_ARCHITECTURE_PROPOSAL.md": "diagnostic proposal md",
        "backbone_state_tracker/docs/DIAGNOSTIC_ARCHITECTURE_PROPOSAL.html": "diagnostic proposal html",
        "backbone_state_tracker/docs/DIAGNOSTIC_MODE_GUIDE.md": "diagnostic mode md",
        "backbone_state_tracker/docs/DIAGNOSTIC_MODE_GUIDE.html": "diagnostic mode html",
        "backbone_state_tracker/docs/ERROR_CODE_CATALOG.md": "error catalog md",
        "backbone_state_tracker/docs/ERROR_CODE_CATALOG.html": "error catalog html",
        "backbone_state_tracker/docs/images/settings-collection.png": "settings image",
        "backbone_state_tracker/docs/images/compare-results.png": "compare image",
        "backbone_state_tracker/docs/images/work-log.png": "log image",
    }


def _source_entries() -> dict[str, str]:
    entries = _common_entries()
    entries.update(
        {
            "backbone_state_tracker/__init__.py": "package init",
            "backbone_state_tracker/app.py": "app",
            "backbone_state_tracker/webapp_launcher.py": "webapp launcher",
            "backbone_state_tracker/LICENSE": "MIT license",
            "backbone_state_tracker/SECURITY.md": "security policy",
            "backbone_state_tracker/DEVELOPMENT.md": "development policy",
            "backbone_state_tracker/requirements.txt": "requirements",
            "backbone_state_tracker/requirements-dev.txt": "development requirements",
            "backbone_state_tracker/requirements-runtime.lock": "runtime lock",
            "backbone_state_tracker/requirements-windows.lock": "windows lock",
            "backbone_state_tracker/core/__init__.py": "core init",
            "backbone_state_tracker/core/analysis_rules.py": "analysis rules",
            "backbone_state_tracker/core/collector.py": "collector",
            "backbone_state_tracker/core/command_safety.py": "command safety",
            "backbone_state_tracker/core/config.py": "config",
            "backbone_state_tracker/core/connectivity.py": "connectivity",
            "backbone_state_tracker/core/diagnostics/__init__.py": "diagnostics init",
            "backbone_state_tracker/core/diagnostics/codes.py": "diagnostics codes",
            "backbone_state_tracker/core/diagnostics/events.py": "diagnostics events",
            "backbone_state_tracker/core/diagnostics/recorder.py": "diagnostics recorder",
            "backbone_state_tracker/core/diagnostics/report.py": "diagnostics report",
            "backbone_state_tracker/core/diagnostics/runner.py": "diagnostics runner",
            "backbone_state_tracker/core/diff_engine.py": "diff engine",
            "backbone_state_tracker/core/gui.py": "gui",
            "backbone_state_tracker/core/mock_validation.py": "mock validation",
            "backbone_state_tracker/core/mockserver/__init__.py": "mockserver init",
            "backbone_state_tracker/core/mockserver/profiles.py": "mockserver profiles",
            "backbone_state_tracker/core/mockserver/runner.py": "mockserver runner",
            "backbone_state_tracker/core/mockserver/ssh_server.py": "mockserver ssh",
            "backbone_state_tracker/core/mockserver/telnet_server.py": "mockserver telnet",
            "backbone_state_tracker/core/models.py": "models",
            "backbone_state_tracker/core/paths.py": "paths",
            "backbone_state_tracker/core/preflight.py": "preflight",
            "backbone_state_tracker/core/redaction.py": "redaction",
            "backbone_state_tracker/core/report_bundle.py": "report bundle",
            "backbone_state_tracker/core/reporter.py": "reporter",
            "backbone_state_tracker/core/snapshot.py": "snapshot",
            "backbone_state_tracker/core/version.py": "version",
            "backbone_state_tracker/core/webapp.py": "webapp",
            "backbone_state_tracker/core/workflow.py": "workflow",
            "backbone_state_tracker/tools/build_release.ps1": "source build",
            "backbone_state_tracker/tools/build_windows_exe.ps1": "exe build",
            "backbone_state_tracker/tools/stamp_sbom_identity.py": "SBOM identity tool",
            "backbone_state_tracker/tools/write_release_manifest.py": "manifest tool",
            "backbone_state_tracker/tools/verify_release_package.py": "verifier",
            "backbone_state_tracker/tools/verify_release_package.ps1": "powershell verifier",
            "backbone_state_tracker/tools/verify_release_assets.py": "asset verifier",
            "backbone_state_tracker/tests/test_analysis_rules.py": "analysis rules tests",
            "backbone_state_tracker/tests/test_cli_output_encoding.py": "cli output encoding tests",
            "backbone_state_tracker/tests/test_collection_security.py": "collection security tests",
            "backbone_state_tracker/tests/test_diagnostics_codes.py": "diagnostic code tests",
            "backbone_state_tracker/tests/test_diagnostics_report.py": "diagnostic report tests",
            "backbone_state_tracker/tests/test_diff_engine.py": "diff engine tests",
            "backbone_state_tracker/tests/test_documentation.py": "documentation tests",
            "backbone_state_tracker/tests/test_gui_formatting.py": "gui formatting tests",
            "backbone_state_tracker/tests/test_mock_collector_integration.py": "mock collector integration tests",
            "backbone_state_tracker/tests/test_mock_validation.py": "mock validation tests",
            "backbone_state_tracker/tests/test_mock_profiles.py": "mock profile tests",
            "backbone_state_tracker/tests/test_mock_ssh_server.py": "mock ssh tests",
            "backbone_state_tracker/tests/test_mock_telnet_server.py": "mock telnet tests",
            "backbone_state_tracker/tests/test_preflight.py": "preflight tests",
            "backbone_state_tracker/tests/test_redaction.py": "redaction tests",
            "backbone_state_tracker/tests/test_release_manifest.py": "manifest tests",
            "backbone_state_tracker/tests/test_release_assets.py": "release asset tests",
            "backbone_state_tracker/tests/test_release_package_verifier.py": "verifier tests",
            "backbone_state_tracker/tests/test_reporter.py": "reporter tests",
            "backbone_state_tracker/tests/test_snapshot.py": "snapshot tests",
            "backbone_state_tracker/tests/test_webapp.py": "webapp tests",
            "backbone_state_tracker/tests/test_workflow.py": "workflow tests",
        }
    )
    return entries


def _windows_entries() -> dict[str, str | bytes]:
    return {
        "backbone_state_tracker/PACKAGE_INFO.txt": "package",
        "backbone_state_tracker/README_START_HERE_KO.txt": "start here",
        "backbone_state_tracker/LICENSE": "MIT license",
        "backbone_state_tracker/gui/BackboneStateTracker.exe": b"fake gui executable payload",
        "backbone_state_tracker/gui/README_GUI_KO.txt": "gui guide",
        "backbone_state_tracker/gui/config/analysis_rules.yaml": "analysis rules",
        "backbone_state_tracker/gui/config/commands.yaml": "commands",
        "backbone_state_tracker/gui/config/devices.example.yaml": "devices example",
        "backbone_state_tracker/gui/config/known_hosts.example": "known hosts example",
        "backbone_state_tracker/gui/config/mock_profiles.yaml": "mock profiles",
        "backbone_state_tracker/web/README_WEB_KO.txt": "web guide",
        "backbone_state_tracker/web/start_webapp.cmd": "start webapp",
        "backbone_state_tracker/web/runtime/BackboneWebApp.exe": b"fake webapp executable payload",
        "backbone_state_tracker/web/config/analysis_rules.yaml": "analysis rules",
        "backbone_state_tracker/web/config/commands.yaml": "commands",
        "backbone_state_tracker/web/config/devices.example.yaml": "devices example",
        "backbone_state_tracker/web/config/known_hosts.example": "known hosts example",
        "backbone_state_tracker/web/config/mock_profiles.yaml": "mock profiles",
    }


def _core_entries(entries: set[str] | dict[str, str]) -> set[str]:
    return {entry for entry in entries if entry.startswith(CORE_ENTRY_PREFIX)}


def _config_entries(entries: set[str] | dict[str, str]) -> set[str]:
    return {entry for entry in entries if entry.startswith(CONFIG_ENTRY_PREFIX) or "/config/" in entry}


def _doc_entries(entries: set[str] | dict[str, str]) -> set[str]:
    return {entry for entry in entries if entry.startswith(DOC_ENTRY_PREFIX)}


def _test_entries(entries: set[str] | dict[str, str]) -> set[str]:
    return {entry for entry in entries if entry.startswith(TEST_ENTRY_PREFIX)}


def _tool_entries(entries: set[str] | dict[str, str]) -> set[str]:
    return {entry for entry in entries if entry.startswith(TOOL_ENTRY_PREFIX)}


class ReleasePackageVerifierTests(unittest.TestCase):
    def test_common_required_config_entries_match_current_shareable_config_files(self) -> None:
        shareable_names = {
            "analysis_rules.yaml",
            "commands.yaml",
            "devices.example.yaml",
            "known_hosts.example",
            "mock_profiles.yaml",
        }
        expected = {
            f"{CONFIG_ENTRY_PREFIX}{name}"
            for name in shareable_names
        }
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        windows_expected = {
            f"{base}/{name}"
            for base in ("backbone_state_tracker/gui/config", "backbone_state_tracker/web/config")
            for name in shareable_names
        }

        for name in shareable_names:
            self.assertTrue(PROJECT_DIR.joinpath("config", name).is_file(), name)
        self.assertEqual(expected, _config_entries(COMMON_REQUIRED))
        self.assertEqual(expected, _config_entries(SOURCE_REQUIRED))
        self.assertEqual(windows_expected, _config_entries(WINDOWS_REQUIRED))
        self.assertEqual(windows_expected, _config_entries(WINDOWS_EXE_REQUIRED))
        self.assertEqual(expected, _config_entries(_common_entries()))
        self.assertEqual(expected, _config_entries(_source_entries()))
        self.assertEqual(windows_expected, _config_entries(_windows_entries()))
        self.assertEqual(expected, set(CONFIG_ENTRY_PATTERN.findall(powershell_text)))

    def test_common_required_doc_entries_match_current_docs(self) -> None:
        expected = {
            f"{DOC_ENTRY_PREFIX}{path.name}"
            for path in sorted(PROJECT_DIR.joinpath("docs").glob("*"))
            if path.suffix in {".md", ".html"}
        }
        expected.update(
            f"{DOC_ENTRY_PREFIX}images/{path.name}"
            for path in sorted(PROJECT_DIR.joinpath("docs", "images").glob("*"))
            if path.is_file()
        )
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        self.assertEqual(expected, _doc_entries(COMMON_REQUIRED))
        self.assertEqual(expected, _doc_entries(SOURCE_REQUIRED))
        self.assertEqual(set(), _doc_entries(WINDOWS_REQUIRED))
        self.assertEqual(set(), _doc_entries(WINDOWS_EXE_REQUIRED))
        self.assertEqual(expected, _doc_entries(_common_entries()))
        self.assertEqual(expected, _doc_entries(_source_entries()))
        self.assertEqual(set(), _doc_entries(_windows_entries()))
        self.assertEqual(expected, set(DOC_ENTRY_PATTERN.findall(powershell_text)))

    def test_source_required_core_entries_match_current_core_files(self) -> None:
        expected = {
            f"{CORE_ENTRY_PREFIX}{path.relative_to(PROJECT_DIR / 'core').as_posix()}"
            for path in sorted((PROJECT_DIR / "core").rglob("*.py"))
        }
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        self.assertEqual(expected, _core_entries(SOURCE_REQUIRED))
        self.assertEqual(expected, _core_entries(_source_entries()))
        self.assertEqual(expected, set(CORE_ENTRY_PATTERN.findall(powershell_text)))

    def test_source_required_test_entries_match_current_test_files(self) -> None:
        expected = {f"{TEST_ENTRY_PREFIX}{path.name}" for path in sorted((PROJECT_DIR / "tests").glob("test_*.py"))}
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        self.assertEqual(expected, _test_entries(SOURCE_REQUIRED))
        self.assertEqual(expected, _test_entries(_source_entries()))
        self.assertEqual(expected, set(TEST_ENTRY_PATTERN.findall(powershell_text)))

    def test_source_required_tool_entries_match_current_tool_files(self) -> None:
        expected = {
            f"{TOOL_ENTRY_PREFIX}{path.name}"
            for path in sorted((PROJECT_DIR / "tools").glob("*"))
            if path.suffix in {".py", ".ps1"}
        }
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        self.assertEqual(expected, _tool_entries(SOURCE_REQUIRED))
        self.assertEqual(expected, _tool_entries(_source_entries()))
        self.assertEqual(expected, set(TOOL_ENTRY_PATTERN.findall(powershell_text)))

    def test_valid_source_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.1_20260611_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.1", generated_at="2026-06-11T10:00:00+09:00")
            write_release_manifest(
                "backbone_state_tracker",
                "0.8.1",
                "20260611",
                dist,
                generated_at="2026-06-11T10:01:00+09:00",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertTrue(result.ok, result.errors)
            self.assertEqual(result.package_type, "source")

    def test_valid_windows_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            release_tag = "v2026.07.08-104830"
            package = dist / f"backbone_state_tracker_{release_tag}_windows.zip"
            _write_zip(package, _windows_entries())
            write_package_checksum(package, "0.8.1", generated_at="2026-06-11T10:00:00+09:00")
            write_release_manifest(
                "backbone_state_tracker",
                "0.8.1",
                "20260611",
                dist,
                generated_at="2026-06-11T10:01:00+09:00",
                release_tag=release_tag,
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertTrue(result.ok, result.errors)
            self.assertEqual(result.package_type, "windows")

    def test_windows_package_can_verify_with_expected_sha_without_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            release_tag = "v2026.07.08-104831"
            package = dist / f"backbone_state_tracker_{release_tag}_windows.zip"
            _write_zip(package, _windows_entries())
            write_release_manifest(
                "backbone_state_tracker",
                "0.8.1",
                "20260708",
                dist,
                generated_at="2026-07-08T10:48:31+09:00",
                release_tag=release_tag,
            )

            result = verify_release_package(
                package,
                require_manifest=True,
                expected_sha256=file_sha256(package),
            )

            self.assertTrue(result.ok, result.errors)
            self.assertTrue(any("--expected-sha256" in warning for warning in result.warnings))

    def test_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.1_20260611_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.1", generated_at="2026-06-11T10:00:00+09:00")
            _write_zip(package, _source_entries() | {"backbone_state_tracker/extra.txt": "changed"})

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("SHA256 mismatch" in error for error in result.errors))
            self.assertTrue(any("Size mismatch" in error for error in result.errors))

    def test_forbidden_local_devices_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.1_20260611_source.zip"
            entries = _source_entries()
            entries["backbone_state_tracker/config/devices.yaml"] = "secret host data"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.1", generated_at="2026-06-11T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Forbidden ZIP entry" in error for error in result.errors))

    def test_forbidden_local_known_hosts_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.9.0_windows.zip"
            entries = _windows_entries()
            entries["backbone_state_tracker/gui/config/known_hosts"] = "real trusted host key"
            _write_zip(package, entries)
            write_package_checksum(package, "0.9.0", date_stamp="20260824")
            write_release_manifest(
                "backbone_state_tracker",
                "0.9.0",
                "20260824",
                dist,
                release_tag="v0.9.0",
            )

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Forbidden ZIP entry" in error for error in result.errors))

    def test_windows_config_allowlist_rejects_backup_keys_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.9.0_windows.zip"
            entries = _windows_entries()
            entries["backbone_state_tracker/gui/config/known_hosts.backup"] = "trusted internal key"
            entries["backbone_state_tracker/gui/config/credentials.yaml"] = "password: internal"
            entries["backbone_state_tracker/web/config/devices.local.yaml"] = "host: 10.0.0.1"
            _write_zip(package, entries)
            write_package_checksum(package, "0.9.0", date_stamp="20260824")
            write_release_manifest(
                "backbone_state_tracker",
                "0.9.0",
                "20260824",
                dist,
                release_tag="v0.9.0",
            )

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            for name in ("known_hosts.backup", "credentials.yaml", "devices.local.yaml"):
                self.assertTrue(any(name in error for error in result.errors), name)

    def test_source_config_allowlist_rejects_backup_keys_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.9.0_20260824_source.zip"
            entries = _source_entries()
            entries["backbone_state_tracker/config/known_hosts.backup"] = "trusted internal key"
            entries["backbone_state_tracker/config/credentials.yaml"] = "password: internal"
            _write_zip(package, entries)
            write_package_checksum(package, "0.9.0", date_stamp="20260824")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            for name in ("known_hosts.backup", "credentials.yaml"):
                self.assertTrue(any(name in error for error in result.errors), name)

    def test_windows_package_requires_mit_license(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.9.0_windows.zip"
            entries = _windows_entries()
            del entries["backbone_state_tracker/LICENSE"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.9.0", date_stamp="20260824")
            write_release_manifest(
                "backbone_state_tracker",
                "0.9.0",
                "20260824",
                dist,
                release_tag="v0.9.0",
            )

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/LICENSE" in error for error in result.errors))

    def test_forbidden_patterns_match_release_exclusion_policy(self) -> None:
        expected = {
            r"/\.git/",
            r"/outputs/",
            r"/dist/",
            r"/build/",
            r"/raw/",
            r"/\.venv/",
            r"/venv/",
            r"/\.pytest_cache/",
            r"/config/devices\.yaml$",
            r"/config/known_hosts$",
            r"__pycache__",
            r"\.pyc$",
            r"\.spec$",
        }
        powershell_text = (PROJECT_DIR / "tools" / "verify_release_package.ps1").read_text(encoding="utf-8")

        self.assertEqual(expected, {pattern.pattern for pattern in FORBIDDEN_PATTERNS})
        for pattern in expected:
            self.assertIn(pattern, powershell_text)

    def test_forbidden_runtime_output_and_build_folders_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.23_20260612_source.zip"
            entries = _source_entries()
            forbidden_entries = [
                "backbone_state_tracker/outputs/snapshots/pre/check.json",
                "backbone_state_tracker/raw/backbone3/device_status.txt",
                "backbone_state_tracker/dist/old_release.zip",
                "backbone_state_tracker/build/temp.txt",
            ]
            for entry in forbidden_entries:
                entries[entry] = "local runtime artifact"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.23", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            for entry in forbidden_entries:
                self.assertTrue(any(f"Forbidden ZIP entry found: {entry}" in error for error in result.errors))

    def test_forbidden_virtual_environment_and_test_cache_folders_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.24_20260612_source.zip"
            entries = _source_entries()
            forbidden_entries = [
                "backbone_state_tracker/.venv/pyvenv.cfg",
                "backbone_state_tracker/venv/pyvenv.cfg",
                "backbone_state_tracker/.pytest_cache/CACHEDIR.TAG",
            ]
            for entry in forbidden_entries:
                entries[entry] = "local cache"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.24", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            for entry in forbidden_entries:
                self.assertTrue(any(f"Forbidden ZIP entry found: {entry}" in error for error in result.errors))

    def test_unexpected_top_level_zip_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.11_20260612_source.zip"
            entries = _source_entries()
            entries["unexpected.txt"] = "unexpected top-level file"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.11", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any("Unexpected ZIP root entry found: unexpected.txt" in error for error in result.errors)
            )

    def test_zip_entry_path_traversal_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.11_20260612_source.zip"
            entries = _source_entries()
            entries["backbone_state_tracker/../unexpected.txt"] = "path traversal"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.11", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any(
                    "Unsafe ZIP entry found: backbone_state_tracker/../unexpected.txt" in error
                    for error in result.errors
                )
            )

    def test_absolute_zip_entries_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.11_20260612_source.zip"
            entries = _source_entries()
            entries["/tmp/unexpected.txt"] = "absolute path"
            entries["C:/temp/unexpected.txt"] = "windows drive path"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.11", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Unsafe ZIP entry found: /tmp/unexpected.txt" in error for error in result.errors))
            self.assertTrue(
                any("Unsafe ZIP entry found: C:/temp/unexpected.txt" in error for error in result.errors)
            )

    def test_duplicate_zip_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.12_20260612_source.zip"
            duplicate_name = "backbone_state_tracker/docs/USER_GUIDE.md"
            entries = list(_source_entries().items())
            entries.append((duplicate_name, "duplicate user guide"))
            _write_zip_items(package, entries)
            write_package_checksum(package, "0.8.12", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any(f"Duplicate ZIP entry found: {duplicate_name}" in error for error in result.errors)
            )

    def test_requires_matching_version_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.1_20260611_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.1", generated_at="2026-06-11T10:00:00+09:00")
            (dist / "backbone_state_tracker_v0.8.0_20260611_release_manifest.txt").write_text(
                "백본 상태 추적기 릴리스 매니페스트\n",
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(
                any("backbone_state_tracker_v0.8.1_20260611_release_manifest.txt" in error for error in result.errors)
            )

    def test_missing_release_checklist_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.8_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/docs/RELEASE_CHECKLIST.md"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.8", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any("backbone_state_tracker/docs/RELEASE_CHECKLIST.md" in error for error in result.errors)
            )

    def test_missing_portfolio_review_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.9.0_20260824_source.zip"
            entries = _source_entries()
            missing_document = "backbone_state_tracker/docs/PORTFOLIO_REVIEW_KO.md"
            del entries[missing_document]
            _write_zip(package, entries)
            write_package_checksum(package, "0.9.0", generated_at="2026-08-24T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any(missing_document in error for error in result.errors))

    def test_missing_user_guide_image_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.19_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/docs/images/settings-collection.png"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.19", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any("backbone_state_tracker/docs/images/settings-collection.png" in error for error in result.errors)
            )

    def test_missing_bundled_command_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.20_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/config/commands.yaml"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.20", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/config/commands.yaml" in error for error in result.errors))

    def test_missing_windows_executable_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v2026.07.08-104830_windows.zip"
            entries = _windows_entries()
            del entries["backbone_state_tracker/gui/BackboneStateTracker.exe"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.21", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(
                any("backbone_state_tracker/gui/BackboneStateTracker.exe" in error for error in result.errors)
            )

    def test_missing_webapp_launcher_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v2026.07.08-104831_windows.zip"
            entries = _windows_entries()
            del entries["backbone_state_tracker/web/start_webapp.cmd"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.22", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/web/start_webapp.cmd" in error for error in result.errors))

    def test_windows_package_rejects_cli_and_source_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v2026.07.08-104832_windows.zip"
            entries = _windows_entries()
            entries["backbone_state_tracker/BackboneStateTracker.exe"] = b"legacy root exe"
            entries["backbone_state_tracker/RUN_FIRST.txt"] = "legacy cli guide"
            entries["backbone_state_tracker/app.py"] = "source cli entry"
            entries["backbone_state_tracker/tools/cli_helper.ps1"] = "tool"
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.22", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Forbidden Windows release ZIP entry" in error for error in result.errors))
            self.assertTrue(any("Unexpected Windows release ZIP entry" in error for error in result.errors))

    def test_missing_runtime_regression_test_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.15_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/tests/test_reporter.py"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.15", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/tests/test_reporter.py" in error for error in result.errors))

    def test_missing_runtime_core_module_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.16_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/core/gui.py"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.16", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/core/gui.py" in error for error in result.errors))

    def test_missing_requirements_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.17_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/requirements.txt"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.17", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/requirements.txt" in error for error in result.errors))

    def test_missing_release_tool_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.18_20260612_source.zip"
            entries = _source_entries()
            del entries["backbone_state_tracker/tools/build_release.ps1"]
            _write_zip(package, entries)
            write_package_checksum(package, "0.8.18", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("backbone_state_tracker/tools/build_release.ps1" in error for error in result.errors))

    def test_sidecar_version_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.9_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.8", generated_at="2026-06-12T10:00:00+09:00")

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Checksum sidecar version mismatch" in error for error in result.errors))

    def test_sidecar_package_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.10_20260612_source.zip"
            _write_zip(package, _source_entries())
            sidecar = write_package_checksum(package, "0.8.10", generated_at="2026-06-12T10:00:00+09:00")
            sidecar.write_text(
                sidecar.read_text(encoding="utf-8").replace(
                    f"SHA256 ({package.name})",
                    "SHA256 (backbone_state_tracker_v2026.07.08-104830_windows.zip)",
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Checksum sidecar package mismatch" in error for error in result.errors))

    def test_sidecar_date_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.14_20260612_source.zip"
            _write_zip(package, _source_entries())
            sidecar = write_package_checksum(package, "0.8.14", generated_at="2026-06-12T10:00:00+09:00")
            sidecar.write_text(
                sidecar.read_text(encoding="utf-8").replace(
                    "Date stamp = 20260612",
                    "Date stamp = 20260611",
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package)

            self.assertFalse(result.ok)
            self.assertTrue(any("Checksum sidecar date mismatch" in error for error in result.errors))

    def test_manifest_version_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.9_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.9", generated_at="2026-06-12T10:00:00+09:00")
            (dist / "backbone_state_tracker_v0.8.9_20260612_release_manifest.txt").write_text(
                "\n".join(
                    [
                        "백본 상태 추적기 릴리스 매니페스트",
                        "Project = backbone_state_tracker",
                        "Version = v0.8.8",
                        "Date stamp = 20260612",
                        "Generated = 2026-06-12T10:01:00+09:00",
                        "",
                        "Packages",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size} bytes",
                        f"  SHA256: {file_sha256(package)}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(any("Release manifest version mismatch" in error for error in result.errors))

    def test_manifest_date_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.9_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.9", generated_at="2026-06-12T10:00:00+09:00")
            (dist / "backbone_state_tracker_v0.8.9_20260612_release_manifest.txt").write_text(
                "\n".join(
                    [
                        "백본 상태 추적기 릴리스 매니페스트",
                        "Project = backbone_state_tracker",
                        "Version = v0.8.9",
                        "Date stamp = 20260611",
                        "Generated = 2026-06-12T10:01:00+09:00",
                        "",
                        "Packages",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size} bytes",
                        f"  SHA256: {file_sha256(package)}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(any("Release manifest date mismatch" in error for error in result.errors))

    def test_manifest_package_record_sha_mismatch_fails_even_if_hash_exists_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.10_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.10", generated_at="2026-06-12T10:00:00+09:00")
            actual_sha = file_sha256(package)
            wrong_sha = "0" * 64
            (dist / "backbone_state_tracker_v0.8.10_20260612_release_manifest.txt").write_text(
                "\n".join(
                    [
                        "백본 상태 추적기 릴리스 매니페스트",
                        "Project = backbone_state_tracker",
                        "Version = v0.8.10",
                        "Date stamp = 20260612",
                        "Generated = 2026-06-12T10:01:00+09:00",
                        "",
                        "Packages",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size} bytes",
                        f"  SHA256: {wrong_sha}",
                        "- Package: unrelated.zip",
                        "  Size: 1 bytes",
                        f"  SHA256: {actual_sha}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(any("Release manifest package SHA256 mismatch" in error for error in result.errors))

    def test_manifest_package_record_size_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.10_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.10", generated_at="2026-06-12T10:00:00+09:00")
            (dist / "backbone_state_tracker_v0.8.10_20260612_release_manifest.txt").write_text(
                "\n".join(
                    [
                        "백본 상태 추적기 릴리스 매니페스트",
                        "Project = backbone_state_tracker",
                        "Version = v0.8.10",
                        "Date stamp = 20260612",
                        "Generated = 2026-06-12T10:01:00+09:00",
                        "",
                        "Packages",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size + 1} bytes",
                        f"  SHA256: {file_sha256(package)}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(any("Release manifest package size mismatch" in error for error in result.errors))

    def test_duplicate_manifest_package_record_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            package = dist / "backbone_state_tracker_v0.8.13_20260612_source.zip"
            _write_zip(package, _source_entries())
            write_package_checksum(package, "0.8.13", generated_at="2026-06-12T10:00:00+09:00")
            (dist / "backbone_state_tracker_v0.8.13_20260612_release_manifest.txt").write_text(
                "\n".join(
                    [
                        "백본 상태 추적기 릴리스 매니페스트",
                        "Project = backbone_state_tracker",
                        "Version = v0.8.13",
                        "Date stamp = 20260612",
                        "Generated = 2026-06-12T10:01:00+09:00",
                        "",
                        "Packages",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size} bytes",
                        f"  SHA256: {file_sha256(package)}",
                        f"- Package: {package.name}",
                        f"  Size: {package.stat().st_size} bytes",
                        f"  SHA256: {file_sha256(package)}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = verify_release_package(package, require_manifest=True)

            self.assertFalse(result.ok)
            self.assertTrue(
                any(
                    f"Duplicate release manifest package record found: {package.name}" in error
                    for error in result.errors
                )
            )


if __name__ == "__main__":
    unittest.main()
