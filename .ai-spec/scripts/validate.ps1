$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$testScript = Join-Path $root 'tests\template.tests.ps1'
$installTestScript = Join-Path $root 'tests\install.tests.ps1'
$skillTestScript = Join-Path $root 'tests\skills.tests.ps1'

$isTemplateRepository = (Test-Path -LiteralPath $testScript -PathType Leaf) -and
    (Test-Path -LiteralPath $installTestScript -PathType Leaf) -and
    (Test-Path -LiteralPath $skillTestScript -PathType Leaf)

if ($isTemplateRepository) {
    & $testScript
    & $installTestScript
    & $skillTestScript
}
else {
    foreach ($requiredPath in @(
        'AI-START.md',
        'README.md',
        'ai-spec.yaml',
        'business\quick-ref.md',
        'core\architecture.md',
        'core\delivery-standard.md',
        'core\security-standard.md',
        'core-lite\delivery-lite.md',
        'core-lite\security-lite.md',
        'core-lite\testing-lite.md',
        'scripts\validate.ps1'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $requiredPath))) {
            throw "Missing installed spec file: $requiredPath"
        }
    }
    Write-Host 'Installed spec structure validation passed.' -ForegroundColor Green
}

$settingsPath = Join-Path $root 'adapters\claude-code\settings.json.template'
if (Test-Path -LiteralPath $settingsPath -PathType Leaf) {
    try {
        Get-Content -Raw -Encoding UTF8 -LiteralPath $settingsPath | ConvertFrom-Json | Out-Null
    }
    catch {
        Write-Host "Invalid JSON template: $settingsPath" -ForegroundColor Red
        throw
    }
}

$brokenLinks = [System.Collections.Generic.List[string]]::new()
$markdownFiles = Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.md' |
    Where-Object { $_.FullName -notmatch '[\\/]docs[\\/]legacy[\\/]' }

foreach ($file in $markdownFiles) {
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName
    $matches = [regex]::Matches($content, '\[[^\]]+\]\(([^)]+)\)')
    foreach ($match in $matches) {
        $target = $match.Groups[1].Value.Trim('<', '>')
        if ($target -match '^(https?://|#|mailto:)' -or $target.Contains('{{')) { continue }
        $targetWithoutAnchor = $target.Split('#')[0]
        if ([string]::IsNullOrWhiteSpace($targetWithoutAnchor)) { continue }
        $resolved = Join-Path $file.DirectoryName $targetWithoutAnchor
        if (-not (Test-Path -LiteralPath $resolved)) {
            $relativeFile = $file.FullName.Substring($root.Length + 1)
            $brokenLinks.Add("$relativeFile -> $target")
        }
    }
}

if ($brokenLinks.Count -gt 0) {
    Write-Host 'Broken local Markdown links:' -ForegroundColor Red
    foreach ($link in $brokenLinks) { Write-Host "- $link" -ForegroundColor Red }
    exit 1
}

Write-Host 'Structure, policy, skill, JSON, and Markdown link validation passed.' -ForegroundColor Green
