#!/usr/bin/env pwsh
# End-to-end smoke test: starts the real stdio server through MCP Inspector
# and uses only synthetic CSV data in a temporary directory.

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("linkedin-mcp-e2e-" + [guid]::NewGuid().ToString('N'))
$exportDir = Join-Path $tempRoot 'fake-export'
$emptyExportDir = Join-Path $tempRoot 'empty-export'
$configPath = Join-Path $tempRoot 'inspector-config.json'

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ($Actual -cne $Expected) {
        throw "$Message (expected '$Expected', got '$Actual')"
    }
}

function Invoke-Inspector([string]$Method, [string[]]$ExtraArgs = @(), [string]$Server = 'linkedin-fake') {
    $arguments = @(
        '--yes', '@modelcontextprotocol/inspector', '--cli',
        '--config', $configPath, '--server', $Server,
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
    New-Item -ItemType Directory -Path $exportDir -Force | Out-Null
    New-Item -ItemType Directory -Path $emptyExportDir -Force | Out-Null

    @'
First Name,Last Name,URL,Email Address,Company,Position,Connected On
Alex,Example,https://example.invalid/alex,alex@example.invalid,Acme,Backend Engineer,01 Jan 2024
Sam,Sample,https://example.invalid/sam,sam@example.invalid,Globex,Data Scientist,02 Feb 2024
'@ | Set-Content (Join-Path $exportDir 'Connections.csv') -Encoding utf8

    @'
First Name,Last Name,Headline,Summary,Industry,Geo Location
Demo,User,Test Engineer,Synthetic profile for MCP E2E tests,Software,Example City
'@ | Set-Content (Join-Path $exportDir 'Profile.csv') -Encoding utf8

    $longPost = 'LongToken ' * 65
    @(
        'Date,ShareLink,ShareCommentary'
        '2024-03-01,https://example.invalid/post-1,"Learning about MCP servers"'
        '2024-03-02,https://example.invalid/post-2,"A synthetic post about testing"'
        "2024-03-03,https://example.invalid/post-long,`"$longPost`""
    ) | Set-Content (Join-Path $exportDir 'Shares.csv') -Encoding utf8

    @'
Company Name,Title,Description,Location,Started On,Finished On
Example Labs,Test Engineer,Builds reliable tests,Example City,Jan 2020,
'@ | Set-Content (Join-Path $exportDir 'Positions.csv') -Encoding utf8

    @'
Name
Python
Testing
'@ | Set-Content (Join-Path $exportDir 'Skills.csv') -Encoding utf8

    $config = @{
        mcpServers = @{
            'linkedin-fake' = @{
                type = 'stdio'
                command = 'uv'
                args = @('run', '--directory', $projectRoot, 'linkedin-mcp')
                cwd = $projectRoot
                env = @{ LINKEDIN_EXPORT_DIR = $exportDir; LOG_LEVEL = 'WARNING' }
            }
            'linkedin-empty' = @{
                type = 'stdio'
                command = 'uv'
                args = @('run', '--directory', $projectRoot, 'linkedin-mcp')
                cwd = $projectRoot
                env = @{ LINKEDIN_EXPORT_DIR = $emptyExportDir; LOG_LEVEL = 'ERROR' }
            }
        }
    }
    $configJson = $config | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($configPath, $configJson, [System.Text.UTF8Encoding]::new($false))

    $init = Invoke-Inspector 'initialize'
    Assert-Equal $init.result.serverInfo.name 'linkedin-data' 'Unexpected MCP server name'

    $listed = Invoke-Inspector 'tools/list'
    $expectedTools = @('get_profile_summary', 'search_connections', 'search_posts', 'list_experience')
    $actualTools = @($listed.result.tools | ForEach-Object { $_.name } | Sort-Object)
    $expectedTools = @($expectedTools | Sort-Object)
    Assert-Equal (($actualTools -join ',')) (($expectedTools -join ',')) 'MCP tool list differs'
    if (@($listed.result.tools | Where-Object { -not $_.annotations.readOnlyHint }).Count -gt 0) {
        throw 'One or more tools are missing the read-only annotation.'
    }

    $profile = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'get_profile_summary'))
    Assert-Equal $profile.name 'Demo User' 'Profile tool returned the wrong fake profile'
    Assert-Equal $profile.connection_count 2 'Profile tool returned the wrong connection count'

    $connections = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_connections', '--tool-arg', 'query=acme'
    ))
    Assert-Equal $connections.count 1 'Connection search returned the wrong count'
    Assert-Equal $connections.results[0].name 'Alex Example' 'Connection search returned the wrong person'
    Assert-Equal $connections.results[0].url 'https://example.invalid/alex' 'Connection URL was not passed through'
    if (($connections | ConvertTo-Json -Depth 8) -match 'alex@example\.invalid') {
        throw 'Connection email was exposed in the public tool result.'
    }

    $connectionLimit = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_connections', '--tool-arg', 'query=a', '--tool-arg', 'limit=1'
    ))
    Assert-Equal $connectionLimit.count 1 'Connection result limit was not applied'
    $noConnections = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_connections', '--tool-arg', 'query=notfound'
    ))
    Assert-Equal $noConnections.count 0 'No-match connection query should return zero results'
    $posts = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_posts', '--tool-arg', 'query=mcp'
    ))
    Assert-Equal $posts.count 1 'Post search returned the wrong count'
    Assert-Equal $posts.results[0].date '2024-03-01' 'Post search returned the wrong post'
    Assert-Equal $posts.results[0].link 'https://example.invalid/post-1' 'Post link was not passed through'
    $postLimit = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_posts', '--tool-arg', 'query=synthetic', '--tool-arg', 'limit=1'
    ))
    Assert-Equal $postLimit.count 1 'Post result limit was not applied'
    $noPosts = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_posts', '--tool-arg', 'query=notfound'
    ))
    Assert-Equal $noPosts.count 0 'No-match post query should return zero results'
    $longPostResult = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_posts', '--tool-arg', 'query=longtoken'
    ))
    $returnedLongPost = $longPostResult.results[0].text
    if (-not $returnedLongPost.StartsWith($longPost.Substring(0, 500))) {
        throw 'Long post did not preserve its first 500 characters.'
    }
    if ($returnedLongPost.Length -le 500 -or $returnedLongPost.Length -ge $longPost.Length) {
        throw 'Long post was not truncated with a suffix after its first 500 characters.'
    }

    $experience = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'list_experience'))
    Assert-Equal $experience.positions.Count 1 'Experience tool returned the wrong positions count'
    Assert-Equal $experience.positions[0].title 'Test Engineer' 'Experience tool returned the wrong position'
    Assert-Equal (($experience.skills -join ',')) 'Python,Testing' 'Experience tool returned the wrong skills'

    $resources = Invoke-Inspector 'resources/list'
    if (-not (@($resources.result.resources | ForEach-Object { $_.uri }) -contains 'linkedin://schema')) {
        throw 'linkedin://schema resource was not listed.'
    }
    $schema = Invoke-Inspector 'resources/read' @('--uri', 'linkedin://schema')
    $schemaText = $schema.result.contents[0].text | ConvertFrom-Json
    if (-not ($schemaText.not_included -contains 'messages')) {
        throw 'Schema resource did not describe excluded private messages.'
    }
    if (-not ($schemaText.not_included -contains 'connection emails')) {
        throw 'Schema resource did not describe excluded connection emails.'
    }
    Assert-Equal $schemaText.counts.connections 2 'Schema reported the wrong connection count'
    Assert-Equal $schemaText.counts.posts 3 'Schema reported the wrong post count'

    $emptyProfile = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'get_profile_summary') -Server 'linkedin-empty')
    if (-not $emptyProfile.error) { throw 'Missing profile should produce a clear error result.' }
    $emptyConnections = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_connections', '--tool-arg', 'query=any'
    ) -Server 'linkedin-empty')
    Assert-Equal $emptyConnections.count 0 'Missing connection CSV should return zero results'
    $emptyPosts = Get-ToolPayload (Invoke-Inspector 'tools/call' @(
        '--tool-name', 'search_posts', '--tool-arg', 'query=any'
    ) -Server 'linkedin-empty')
    Assert-Equal $emptyPosts.count 0 'Missing shares CSV should return zero results'
    $emptyExperience = Get-ToolPayload (Invoke-Inspector 'tools/call' @('--tool-name', 'list_experience') -Server 'linkedin-empty')
    Assert-Equal $emptyExperience.positions.Count 0 'Missing positions CSV should return an empty list'
    Assert-Equal $emptyExperience.skills.Count 0 'Missing skills CSV should return an empty list'

    Write-Host 'PASS: MCP Inspector E2E checks passed for protocol, all 4 tools, result edges, missing files, privacy, links, truncation, and linkedin://schema.'
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
