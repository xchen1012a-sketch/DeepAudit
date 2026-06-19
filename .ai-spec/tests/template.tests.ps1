$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$failures = [System.Collections.Generic.List[string]]::new()

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { $script:failures.Add($Message) }
}

function Read-ProjectFile {
    param([string]$RelativePath)
    $path = Join-Path $root $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $script:failures.Add("Missing file: $RelativePath")
        return ''
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $path
}

$requiredFiles = @(
    'AI-START.md',
    'README.md',
    'ai-spec.example.yaml',
    'adapters/README.md',
    'adapters/claude-code/CLAUDE.md.template',
    'adapters/claude-code/settings.json.template',
    'adapters/codex/AGENTS.md.template',
    'adapters/cursor/ai-spec.mdc.template',
    'adapters/github-copilot/copilot-instructions.md.template',
    'adapters/generic/START-PROMPT.md',
    'business/quick-ref.md',
    'core-lite/delivery-lite.md',
    'core-lite/security-lite.md',
    'core-lite/testing-lite.md',
    'core/command-standard.md',
    'workflows/new-project.md',
    'workflows/existing-project.md',
    'workflows/in-progress-project.md',
    'governance/policy-levels.md',
    'governance/exception-template.md',
    'governance/adr-template.md',
    'governance/rfc-template.md',
    'governance/risk-register-template.md',
    'governance/handoff-template.md',
    'governance/ownership-template.md',
    'skills/product-architect/SKILL.md',
    'skills/dev-implementation/SKILL.md',
    'scripts/install.ps1',
    'scripts/validate.ps1'
)

foreach ($relativePath in $requiredFiles) {
    Assert-True (Test-Path -LiteralPath (Join-Path $root $relativePath) -PathType Leaf) "Missing file: $relativePath"
}

# Root .md whitelist: AI-START.md, README.md, and any manual with prefix "AI"
$rootMarkdown = @(Get-ChildItem -LiteralPath $root -File -Filter '*.md' | Select-Object -ExpandProperty Name)
$allowedRootMarkdown = @('AI-START.md', 'README.md')
$unexpectedRootMarkdown = @($rootMarkdown | Where-Object {
    $_ -notin $allowedRootMarkdown -and $_ -notmatch '^AI.*\.md$'
})
Assert-True ($unexpectedRootMarkdown.Count -eq 0) "Unexpected root Markdown: $($unexpectedRootMarkdown -join ', ')"

$start = Read-ProjectFile 'AI-START.md'
foreach ($section in @('Startup Protocol', 'Project Stage Detection', 'AI Tool Detection', 'Security Baseline', 'Context Routing', 'Delivery Protocol')) {
    Assert-True ($start.Contains($section)) "AI-START.md missing section marker: $section"
}
Assert-True ($start.Contains('new-project')) 'AI-START.md does not route new projects'
Assert-True ($start.Contains('existing-project')) 'AI-START.md does not route existing projects'
Assert-True ($start.Contains('in-progress-project')) 'AI-START.md does not route in-progress projects'
Assert-True ($start.Contains('generic')) 'AI-START.md has no generic fallback'
Assert-True ($start.Contains('上下文预算')) 'AI-START.md missing context budget protocol'
Assert-True ($start.Contains('状态: GENERATED')) 'AI-START.md quick recovery does not require generated quick-ref status'
Assert-True ($start.Contains('上下文使用报告')) 'AI-START.md does not require context usage reporting'
Assert-True ($start.Contains('受控例外')) 'AI-START.md does not define controlled exceptions'
Assert-True ($start.Contains('初始基线 commit')) 'AI-START.md does not clarify the no-Git initial commit exception'
Assert-True ($start.Contains('quick-ref.md 是日常启动唯一入口')) 'AI-START.md does not make quick-ref the daily startup entry'
Assert-True ($start.Contains('core-lite/delivery-lite.md')) 'AI-START.md does not route simple tasks to core-lite'
Assert-True ($start.Contains('projectSize')) 'AI-START.md missing project size routing'
Assert-True ($start.Contains('tiny | small | medium | large | enterprise')) 'AI-START.md missing project size levels'
Assert-True ($start.Contains('Git 提交硬性门禁')) 'AI-START.md missing hard git commit gate'
Assert-True ($start.Contains('只提交纯代码')) 'AI-START.md missing pure-code commit rule'
Assert-True ($start.Contains('暂存区必须检查')) 'AI-START.md missing staging-area check rule'
Assert-True ($start.Contains('templateVersion')) 'AI-START.md missing template version consistency rule'
Assert-True ($start.Contains('install.ps1 -Sync')) 'AI-START.md missing sync command rule'
Assert-True ($start.Contains('不得自动覆盖')) 'AI-START.md missing no-automatic-sync-overwrite rule'
Assert-True ($start.Contains('先澄清假设')) 'AI-START.md missing clarify-assumptions coding discipline'
Assert-True ($start.Contains('简单优先')) 'AI-START.md missing simplicity-first coding discipline'
Assert-True ($start.Contains('外科式改动')) 'AI-START.md missing surgical-change coding discipline'
Assert-True ($start.Contains('目标驱动验证')) 'AI-START.md missing goal-driven verification discipline'
foreach ($mode in @('L0 快速恢复', 'L1 机械改动', 'L2 标准改动', 'L3 高风险改动', 'L4 接入/审计')) {
    Assert-True ($start.Contains($mode)) "AI-START.md missing context budget mode: $mode"
}

$quickRef = Read-ProjectFile 'business/quick-ref.md'
Assert-True ($quickRef.Contains('状态: TEMPLATE_PLACEHOLDER')) 'quick-ref.md missing placeholder status marker'
Assert-True ($quickRef.Contains('生成后改为 GENERATED')) 'quick-ref.md does not explain generated status transition'
Assert-True ($quickRef.Contains('动态上下文门禁')) 'quick-ref.md missing dynamic context gate'
Assert-True ($quickRef.Contains('日常启动唯一入口')) 'quick-ref.md is not documented as the daily startup entry'
Assert-True ($quickRef.Contains('projectSize:')) 'quick-ref.md missing project size marker'
Assert-True ($quickRef.Contains('sizeStrategy:')) 'quick-ref.md missing size-based loading strategy marker'

foreach ($lite in @('core-lite/delivery-lite.md', 'core-lite/security-lite.md', 'core-lite/testing-lite.md')) {
    $liteContent = Read-ProjectFile $lite
    Assert-True ($liteContent.Contains('appliesTo:')) "$lite missing appliesTo frontmatter"
    Assert-True ($liteContent.Contains('loadWhen:')) "$lite missing loadWhen frontmatter"
}

$specExample = Read-ProjectFile 'ai-spec.example.yaml'
Assert-True ($specExample.Contains('context:')) 'ai-spec.example.yaml missing context configuration'
Assert-True ($specExample.Contains('projectSize: auto')) 'ai-spec.example.yaml missing project size default'
Assert-True ($specExample.Contains('projectSizeSignals:')) 'ai-spec.example.yaml missing project size signals'
Assert-True ($specExample.Contains('quickRefStatus: TEMPLATE_PLACEHOLDER')) 'ai-spec.example.yaml missing quick-ref status default'

foreach ($routedFile in @(
    'core/delivery-standard.md',
    'core/security-standard.md',
    'core/testing-standard.md',
    'contracts/api-contract-standard.md',
    'contracts/integration-standard.md',
    'stacks/frontend-general.md',
    'stacks/backend-general.md'
)) {
    $routedContent = Read-ProjectFile $routedFile
    $normalizedRoutedContent = $routedContent.TrimStart([char]0xFEFF, [char]0x200B, " ", "`r", "`n", "`t")
    Assert-True ($normalizedRoutedContent.StartsWith('---')) "$routedFile missing routing frontmatter"
    Assert-True ($routedContent.Contains('appliesTo:')) "$routedFile missing appliesTo frontmatter"
    Assert-True ($routedContent.Contains('loadWhen:')) "$routedFile missing loadWhen frontmatter"
    Assert-True (([regex]::Matches($routedContent, '(?m)^appliesTo:')).Count -eq 1) "$routedFile has duplicate appliesTo frontmatter"
    Assert-True (([regex]::Matches($routedContent, '(?m)^loadWhen:')).Count -eq 1) "$routedFile has duplicate loadWhen frontmatter"
    Assert-True (([regex]::Matches($routedContent, '(?m)^fallbackTo:')).Count -eq 1) "$routedFile has duplicate fallbackTo frontmatter"
}

$securityStandard = Read-ProjectFile 'core/security-standard.md'
Assert-True ($securityStandard.Contains('Git 提交硬性门禁')) 'security standard missing hard git commit gate'
Assert-True ($securityStandard.Contains('暂存区必须检查')) 'security standard missing staging-area check'
Assert-True ($securityStandard.Contains('只提交纯代码')) 'security standard missing pure-code commit rule'
Assert-True ($securityStandard.Contains('.env')) 'security standard missing env-file filter'
Assert-True ($securityStandard.Contains('IDE 配置')) 'security standard missing IDE config filter'
Assert-True ($securityStandard.Contains('构建产物')) 'security standard missing build artifact filter'

foreach ($skill in @('product-architect', 'dev-implementation')) {
    $relativePath = "skills/$skill/SKILL.md"
    $content = Read-ProjectFile $relativePath
    Assert-True ($content -match "(?ms)^---\s*\nname:\s*$skill\s*\ndescription:") "$relativePath has invalid frontmatter"
    Assert-True (-not ($content -match '(?m)^trigger:')) "$relativePath uses non-standard trigger field"
}

$settings = Read-ProjectFile 'adapters/claude-code/settings.json.template'
foreach ($dangerousRule in @(
    'Bash(npm *)', 'Bash(pip *)', 'Bash(python *)', 'Bash(docker *)',
    'Bash(curl *)', 'Bash(redis-cli *)', 'Bash(git checkout *)'
)) {
    Assert-True (-not $settings.Contains($dangerousRule)) "Unsafe default Claude permission: $dangerousRule"
}

$activeTextFiles = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object {
        $_.Extension -in @('.md', '.template', '.json', '.yaml', '.yml') -and
        $_.FullName -notmatch '[\\/]docs[\\/]legacy[\\/]'
    }

foreach ($file in $activeTextFiles) {
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName
    $relativePath = $file.FullName.Substring($root.Length + 1)
    Assert-True (-not $content.Contains('USAGE.md')) "$relativePath references missing USAGE.md"
    Assert-True (-not ($content -match '\.claude/skills/[^/\s`]+\.md')) "$relativePath uses a flat skill path"
    if ($relativePath -notmatch '^adapters[\\/]' -and $relativePath -notmatch '^(scripts|tests)[\\/]') {
        Assert-True (-not ($content -match '\{\{[A-Z_][A-Z0-9_]*\}\}')) "$relativePath contains an unresolved runtime placeholder"
    }
}

$integration = Read-ProjectFile 'contracts/integration-standard.md'
$passwordCodePoints = @(23494, 30721)
$passwordWord = -join ($passwordCodePoints | ForEach-Object { [char]$_ })
Assert-True (-not ($integration.Contains($passwordWord))) 'Integration standard asks for a plaintext password'

if ($failures.Count -gt 0) {
    Write-Host "V2 template tests failed: $($failures.Count)" -ForegroundColor Red
    foreach ($failure in $failures) { Write-Host "- $failure" -ForegroundColor Red }
    exit 1
}

Write-Host 'V2 template tests passed.' -ForegroundColor Green
