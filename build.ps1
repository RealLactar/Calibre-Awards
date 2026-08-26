# Build a clean Calibre Awards ZIP from an explicit runtime allowlist, then
# install that exact ZIP with calibre-customize -a.
# Filter SyntaxWarning noise from unrelated installed plugins only.
# Never suppress warnings from calibre_awards itself.
# Preserve calibre-customize's exit code.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location -LiteralPath $PSScriptRoot

# Runtime allowlist: only these files and directories ship in the public ZIP.
# Add a new runtime module or resource here when install-time code needs it.
# Tests, README, AGENTS.md, and this script stay off the list so later
# development files cannot leak into a release.
$RuntimeRootFiles = @(
    '__init__.py',
    'ui.py',
    'config.py',
    'edit_metadata_hook.py',
    'award_selection_dialog.py',
    'supported_sources_dialog.py',
    'plugin-import-name-calibre_awards.txt',
    'LICENSE'
)
$RuntimeDirectories = @(
    'awards',
    'images'
)

function Get-PluginVersion {
    $initPath = Join-Path $PSScriptRoot '__init__.py'
    $text = Get-Content -LiteralPath $initPath -Raw
    $match = [regex]::Match(
        $text,
        'version\s*=\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)'
    )
    if (-not $match.Success) {
        throw 'Could not read version = (x, y, z) from __init__.py'
    }
    return '{0}.{1}.{2}' -f $match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value
}

function Test-IsSuppressedUnrelatedSyntaxWarning {
    param([string]$Line)

    if ($Line -notmatch 'SyntaxWarning') {
        return $false
    }
    # Never suppress our own plugin.
    if ($Line -match 'calibre_plugins\.calibre_awards') {
        return $false
    }
    if ($Line -match 'calibre_plugins\.(fantastic_fiction|kobo_metadata)') {
        return $true
    }
    return $false
}

function Write-FilteredLines {
    param(
        [string[]]$Lines,
        [ValidateSet('Output', 'Error')]
        [string]$Stream
    )

    $suppressContinuation = $false
    foreach ($line in $Lines) {
        if ($null -eq $line) {
            continue
        }

        if (Test-IsSuppressedUnrelatedSyntaxWarning -Line $line) {
            $suppressContinuation = $true
            continue
        }

        # Suppress only the immediate continuation line of a filtered warning.
        if (
            $suppressContinuation -and
            (
                $line -match 'Such sequences will not work in the future' -or
                $line -match 'raw string is also an option'
            )
        ) {
            $suppressContinuation = $false
            continue
        }

        $suppressContinuation = $false

        if ($Stream -eq 'Error') {
            [Console]::Error.WriteLine($line)
        }
        else {
            Write-Output $line
        }
    }
}

function Copy-RuntimeTree {
    param(
        [string]$SourceRoot,
        [string]$DestinationRoot
    )

    foreach ($name in $RuntimeRootFiles) {
        $source = Join-Path $SourceRoot $name
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Runtime file missing: $name"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $DestinationRoot $name)
    }

    foreach ($name in $RuntimeDirectories) {
        $source = Join-Path $SourceRoot $name
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Runtime directory missing: $name"
        }
        $destination = Join-Path $DestinationRoot $name
        Copy-Item -LiteralPath $source -Destination $destination -Recurse
    }

    Get-ChildItem -LiteralPath $DestinationRoot -Recurse -Force |
        Where-Object {
            $_.Name -eq '__pycache__' -or
            $_.Extension -in @('.pyc', '.pyo')
        } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

$version = Get-PluginVersion
$distDir = Join-Path $PSScriptRoot 'dist'
$zipName = "Calibre-Awards-$version.zip"
$zipPath = Join-Path $distDir $zipName
$stage = Join-Path ([System.IO.Path]::GetTempPath()) (
    'calibre-awards-stage-' + [guid]::NewGuid().ToString('N')
)
$stdoutFile = [System.IO.Path]::GetTempFileName()
$stderrFile = [System.IO.Path]::GetTempFileName()
$exitCode = 1

try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-RuntimeTree -SourceRoot $PSScriptRoot -DestinationRoot $stage

    if (-not (Test-Path -LiteralPath $distDir)) {
        New-Item -ItemType Directory -Path $distDir | Out-Null
    }
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    $stageForPython = $stage.Replace('\', '/')
    $zipForPython = $zipPath.Replace('\', '/')
    python -c @"
import os
import zipfile

src = r'$stageForPython'
dest = r'$zipForPython'
with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
        for name in files:
            if name.endswith(('.pyc', '.pyo')):
                continue
            path = os.path.join(root, name)
            arc = os.path.relpath(path, src).replace(os.sep, '/')
            zf.write(path, arc)
"@
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to write $zipName"
    }
    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Release ZIP was not created: $zipPath"
    }

    $ErrorActionPreference = 'Continue'
    $calibreCustomize = (Get-Command calibre-customize -ErrorAction Stop).Source
    $process = Start-Process -FilePath $calibreCustomize `
        -ArgumentList '-a', $zipPath `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile `
        -NoNewWindow `
        -Wait `
        -PassThru
    $exitCode = $process.ExitCode
    $ErrorActionPreference = 'Stop'

    $stdoutLines = @(Get-Content -LiteralPath $stdoutFile -ErrorAction SilentlyContinue)
    $stderrLines = @(Get-Content -LiteralPath $stderrFile -ErrorAction SilentlyContinue)
    Write-FilteredLines -Lines $stdoutLines -Stream Output
    Write-FilteredLines -Lines $stderrLines -Stream Error
    Write-Output "Release ZIP: $zipPath"
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
}

exit $exitCode
