#!/usr/bin/env pwsh
# Read-only MCP Inspector integration run against LINKEDIN_EXPORT_DIR from .env.
# It writes only a temporary Inspector config and never modifies the export.

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("linkedin-mcp-real-e2e-" + [guid]::NewGuid().ToString('N'))
$configPath = Join-Path $tempRoot 'inspector-config.json'

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -cne $Expected) {
        throw $Message
    }
}

function Invoke-Inspector([string]$Method, [string[]]$ExtraArgs = @()) {
    $arguments = @(
        '--yes', '@modelcontextprotocol/inspector', '--cli',
        '--config', $configPath, '--server', 'linkedin-real',
        '--method', $Method, '--format', 'json', '--quiet'
    ) + $ExtraArgs
    $output = & npx @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "MCP Inspector failed for '$Method' (exit $LASTEXITCODE)."
    }
    return ($output -join [Environment]::NewLine) | ConvertFrom-Json
}

function Get-ToolPayload($Envelope) {
    if ($null -ne $Envelope.result.structuredContent) {
        return $Envelope.result.structuredContent
    }
    $textItem = $Envelope.result.content | Where-Object { $_.type -eq 'text' } | Select-Object -First 1
    if ($null -eq $textItem) {
        throw 'Tool response did not contain structured data or a text result.'
    }
    return $textItem.text | ConvertFrom-Json
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    # Resolve configuration through the app's own dotenv loader and build
    # search probes in memory; only the temporary config is written to disk.
    $pythonProbe = @'
import json
from linkedin_mcp.config import load_settings
from linkedin_mcp.repository import LinkedInData

settings = load_settings()
data = LinkedInData.from_directory(settings.export_dir)
connection = next((item for item in data.connections if item.full_name.strip()), None)
post = next((item for item in data.posts if item.text.split()), None)
connection_query = " ".join(part for part in (connection.first_name, connection.last_name) if part.strip()) if connection else ""
if connection and not connection_query:
    connection_query = connection.company.strip() or connection.position.strip()
post_query = post.text.split()[0] if post else ""
connection_public = connection.to_public_dict() if connection else None
post_public = post.to_public_dict() if post else None
print(json.dumps({
    "export_dir": str(settings.export_dir),
    "connection_count": len(data.connections),
    "post_count": len(data.posts),
    "position_count": len(data.positions),
    "skill_count": len(data.skills),
    "profile_present": data.profile is not None,
    "profile_public": ({
        **data.profile.to_public_dict(),
        "connection_count": len(data.connections),
        "post_count": len(data.posts),
    } if data.profile else None),
    "connection_query": connection_query,
    "connection_public": connection_public,
    "post_query": post_query,
    "post_public": post_public,
    "positions_public": [item.to_public_dict() for item in data.positions],
    "skills": data.skills,
}))
'@
    $probeOutput = $pythonProbe | uv run --directory $projectRoot python -
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not resolve or load the export configured by .env.'
    }
    $info = ($probeOutput -join [Environment]::NewLine) | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $info.export_dir -PathType Container)) {
        throw 'LINKEDIN_EXPORT_DIR does not point to an existing folder.'
    }
    if (@($info.connection_count, $info.post_count, $info.position_count, $info.skill_count | Where-Object { $_ -gt 0 }).Count -eq 0 -and -not $info.profile_present) {
        throw 'The configured folder did not contain any data supported by this server.'
    }

    $config = @{
        mcpServers = @{
            'linkedin-real' = @{
                type = 'stdio'
                command = 'uv'
                args = @('run', '--directory', $projectRoot, 'linkedin-mcp')
                cwd = $projectRoot
                env = @{ LINKEDIN_EXPORT_DIR = $info.export_dir; LOG_LEVEL = 'ERROR' }
            }
        }
    }
    $configJson = $config | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($configPath, $configJson, [System.Text.UTF8Encoding]::new($false))

    $init = Invoke-Inspector 'initialize'
    Assert-Equal $init.result.serverInfo.name 'linkedin-data' 'Unexpected MCP server name.'

    $listed = Invoke-Inspector 'tools/list'
    $expectedTools = @('get_profile_summary', 'search_connections', 'search_posts', 'list_experience')
    $actualTools = @($listed.result.tools | ForEach-Object { $_.name } | Sort-Object)
    $expectedTools = @($expectedTools | Sort-Object)
    Assert-Equal ($actualTools -join ',') ($expectedTools -join ',') 'The MCP tool list differed from the expected tools.'
    if (@($listed.result.tools | Where-Object { -not $_.annotations.readOnlyHint }).Count -gt 0) {
        throw 'One or more tools are missing the read-only annotation.'
    }
    $toolByName = @{}
    foreach ($tool in $listed.result.tools) { $toolByName[$tool.name] = $tool }
    $connectionProperties = $toolByName['search_connections'].inputSchema.properties.PSObject.Properties.Name
    foreach ($requiredProperty in @('query', 'limit')) {
        if ($connectionProperties -notcontains $requiredProperty) {
            throw "search_connections is missing its '$requiredProperty' input schema property."
        }
    }
    $postProperties = $toolByName['search_posts'].inputSchema.properties.PSObject.Properties.Name
    foreach ($requiredProperty in @('query', 'limit')) {
        if ($postProperties -notcontains $requiredProperty) {
            throw "search_posts is missing its '$requiredProperty' input schema property."
        }
    }

    $profile = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'get_profile_summary'))
    if ($info.profile_present) {
        if (($profile | ConvertTo-Json -Depth 8 -Compress) -cne ($info.profile_public | ConvertTo-Json -Depth 8 -Compress)) {
            throw 'The profile tool fields did not match the configured export.'
        }
    } elseif (-not $profile.error) {
        throw 'The profile tool did not report the missing Profile.csv.'
    }

    if ($info.connection_query) {
        $connections = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
            '--tool-name', 'search_connections', '--tool-arg', "query=$($info.connection_query)", '--tool-arg', 'limit=50'
        ))
        if ($connections.count -lt 1 -or -not ($connections.results | Where-Object { ($_ | ConvertTo-Json -Depth 8 -Compress) -ceq ($info.connection_public | ConvertTo-Json -Depth 8 -Compress) })) {
            throw 'Connection search fields did not match the derived export record.'
        }
    } else {
        $connections = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
            '--tool-name', 'search_connections', '--tool-arg', 'query=__linkedin_mcp_no_match__'
        ))
        Assert-Equal $connections.count 0 'Empty connection data should return zero matches.'
    }

    if ($info.post_query) {
        $posts = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
            '--tool-name', 'search_posts', '--tool-arg', "query=$($info.post_query)", '--tool-arg', 'limit=50'
        ))
        if ($posts.count -lt 1 -or -not ($posts.results | Where-Object { ($_ | ConvertTo-Json -Depth 8 -Compress) -ceq ($info.post_public | ConvertTo-Json -Depth 8 -Compress) })) {
            throw 'Post search fields did not match the derived Shares.csv record.'
        }
    } else {
        $posts = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
            '--tool-name', 'search_posts', '--tool-arg', 'query=__linkedin_mcp_no_match__'
        ))
        Assert-Equal $posts.count 0 'Missing or empty Shares.csv should return zero matches.'
    }

    $experience = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'list_experience'))
    if (($experience.positions | ConvertTo-Json -Depth 8 -Compress) -cne ($info.positions_public | ConvertTo-Json -Depth 8 -Compress)) {
        throw 'Experience position fields did not match the configured export.'
    }
    if (($experience.skills | ConvertTo-Json -Depth 8 -Compress) -cne ($info.skills | ConvertTo-Json -Depth 8 -Compress)) {
        throw 'Experience skills did not match the configured export.'
    }

    $resources = Invoke-Inspector 'resources/list'
    if (-not (@($resources.result.resources | ForEach-Object { $_.uri }) -contains 'linkedin://schema')) {
        throw 'linkedin://schema resource was not listed.'
    }
    $schema = Invoke-Inspector 'resources/read' @('--uri', 'linkedin://schema')
    $schemaData = $schema.result.contents[0].text | ConvertFrom-Json
    Assert-Equal $schemaData.counts.connections $info.connection_count 'Schema connection count did not match the export.'
    Assert-Equal $schemaData.counts.posts $info.post_count 'Schema post count did not match the export.'
    Assert-Equal $schemaData.counts.positions $info.position_count 'Schema position count did not match the export.'
    Assert-Equal $schemaData.counts.skills $info.skill_count 'Schema skill count did not match the export.'
    if (-not ($schemaData.not_included -contains 'messages') -or -not ($schemaData.not_included -contains 'connection emails')) {
        throw 'Schema did not list the intentionally excluded private data.'
    }

    Write-Host 'PASS: Real-export MCP Inspector checks passed for initialization, all 4 tools, available data, and linkedin://schema. No export contents were printed.'
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
