$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$failures = [System.Collections.Generic.List[string]]::new()

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $script:failures.Add($Message) }
}

$skills = @{
    'product-architect' = @(
        'references/discovery-and-modeling.md',
        'references/solution-mapping.md',
        'references/deliverable-templates.md',
        'references/review-checklist.md'
    )
    'dev-implementation' = @(
        'references/repository-investigation.md',
        'references/implementation-workflows.md',
        'references/integration-and-permissions.md',
        'references/delivery-templates.md',
        'references/review-checklist.md'
    )
}

foreach ($skillName in $skills.Keys) {
    $skillRoot = Join-Path $root "skills\$skillName"
    $skillPath = Join-Path $skillRoot 'SKILL.md'
    $metadataPath = Join-Path $skillRoot 'agents\openai.yaml'

    Assert-True (Test-Path -LiteralPath $skillPath -PathType Leaf) "$skillName missing SKILL.md"
    Assert-True (Test-Path -LiteralPath $metadataPath -PathType Leaf) "$skillName missing agents/openai.yaml"

    foreach ($relativePath in $skills[$skillName]) {
        Assert-True (Test-Path -LiteralPath (Join-Path $skillRoot $relativePath) -PathType Leaf) "$skillName missing $relativePath"
    }

    if (Test-Path -LiteralPath $skillPath -PathType Leaf) {
        $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $skillPath
        Assert-True ($content.Contains('references/')) "$skillName does not route reference files"
        Assert-True ($content.Contains('confirmed facts')) "$skillName does not separate facts from assumptions"
        Assert-True ($content.Contains('project-native')) "$skillName does not preserve project-native conventions"
        Assert-True (-not ($content -match '(?m)^(when_to_use|user-invocable):')) "$skillName uses unsupported frontmatter"
    }

    if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
        $metadata = Get-Content -Raw -Encoding UTF8 -LiteralPath $metadataPath
        Assert-True ($metadata.Contains("`$$skillName")) "$skillName default prompt does not explicitly invoke the skill"
    }
}

$skillFiles = Get-ChildItem -LiteralPath (Join-Path $root 'skills') -Recurse -File
$forbiddenPatterns = @(
    'yudao', 'bt-back', 'bt-web', 'bt-XXX', 'OpenClaw',
    'Spring', 'Vue', 'Java', 'Mapper', 'Controller'
)
foreach ($file in $skillFiles) {
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName
    foreach ($pattern in $forbiddenPatterns) {
        Assert-True (-not ($content -match [regex]::Escape($pattern))) "$($file.FullName) contains framework/project binding: $pattern"
    }
}

if ($failures.Count -gt 0) {
    Write-Host "Skill tests failed: $($failures.Count)" -ForegroundColor Red
    foreach ($failure in $failures) { Write-Host "- $failure" -ForegroundColor Red }
    exit 1
}

Write-Host 'Skill tests passed.' -ForegroundColor Green
