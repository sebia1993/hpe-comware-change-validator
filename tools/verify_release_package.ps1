param(
    [Parameter(Mandatory = $true)]
    [string]$Package,

    [ValidateSet("source", "windows", "windows_exe", "unknown")]
    [string]$Type = "unknown",

    [switch]$RequireManifest
)

$ErrorActionPreference = "Stop"

function Get-NormalizedZipEntries {
    param([string]$PackagePath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
    try {
        return @($archive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    } finally {
        $archive.Dispose()
    }
}

function Get-ZipEntrySafetyErrors {
    param([string[]]$Entries)

    $entryErrors = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $Entries) {
        $normalized = $entry.Replace("\", "/")
        $stripped = $normalized.TrimEnd("/")
        $parts = if ([string]::IsNullOrEmpty($stripped)) { @() } else { $stripped -split "/" }
        $hasUnsafePart = $false
        foreach ($part in $parts) {
            if ([string]::IsNullOrEmpty($part) -or $part -eq "." -or $part -eq "..") {
                $hasUnsafePart = $true
                break
            }
        }

        if (
            $normalized.StartsWith("/") -or
            $normalized -match "^[A-Za-z]:/" -or
            [string]::IsNullOrEmpty($stripped) -or
            $hasUnsafePart
        ) {
            $entryErrors.Add("Unsafe ZIP entry found: $entry")
            continue
        }

        if ($stripped -ne "backbone_state_tracker" -and -not $normalized.StartsWith("backbone_state_tracker/")) {
            $entryErrors.Add("Unexpected ZIP root entry found: $entry")
        }
    }
    return @($entryErrors.ToArray())
}

function Get-PackageType {
    param([string]$PackageName)

    $lowerName = $PackageName.ToLowerInvariant()
    if ($lowerName.EndsWith("_source.zip")) {
        return "source"
    }
    if ($lowerName.EndsWith("_windows.zip")) {
        return "windows"
    }
    if ($lowerName.EndsWith("_windows_exe.zip")) {
        return "windows_exe"
    }
    return "unknown"
}

function Get-ExpectedManifestName {
    param([string]$PackageName)

    if ($PackageName -match "^(?<prefix>.+_v\d+\.\d+\.\d+_\d{8})_(source|windows_exe)\.zip$") {
        return "$($Matches["prefix"])_release_manifest.txt"
    }
    if ($PackageName -match "^(?<prefix>.+_v(?:\d+\.\d+\.\d+(?:-rc\.\d+)?|\d{4}\.\d{2}\.\d{2}-\d{6}(?:-\d+)?))_windows\.zip$") {
        return "$($Matches["prefix"])_release_manifest.txt"
    }
    return $null
}

function Format-VersionLabel {
    param([string]$Version)

    if ($Version.StartsWith("v")) {
        return $Version
    }
    return "v$Version"
}

function Get-PackageIdentity {
    param([string]$PackageName)

    if ($PackageName -match "^(?<project>.+)_v(?<version>\d+\.\d+\.\d+)_(?<date>\d{8})_(source|windows_exe)\.zip$") {
        return @{
            Version = "v$($Matches["version"])"
            DateStamp = $Matches["date"]
        }
    }
    if ($PackageName -match "^(?<project>.+)_v(?<version>\d+\.\d+\.\d+(?:-rc\.\d+)?)_windows\.zip$") {
        return @{
            Version = "v$($Matches["version"])"
            DateStamp = $null
        }
    }
    return $null
}

function Get-ManifestPackageRecords {
    param([string]$ManifestText)

    $records = @{}
    $currentName = $null
    foreach ($line in ($ManifestText -split "`r?`n")) {
        if ($line -match "^- Package: (?<name>.+)$") {
            $currentName = $Matches["name"]
            $records[$currentName] = @{}
            continue
        }
        if ([string]::IsNullOrWhiteSpace($currentName)) {
            continue
        }
        if ($line -match "^  Size: (?<size>\d+) bytes$") {
            $records[$currentName]["SizeBytes"] = [int64]$Matches["size"]
            continue
        }
        if ($line -match "^  SHA256: (?<sha256>[0-9a-f]{64})$") {
            $records[$currentName]["SHA256"] = $Matches["sha256"]
        }
    }
    return $records
}

function Get-DuplicateManifestPackageRecordErrors {
    param([string]$ManifestText)

    $recordErrors = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($line in ($ManifestText -split "`r?`n")) {
        if ($line -match "^- Package: (?<name>.+)$") {
            $packageRecordName = $Matches["name"]
            if ($seen.ContainsKey($packageRecordName)) {
                $recordErrors.Add("Duplicate release manifest package record found: $packageRecordName")
            } else {
                $seen[$packageRecordName] = $true
            }
        }
    }
    return @($recordErrors.ToArray())
}

$resolvedPackage = (Resolve-Path -LiteralPath $Package).Path
$packageItem = Get-Item -LiteralPath $resolvedPackage
$packageName = $packageItem.Name
$packageType = if ($Type -eq "unknown") { Get-PackageType -PackageName $packageName } else { $Type }
$packageIdentity = Get-PackageIdentity -PackageName $packageName
$sidecarPath = "$resolvedPackage.sha256.txt"
$expectedSha = $null
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $sidecarPath)) {
    $errors.Add("Missing checksum sidecar: $(Split-Path $sidecarPath -Leaf)")
} else {
    $sidecarText = Get-Content -LiteralPath $sidecarPath -Raw -Encoding UTF8
    $multiline = [System.Text.RegularExpressions.RegexOptions]::Multiline
    $shaMatch = [regex]::Match($sidecarText, "^SHA256 \((?<name>.+)\) = (?<sha256>[0-9a-f]{64})\r?$", $multiline)
    $sizeMatch = [regex]::Match($sidecarText, "^Size = (?<size>\d+) bytes\r?$", $multiline)
    $versionMatch = [regex]::Match($sidecarText, "^Version = (?<version>v?\d+\.\d+\.\d+)\r?$", $multiline)
    $dateStampMatch = [regex]::Match($sidecarText, "^Date stamp = (?<date>\d{8})\r?$", $multiline)
    if (-not $shaMatch.Success) {
        $errors.Add("Checksum sidecar does not contain a SHA256 line: $(Split-Path $sidecarPath -Leaf)")
    }
    if (-not $sizeMatch.Success) {
        $errors.Add("Checksum sidecar does not contain a Size line: $(Split-Path $sidecarPath -Leaf)")
    }
    if (-not $versionMatch.Success) {
        $errors.Add("Checksum sidecar does not contain a Version line: $(Split-Path $sidecarPath -Leaf)")
    }
    if (-not $dateStampMatch.Success) {
        $errors.Add("Checksum sidecar does not contain a Date stamp line: $(Split-Path $sidecarPath -Leaf)")
    }
    if ($shaMatch.Success) {
        $sidecarPackageName = $shaMatch.Groups["name"].Value
        if ($sidecarPackageName -ne $packageName) {
            $errors.Add("Checksum sidecar package mismatch: expected $packageName, sidecar $sidecarPackageName")
        }
        $expectedSha = $shaMatch.Groups["sha256"].Value
        $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedPackage).Hash.ToLowerInvariant()
        if ($actualSha -ne $expectedSha) {
            $errors.Add("SHA256 mismatch for ${packageName}: expected $expectedSha, actual $actualSha")
        }
    }
    if ($sizeMatch.Success) {
        $expectedSize = [int64]$sizeMatch.Groups["size"].Value
        if ($packageItem.Length -ne $expectedSize) {
            $errors.Add("Size mismatch for ${packageName}: expected $expectedSize, actual $($packageItem.Length)")
        }
    }
    if ($versionMatch.Success -and $packageIdentity) {
        $sidecarVersion = Format-VersionLabel -Version $versionMatch.Groups["version"].Value
        if ($sidecarVersion -ne $packageIdentity.Version) {
            $errors.Add("Checksum sidecar version mismatch for ${packageName}: expected $($packageIdentity.Version), sidecar $sidecarVersion")
        }
    }
    if ($dateStampMatch.Success -and $packageIdentity -and -not [string]::IsNullOrWhiteSpace($packageIdentity.DateStamp)) {
        $sidecarDateStamp = $dateStampMatch.Groups["date"].Value
        if ($sidecarDateStamp -ne $packageIdentity.DateStamp) {
            $errors.Add("Checksum sidecar date mismatch for ${packageName}: expected $($packageIdentity.DateStamp), sidecar $sidecarDateStamp")
        }
    }
}

$commonRequired = @(
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
    "backbone_state_tracker/docs/images/work-log.png"
)
$sourceRequired = $commonRequired + @(
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
    "backbone_state_tracker/tests/test_workflow.py"
)
$windowsRequired = @(
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
    "backbone_state_tracker/web/config/mock_profiles.yaml"
)
$sourceConfigAllowed = @(
    "backbone_state_tracker/config/analysis_rules.yaml",
    "backbone_state_tracker/config/commands.yaml",
    "backbone_state_tracker/config/devices.example.yaml",
    "backbone_state_tracker/config/known_hosts.example",
    "backbone_state_tracker/config/mock_profiles.yaml"
)
$required = switch ($packageType) {
    "source" { $sourceRequired }
    "windows" { $windowsRequired }
    "windows_exe" { $windowsRequired }
    default { $commonRequired }
}

$entries = Get-NormalizedZipEntries -PackagePath $resolvedPackage
$entrySet = @{}
foreach ($entry in $entries) {
    if ($entrySet.ContainsKey($entry)) {
        $errors.Add("Duplicate ZIP entry found: $entry")
    } else {
        $entrySet[$entry] = $true
    }
}

if ($packageType -eq "windows" -or $packageType -eq "windows_exe") {
    $windowsAllowedDirectories = @(
        "backbone_state_tracker/gui",
        "backbone_state_tracker/gui/config",
        "backbone_state_tracker/web",
        "backbone_state_tracker/web/config",
        "backbone_state_tracker/web/runtime"
    )
    $windowsForbiddenEntries = @(
        "backbone_state_tracker/BackboneStateTracker.exe",
        "backbone_state_tracker/RUN_FIRST.txt",
        "backbone_state_tracker/README.md",
        "backbone_state_tracker/RELEASE_NOTES.md",
        "backbone_state_tracker/CHANGELOG.md",
        "backbone_state_tracker/app.py",
        "backbone_state_tracker/webapp_launcher.py"
    )
    foreach ($entry in $entries) {
        $stripped = $entry.TrimEnd("/")
        if ([string]::IsNullOrWhiteSpace($stripped) -or $stripped -eq "backbone_state_tracker") {
            continue
        }
        if ($windowsForbiddenEntries -contains $stripped) {
            $errors.Add("Forbidden Windows release ZIP entry found: $stripped")
            continue
        }
        if ($windowsRequired -contains $stripped -or $windowsAllowedDirectories -contains $stripped) {
            continue
        }
        $errors.Add("Unexpected Windows release ZIP entry found: $stripped")
    }
}
if ($packageType -eq "source") {
    foreach ($entry in $entries) {
        $stripped = $entry.TrimEnd("/")
        if ($stripped.StartsWith("backbone_state_tracker/config/") -and $sourceConfigAllowed -notcontains $stripped) {
            $errors.Add("Unexpected source config ZIP entry found: $stripped")
        }
    }
}
foreach ($entryError in (Get-ZipEntrySafetyErrors -Entries @($entrySet.Keys))) {
    $errors.Add($entryError)
}
foreach ($requiredEntry in $required) {
    if (-not $entrySet.ContainsKey($requiredEntry)) {
        $errors.Add("Missing required ZIP entry: $requiredEntry")
    }
}

$forbiddenPatterns = @(
    "/\.git/",
    "/outputs/",
    "/dist/",
    "/build/",
    "/raw/",
    "/\.venv/",
    "/venv/",
    "/\.pytest_cache/",
    "/config/devices\.yaml$",
    "/config/known_hosts$",
    "__pycache__",
    "\.pyc$",
    "\.spec$"
)
foreach ($entry in $entries) {
    foreach ($pattern in $forbiddenPatterns) {
        if ($entry -match $pattern) {
            $errors.Add("Forbidden ZIP entry found: $entry")
            break
        }
    }
}

$manifestName = Get-ExpectedManifestName -PackageName $packageName
if ([string]::IsNullOrWhiteSpace($manifestName)) {
    $message = "Release manifest was not found next to the package."
    if ($RequireManifest) {
        $errors.Add($message)
    } else {
        $warnings.Add($message)
    }
} else {
    $manifestPath = Join-Path $packageItem.DirectoryName $manifestName
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        $message = "Release manifest was not found next to the package: $manifestName"
        if ($RequireManifest) {
            $errors.Add($message)
        } else {
            $warnings.Add($message)
        }
    } else {
        $manifestText = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
        foreach ($manifestRecordError in (Get-DuplicateManifestPackageRecordErrors -ManifestText $manifestText)) {
            $errors.Add($manifestRecordError)
        }
        if ($packageIdentity) {
            $multiline = [System.Text.RegularExpressions.RegexOptions]::Multiline
            $manifestVersionMatch = [regex]::Match($manifestText, "^Version = (?<version>v?\d+\.\d+\.\d+)\r?$", $multiline)
            $manifestDateMatch = [regex]::Match($manifestText, "^Date stamp = (?<date>\d{8})\r?$", $multiline)
            if (-not $manifestVersionMatch.Success) {
                $errors.Add("Release manifest does not contain a Version line: $manifestName")
            } else {
                $manifestVersion = Format-VersionLabel -Version $manifestVersionMatch.Groups["version"].Value
                if ($manifestVersion -ne $packageIdentity.Version) {
                    $errors.Add("Release manifest version mismatch for ${packageName}: expected $($packageIdentity.Version), manifest $manifestVersion")
                }
            }
            if (-not $manifestDateMatch.Success) {
                $errors.Add("Release manifest does not contain a Date stamp line: $manifestName")
            } elseif (
                -not [string]::IsNullOrWhiteSpace($packageIdentity.DateStamp) -and
                $manifestDateMatch.Groups["date"].Value -ne $packageIdentity.DateStamp
            ) {
                $errors.Add("Release manifest date mismatch for ${packageName}: expected $($packageIdentity.DateStamp), manifest $($manifestDateMatch.Groups["date"].Value)")
            }
        }
        $manifestRecords = Get-ManifestPackageRecords -ManifestText $manifestText
        if (-not $manifestRecords.ContainsKey($packageName)) {
            $errors.Add("Release manifest does not list package record: $packageName")
        } else {
            $packageRecord = $manifestRecords[$packageName]
            if (-not $packageRecord.ContainsKey("SizeBytes")) {
                $errors.Add("Release manifest package record does not list size: $packageName")
            } elseif ($packageRecord["SizeBytes"] -ne $packageItem.Length) {
                $errors.Add("Release manifest package size mismatch for ${packageName}: expected $($packageItem.Length), manifest $($packageRecord["SizeBytes"])")
            }
            if (-not $packageRecord.ContainsKey("SHA256")) {
                $errors.Add("Release manifest package record does not list SHA256: $packageName")
            } else {
                $actualManifestSha = $packageRecord["SHA256"]
                $actualPackageSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedPackage).Hash.ToLowerInvariant()
                if ($actualManifestSha -ne $actualPackageSha) {
                    $errors.Add("Release manifest package SHA256 mismatch for ${packageName}: expected $actualPackageSha, manifest $actualManifestSha")
                }
            }
        }
    }
}

Write-Host "Package: $resolvedPackage"
Write-Host "Type: $packageType"
if ($warnings.Count -gt 0) {
    Write-Host "Warnings:"
    foreach ($warning in $warnings) {
        Write-Host "- $warning"
    }
}
if ($errors.Count -gt 0) {
    Write-Host "Errors:"
    foreach ($errorMessage in $errors) {
        Write-Host "- $errorMessage"
    }
    exit 1
}

Write-Host "Verification OK"
