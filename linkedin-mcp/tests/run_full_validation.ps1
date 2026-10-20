#!/usr/bin/env pwsh
# One entry point for synthetic edge-case E2E, real-export Inspector E2E,
# and the full pytest suite with real-export checks enabled.
# All real-export calls are read-only. Temporary test fixtures/configs are
# created by the subordinate scripts and removed when they finish.

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Project virtualenv not found. From the project folder run: uv sync --extra dev'
}
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw 'npx is required for MCP Inspector. Install Node.js/npm, then rerun this script.'
}

Push-Location $projectRoot
try {
    Write-Host '=== MCP Inspector: synthetic CSV E2E and edge cases ==='
    & (Join-Path $PSScriptRoot 'run_inspector_e2e.ps1')

    Write-Host '=== MCP Inspector: configured real LinkedIn export ==='
    & (Join-Path $PSScriptRoot 'run_inspector_real_export.ps1')

    Write-Host '=== Pytest: unit tests plus opt-in real-export checks ==='
    $previousRealTestFlag = $env:LINKEDIN_MCP_REAL_DATA_TESTS
    $env:LINKEDIN_MCP_REAL_DATA_TESTS = '1'
    try {
        & $python -m pytest --tb=short
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed (exit $LASTEXITCODE)."
        }
    }
    finally {
        if ($null -eq $previousRealTestFlag) {
            Remove-Item Env:LINKEDIN_MCP_REAL_DATA_TESTS -ErrorAction SilentlyContinue
        }
        else {
            $env:LINKEDIN_MCP_REAL_DATA_TESTS = $previousRealTestFlag
        }
    }

    Write-Host 'PASS: Full validation entry point completed. Any skipped checks reflect unavailable data (for example, missing Shares.csv).'
}
finally {
    Pop-Location
}
