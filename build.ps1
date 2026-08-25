# Build/install Calibre Awards via calibre-customize.
# Filter SyntaxWarning noise from unrelated installed plugins only.
# Never suppress warnings from calibre_awards itself.
# Preserve calibre-customize's exit code.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

Set-Location -LiteralPath $PSScriptRoot

$stdoutFile = [System.IO.Path]::GetTempFileName()
$stderrFile = [System.IO.Path]::GetTempFileName()

try {
    $calibreCustomize = (Get-Command calibre-customize -ErrorAction Stop).Source
    $process = Start-Process -FilePath $calibreCustomize `
        -ArgumentList '-b', '.' `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile `
        -NoNewWindow `
        -Wait `
        -PassThru

    $exitCode = $process.ExitCode

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

    $stdoutLines = @(Get-Content -LiteralPath $stdoutFile -ErrorAction SilentlyContinue)
    $stderrLines = @(Get-Content -LiteralPath $stderrFile -ErrorAction SilentlyContinue)

    Write-FilteredLines -Lines $stdoutLines -Stream Output
    Write-FilteredLines -Lines $stderrLines -Stream Error

    exit $exitCode
}
finally {
    Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
}
