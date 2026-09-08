from __future__ import annotations

import argparse
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    from backbone_state_tracker.tools.write_release_manifest import file_sha256
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution.
    from write_release_manifest import file_sha256


SHA256_LINE = re.compile(r"^SHA256 \((?P<name>.+)\) = (?P<sha256>[0-9a-f]{64})$", re.MULTILINE)
SIZE_LINE = re.compile(r"^Size = (?P<size>\d+) bytes$", re.MULTILINE)
VERSION_LINE = re.compile(r"^Version = (?P<version>v?\d+\.\d+\.\d+)$", re.MULTILINE)
DATE_STAMP_LINE = re.compile(r"^Date stamp = (?P<date>\d{8})$", re.MULTILINE)
MANIFEST_PACKAGE_LINE = re.compile(r"^- Package: (?P<name>.+)$")
MANIFEST_SIZE_LINE = re.compile(r"^  Size: (?P<size>\d+) bytes$")
MANIFEST_SHA_LINE = re.compile(r"^  SHA256: (?P<sha256>[0-9a-f]{64})$")
PACKAGE_PREFIX = re.compile(
    r"^(?P<prefix>.+_v(?P<version>\d+\.\d+\.\d+)_(?P<date>\d{8}))_(source|windows_exe)\.zip$"
)
TAGGED_WINDOWS_PACKAGE_PREFIX = re.compile(
    r"^(?P<prefix>.+_(?P<tag>v(?:\d+\.\d+\.\d+(?:-rc\.\d+)?|\d{4}\.\d{2}\.\d{2}-\d{6}(?:-\d+)?)))_windows\.zip$"
)
PACKAGE_ROOT = "backbone_state_tracker/"
PACKAGE_ROOT_NAME = "backbone_state_tracker"
WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:/")

COMMON_REQUIRED = {
    "backbone_state_tracker/PACKAGE_INFO.txt",
    "backbone_state_tracker/README.md",
    "backbone_state_tracker/RELEASE_NOTES.md",
    "backbone_state_tracker/CHANGELOG.md",
    "backbone_state_tracker/config/analysis_rules.yaml",
    "backbone_state_tracker/config/commands.yaml",
    "backbone_state_tracker/config/devices.example.yaml",
    "backbone_state_tracker/config/known_hosts.example",
    "backbone_state_tracker/config/mock_profiles.yaml",
    "backbone_state_tracker/docs/ARCHITECTURE.md",
    "backbone_state_tracker/docs/CHANGE_VALIDATION_LOGIC.md",
    "backbone_state_tracker/docs/VALIDATION_REPORT.md",
    "backbone_state_tracker/docs/PORTFOLIO_REVIEW_KO.md",
    "backbone_state_tracker/docs/USAGE_SCREENSHOTS_KO.md",
    "backbone_state_tracker/docs/USER_GUIDE.md",
    "backbone_state_tracker/docs/USER_GUIDE.html",
    "backbone_state_tracker/docs/COMMAND_GUIDE.md",
    "backbone_state_tracker/docs/COMMAND_GUIDE.html",
    "backbone_state_tracker/docs/DEVELOPER_GUIDE_BEGINNER.md",
    "backbone_state_tracker/docs/DEVELOPER_GUIDE_BEGINNER.html",
    "backbone_state_tracker/docs/VERSION_HISTORY.md",
    "backbone_state_tracker/docs/VERSION_HISTORY.html",
    "backbone_state_tracker/docs/RELEASE_CHECKLIST.md",
    "backbone_state_tracker/docs/RELEASE_CHECKLIST.html",
    "backbone_state_tracker/docs/DIAGNOSTIC_ARCHITECTURE_PROPOSAL.md",
    "backbone_state_tracker/docs/DIAGNOSTIC_ARCHITECTURE_PROPOSAL.html",
    "backbone_state_tracker/docs/DIAGNOSTIC_MODE_GUIDE.md",
    "backbone_state_tracker/docs/DIAGNOSTIC_MODE_GUIDE.html",
    "backbone_state_tracker/docs/ERROR_CODE_CATALOG.md",
    "backbone_state_tracker/docs/ERROR_CODE_CATALOG.html",
    "backbone_state_tracker/docs/images/settings-collection.png",
    "backbone_state_tracker/docs/images/compare-results.png",
    "backbone_state_tracker/docs/images/work-log.png",
    "backbone_state_tracker/docs/images/selected-change.png",
    "backbone_state_tracker/docs/images/capture-manifest.json",
}

SOURCE_REQUIRED = COMMON_REQUIRED | {
    "backbone_state_tracker/__init__.py",
    "backbone_state_tracker/app.py",
    "backbone_state_tracker/webapp_launcher.py",
    "backbone_state_tracker/LICENSE",
    "backbone_state_tracker/SECURITY.md",
    "backbone_state_tracker/DEVELOPMENT.md",
    "backbone_state_tracker/requirements.txt",
    "backbone_state_tracker/requirements-dev.txt",
    "backbone_state_tracker/requirements-runtime.lock",
    "backbone_state_tracker/requirements-windows.lock",
    "backbone_state_tracker/core/__init__.py",
    "backbone_state_tracker/core/analysis_rules.py",
    "backbone_state_tracker/core/collector.py",
    "backbone_state_tracker/core/command_safety.py",
    "backbone_state_tracker/core/config.py",
    "backbone_state_tracker/core/connectivity.py",
    "backbone_state_tracker/core/diagnostics/__init__.py",
    "backbone_state_tracker/core/diagnostics/codes.py",
    "backbone_state_tracker/core/diagnostics/events.py",
    "backbone_state_tracker/core/diagnostics/recorder.py",
    "backbone_state_tracker/core/diagnostics/report.py",
    "backbone_state_tracker/core/diagnostics/runner.py",
    "backbone_state_tracker/core/diff_engine.py",
    "backbone_state_tracker/core/gui.py",
    "backbone_state_tracker/core/mock_validation.py",
    "backbone_state_tracker/core/mockserver/__init__.py",
    "backbone_state_tracker/core/mockserver/profiles.py",
    "backbone_state_tracker/core/mockserver/runner.py",
    "backbone_state_tracker/core/mockserver/ssh_server.py",
    "backbone_state_tracker/core/mockserver/telnet_server.py",
    "backbone_state_tracker/core/models.py",
    "backbone_state_tracker/core/paths.py",
    "backbone_state_tracker/core/preflight.py",
    "backbone_state_tracker/core/redaction.py",
    "backbone_state_tracker/core/report_bundle.py",
    "backbone_state_tracker/core/reporter.py",
    "backbone_state_tracker/core/snapshot.py",
    "backbone_state_tracker/core/version.py",
    "backbone_state_tracker/core/webapp.py",
    "backbone_state_tracker/core/workflow.py",
    "backbone_state_tracker/tools/build_release.ps1",
    "backbone_state_tracker/tools/build_windows_exe.ps1",
    "backbone_state_tracker/tools/stamp_sbom_identity.py",
    "backbone_state_tracker/tools/write_release_manifest.py",
    "backbone_state_tracker/tools/capture_windows.py",
    "backbone_state_tracker/tools/capture_usage_screenshots.py",
    "backbone_state_tracker/tools/verify_release_package.py",
    "backbone_state_tracker/tools/verify_release_package.ps1",
    "backbone_state_tracker/tools/verify_release_assets.py",
    "backbone_state_tracker/tests/test_analysis_rules.py",
    "backbone_state_tracker/tests/test_cli_output_encoding.py",
    "backbone_state_tracker/tests/test_collection_security.py",
    "backbone_state_tracker/tests/test_diagnostics_codes.py",
    "backbone_state_tracker/tests/test_diagnostics_report.py",
    "backbone_state_tracker/tests/test_diff_engine.py",
    "backbone_state_tracker/tests/test_documentation.py",
    "backbone_state_tracker/tests/test_gui_formatting.py",
    "backbone_state_tracker/tests/test_mock_collector_integration.py",
    "backbone_state_tracker/tests/test_mock_validation.py",
    "backbone_state_tracker/tests/test_mock_profiles.py",
    "backbone_state_tracker/tests/test_mock_ssh_server.py",
    "backbone_state_tracker/tests/test_mock_telnet_server.py",
    "backbone_state_tracker/tests/test_preflight.py",
    "backbone_state_tracker/tests/test_redaction.py",
    "backbone_state_tracker/tests/test_release_manifest.py",
    "backbone_state_tracker/tests/test_release_assets.py",
    "backbone_state_tracker/tests/test_release_package_verifier.py",
    "backbone_state_tracker/tests/test_reporter.py",
    "backbone_state_tracker/tests/test_snapshot.py",
    "backbone_state_tracker/tests/test_webapp.py",
    "backbone_state_tracker/tests/test_workflow.py",
}

WINDOWS_REQUIRED = {
    "backbone_state_tracker/PACKAGE_INFO.txt",
    "backbone_state_tracker/README_START_HERE_KO.txt",
    "backbone_state_tracker/LICENSE",
    "backbone_state_tracker/gui/BackboneStateTracker.exe",
    "backbone_state_tracker/gui/README_GUI_KO.txt",
    "backbone_state_tracker/gui/config/analysis_rules.yaml",
    "backbone_state_tracker/gui/config/commands.yaml",
    "backbone_state_tracker/gui/config/devices.example.yaml",
    "backbone_state_tracker/gui/config/known_hosts.example",
    "backbone_state_tracker/gui/config/mock_profiles.yaml",
    "backbone_state_tracker/web/README_WEB_KO.txt",
    "backbone_state_tracker/web/start_webapp.cmd",
    "backbone_state_tracker/web/runtime/BackboneWebApp.exe",
    "backbone_state_tracker/web/config/analysis_rules.yaml",
    "backbone_state_tracker/web/config/commands.yaml",
    "backbone_state_tracker/web/config/devices.example.yaml",
    "backbone_state_tracker/web/config/known_hosts.example",
    "backbone_state_tracker/web/config/mock_profiles.yaml",
}

WINDOWS_EXE_REQUIRED = WINDOWS_REQUIRED

SOURCE_CONFIG_ALLOWED = {
    "backbone_state_tracker/config/analysis_rules.yaml",
    "backbone_state_tracker/config/commands.yaml",
    "backbone_state_tracker/config/devices.example.yaml",
    "backbone_state_tracker/config/known_hosts.example",
    "backbone_state_tracker/config/mock_profiles.yaml",
}

WINDOWS_ALLOWED_DIRECTORIES = {
    "backbone_state_tracker/gui",
    "backbone_state_tracker/gui/config",
    "backbone_state_tracker/web",
    "backbone_state_tracker/web/config",
    "backbone_state_tracker/web/runtime",
}

WINDOWS_FORBIDDEN_ENTRIES = {
    "backbone_state_tracker/BackboneStateTracker.exe",
    "backbone_state_tracker/RUN_FIRST.txt",
    "backbone_state_tracker/README.md",
    "backbone_state_tracker/RELEASE_NOTES.md",
    "backbone_state_tracker/CHANGELOG.md",
    "backbone_state_tracker/app.py",
    "backbone_state_tracker/webapp_launcher.py",
}

FORBIDDEN_PATTERNS = [
    re.compile(pattern)
    for pattern in (
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
    )
]


@dataclass(frozen=True)
class VerificationResult:
    package_path: Path
    package_type: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def infer_package_type(package_path: Path) -> str:
    name = package_path.name.lower()
    if name.endswith("_source.zip"):
        return "source"
    if name.endswith("_windows.zip"):
        return "windows"
    if name.endswith("_windows_exe.zip"):
        return "windows_exe"
    return "unknown"


def version_label(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def package_identity(package_path: Path) -> tuple[str, str | None] | None:
    match = PACKAGE_PREFIX.match(package_path.name)
    if match:
        return version_label(match.group("version")), match.group("date")
    tagged_match = TAGGED_WINDOWS_PACKAGE_PREFIX.match(package_path.name)
    if tagged_match and re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tagged_match.group("tag")):
        return tagged_match.group("tag"), None
    return None


def parse_checksum_sidecar(
    sidecar_path: Path,
) -> tuple[str | None, str | None, int | None, str | None, str | None, list[str]]:
    errors: list[str] = []
    if not sidecar_path.is_file():
        return None, None, None, None, None, [f"Missing checksum sidecar: {sidecar_path.name}"]

    text = sidecar_path.read_text(encoding="utf-8")
    sha_match = SHA256_LINE.search(text)
    size_match = SIZE_LINE.search(text)
    version_match = VERSION_LINE.search(text)
    date_match = DATE_STAMP_LINE.search(text)
    sidecar_package_name = sha_match.group("name") if sha_match else None
    expected_sha = sha_match.group("sha256") if sha_match else None
    expected_size = int(size_match.group("size")) if size_match else None
    expected_version = version_label(version_match.group("version")) if version_match else None
    expected_date = date_match.group("date") if date_match else None
    if expected_sha is None:
        errors.append(f"Checksum sidecar does not contain a SHA256 line: {sidecar_path.name}")
    if expected_size is None:
        errors.append(f"Checksum sidecar does not contain a Size line: {sidecar_path.name}")
    if expected_version is None:
        errors.append(f"Checksum sidecar does not contain a Version line: {sidecar_path.name}")
    if expected_date is None:
        errors.append(f"Checksum sidecar does not contain a Date stamp line: {sidecar_path.name}")
    return sidecar_package_name, expected_sha, expected_size, expected_version, expected_date, errors


def parse_manifest_package_records(manifest_text: str) -> dict[str, dict[str, str | int]]:
    records: dict[str, dict[str, str | int]] = {}
    current_name: str | None = None
    for line in manifest_text.splitlines():
        package_match = MANIFEST_PACKAGE_LINE.match(line)
        if package_match:
            current_name = package_match.group("name")
            records[current_name] = {}
            continue
        if current_name is None:
            continue
        size_match = MANIFEST_SIZE_LINE.match(line)
        if size_match:
            records[current_name]["size_bytes"] = int(size_match.group("size"))
            continue
        sha_match = MANIFEST_SHA_LINE.match(line)
        if sha_match:
            records[current_name]["sha256"] = sha_match.group("sha256")
    return records


def duplicate_manifest_package_record_errors(manifest_text: str) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for line in manifest_text.splitlines():
        package_match = MANIFEST_PACKAGE_LINE.match(line)
        if not package_match:
            continue
        package_name = package_match.group("name")
        if package_name in seen:
            errors.append(f"Duplicate release manifest package record found: {package_name}")
        else:
            seen.add(package_name)
    return errors


def normalized_zip_names(package_path: Path) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    names: set[str] = set()
    try:
        with zipfile.ZipFile(package_path) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name in names:
                    errors.append(f"Duplicate ZIP entry found: {name}")
                else:
                    names.add(name)
    except zipfile.BadZipFile:
        errors.append(f"Not a readable ZIP file: {package_path.name}")
    return names, errors


def zip_entry_safety_errors(names: set[str]) -> list[str]:
    errors: list[str] = []
    for name in sorted(names):
        normalized = name.replace("\\", "/")
        stripped = normalized.rstrip("/")
        parts = stripped.split("/") if stripped else []
        unsafe = (
            normalized.startswith("/")
            or WINDOWS_DRIVE_PREFIX.match(normalized) is not None
            or not stripped
            or any(part in ("", ".", "..") for part in parts)
        )
        if unsafe:
            errors.append(f"Unsafe ZIP entry found: {name}")
            continue
        if stripped != PACKAGE_ROOT_NAME and not normalized.startswith(PACKAGE_ROOT):
            errors.append(f"Unexpected ZIP root entry found: {name}")
    return errors


def required_entries_for(package_type: str) -> set[str]:
    if package_type == "source":
        return SOURCE_REQUIRED
    if package_type in {"windows", "windows_exe"}:
        return WINDOWS_REQUIRED
    return COMMON_REQUIRED


def windows_release_contract_errors(names: set[str], package_type: str) -> list[str]:
    if package_type not in {"windows", "windows_exe"}:
        return []

    errors: list[str] = []
    for name in sorted(names):
        stripped = name.rstrip("/")
        if not stripped or stripped == PACKAGE_ROOT_NAME:
            continue
        if stripped in WINDOWS_FORBIDDEN_ENTRIES:
            errors.append(f"Forbidden Windows release ZIP entry found: {stripped}")
            continue
        if stripped in WINDOWS_REQUIRED or stripped in WINDOWS_ALLOWED_DIRECTORIES:
            continue
        errors.append(f"Unexpected Windows release ZIP entry found: {stripped}")
    return errors


def source_config_contract_errors(names: set[str], package_type: str) -> list[str]:
    if package_type != "source":
        return []
    return [
        f"Unexpected source config ZIP entry found: {name.rstrip('/')}"
        for name in sorted(names)
        if name.rstrip('/').startswith("backbone_state_tracker/config/")
        and name.rstrip('/') not in SOURCE_CONFIG_ALLOWED
    ]


def expected_manifest_path(package_path: Path) -> Path | None:
    match = PACKAGE_PREFIX.match(package_path.name)
    if match:
        return package_path.with_name(f"{match.group('prefix')}_release_manifest.txt")
    tagged_match = TAGGED_WINDOWS_PACKAGE_PREFIX.match(package_path.name)
    if tagged_match:
        return package_path.with_name(f"{tagged_match.group('prefix')}_release_manifest.txt")
    return None


def verify_release_package(
    package_path: Path,
    package_type: str | None = None,
    require_manifest: bool = False,
    expected_sha256: str | None = None,
) -> VerificationResult:
    package_path = Path(package_path)
    resolved_type = package_type or infer_package_type(package_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not package_path.is_file():
        return VerificationResult(
            package_path=package_path,
            package_type=resolved_type,
            errors=(f"Package does not exist: {package_path}",),
            warnings=(),
        )

    identity = package_identity(package_path)
    expected_version = identity[0] if identity else None
    expected_date = identity[1] if identity else None

    normalized_expected_sha = expected_sha256.lower() if expected_sha256 else None
    if normalized_expected_sha is not None and not re.fullmatch(r"[0-9a-f]{64}", normalized_expected_sha):
        errors.append(f"Invalid expected SHA256 value: {expected_sha256}")

    sidecar_path = package_path.with_name(f"{package_path.name}.sha256.txt")
    expected_sha: str | None = None
    expected_size: int | None = None
    if sidecar_path.is_file():
        (
            sidecar_package_name,
            expected_sha,
            expected_size,
            sidecar_version,
            sidecar_date,
            sidecar_errors,
        ) = parse_checksum_sidecar(sidecar_path)
        errors.extend(sidecar_errors)
        if sidecar_package_name is not None and sidecar_package_name != package_path.name:
            errors.append(
                f"Checksum sidecar package mismatch: expected {package_path.name}, sidecar {sidecar_package_name}"
            )
        if expected_version is not None and sidecar_version is not None and sidecar_version != expected_version:
            errors.append(
                f"Checksum sidecar version mismatch for {package_path.name}: "
                f"expected {expected_version}, sidecar {sidecar_version}"
            )
        if expected_date is not None and sidecar_date is not None and sidecar_date != expected_date:
            errors.append(
                f"Checksum sidecar date mismatch for {package_path.name}: "
                f"expected {expected_date}, sidecar {sidecar_date}"
            )
    elif normalized_expected_sha is None:
        errors.append(f"Missing checksum sidecar: {sidecar_path.name}")
    else:
        warnings.append(f"Checksum sidecar not present; using --expected-sha256 for {package_path.name}")

    actual_sha = file_sha256(package_path)
    actual_size = package_path.stat().st_size
    if normalized_expected_sha is not None and actual_sha != normalized_expected_sha:
        errors.append(
            f"SHA256 mismatch for {package_path.name}: expected {normalized_expected_sha}, actual {actual_sha}"
        )
    if expected_sha is not None and actual_sha != expected_sha:
        errors.append(f"SHA256 mismatch for {package_path.name}: expected {expected_sha}, actual {actual_sha}")
    if expected_size is not None and actual_size != expected_size:
        errors.append(f"Size mismatch for {package_path.name}: expected {expected_size}, actual {actual_size}")

    names, zip_errors = normalized_zip_names(package_path)
    errors.extend(zip_errors)
    if names:
        errors.extend(zip_entry_safety_errors(names))

        required_entries = required_entries_for(resolved_type)
        missing = sorted(required_entries - names)
        errors.extend(f"Missing required ZIP entry: {entry}" for entry in missing)
        errors.extend(windows_release_contract_errors(names, resolved_type))
        errors.extend(source_config_contract_errors(names, resolved_type))

        for name in sorted(names):
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(name):
                    errors.append(f"Forbidden ZIP entry found: {name}")
                    break

    manifest_path = expected_manifest_path(package_path)
    if manifest_path is None:
        message = "Release manifest was not found next to the package."
        if require_manifest:
            errors.append(message)
        else:
            warnings.append(message)
    elif not manifest_path.is_file():
        message = f"Release manifest was not found next to the package: {manifest_path.name}"
        if require_manifest:
            errors.append(message)
        else:
            warnings.append(message)
    else:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        errors.extend(duplicate_manifest_package_record_errors(manifest_text))
        if expected_version is not None:
            manifest_version_match = VERSION_LINE.search(manifest_text)
            manifest_version = (
                version_label(manifest_version_match.group("version")) if manifest_version_match else None
            )
            if manifest_version is None:
                errors.append(f"Release manifest does not contain a Version line: {manifest_path.name}")
            elif manifest_version != expected_version:
                errors.append(
                    f"Release manifest version mismatch for {package_path.name}: "
                    f"expected {expected_version}, manifest {manifest_version}"
                )
        if expected_date is not None:
            manifest_date_match = DATE_STAMP_LINE.search(manifest_text)
            manifest_date = manifest_date_match.group("date") if manifest_date_match else None
            if manifest_date is None:
                errors.append(f"Release manifest does not contain a Date stamp line: {manifest_path.name}")
            elif manifest_date != expected_date:
                errors.append(
                    f"Release manifest date mismatch for {package_path.name}: "
                    f"expected {expected_date}, manifest {manifest_date}"
                )
        package_records = parse_manifest_package_records(manifest_text)
        package_record = package_records.get(package_path.name)
        if package_record is None:
            errors.append(f"Release manifest does not list package record: {package_path.name}")
        else:
            manifest_size = package_record.get("size_bytes")
            manifest_sha = package_record.get("sha256")
            if manifest_size is None:
                errors.append(f"Release manifest package record does not list size: {package_path.name}")
            elif manifest_size != actual_size:
                errors.append(
                    f"Release manifest package size mismatch for {package_path.name}: "
                    f"expected {actual_size}, manifest {manifest_size}"
                )
            if manifest_sha is None:
                errors.append(f"Release manifest package record does not list SHA256: {package_path.name}")
            elif manifest_sha != actual_sha:
                errors.append(
                    f"Release manifest package SHA256 mismatch for {package_path.name}: "
                    f"expected {actual_sha}, manifest {manifest_sha}"
                )

    return VerificationResult(
        package_path=package_path,
        package_type=resolved_type,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="백본 상태 추적기 릴리스 ZIP을 검증합니다.")
    parser.add_argument("package", type=Path)
    parser.add_argument("--type", choices=("source", "windows", "windows_exe", "unknown"), default=None)
    parser.add_argument("--require-manifest", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)

    result = verify_release_package(
        args.package,
        package_type=args.type,
        require_manifest=args.require_manifest,
        expected_sha256=args.expected_sha256,
    )
    print(f"패키지: {result.package_path}")
    print(f"유형: {result.package_type}")
    if result.warnings:
        print("경고:")
        for warning in result.warnings:
            print(f"- {warning}")
    if result.errors:
        print("오류:")
        for error in result.errors:
            print(f"- {error}")
        return 1
    print("검증 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
