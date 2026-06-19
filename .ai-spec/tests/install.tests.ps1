$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $root 'scripts\install.ps1'
$tempRoot = [System.IO.Path]::GetFullPath((Join-Path $env:TEMP ("ai-spec-v2-test-" + [guid]::NewGuid().ToString('N'))))

function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    $safeRoot = Join-Path $tempRoot 'safe-copy'
    New-Item -ItemType Directory -Force -Path $safeRoot | Out-Null
    $ownedClaude = Join-Path $safeRoot 'CLAUDE.md'
    [System.IO.File]::WriteAllText($ownedClaude, 'user-owned', [System.Text.UTF8Encoding]::new($false))

    & $installer -TargetRoot $safeRoot -Mode existing -Tools 'claude-code,codex,cursor,github-copilot' -Apply *> $null

    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.ai-spec\AI-START.md')) 'Installer did not copy AI-START.md'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.ai-spec\ai-spec.yaml')) 'Installer did not create ai-spec.yaml'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot 'AGENTS.md')) 'Installer did not create AGENTS.md'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.cursor\rules\ai-spec.mdc')) 'Installer did not create Cursor rules'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.github\copilot-instructions.md')) 'Installer did not create Copilot instructions'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.claude\settings.json')) 'Installer did not create Claude settings'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.agents\skills\product-architect\SKILL.md')) 'Installer did not create Codex skill'
    Assert-Test (Test-Path -LiteralPath (Join-Path $safeRoot '.claude\skills\dev-implementation\SKILL.md')) 'Installer did not create Claude skill'
    Assert-Test ((Get-Content -Raw -Encoding UTF8 -LiteralPath $ownedClaude) -eq 'user-owned') 'Installer overwrote an existing CLAUDE.md'

    $agents = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $safeRoot 'AGENTS.md')
    Assert-Test (-not $agents.Contains('{{')) 'Installer left placeholders in AGENTS.md'

    $profile = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $safeRoot '.ai-spec\ai-spec.yaml')
    Assert-Test ($profile.Contains('stage: existing')) 'Installer did not write the selected project stage'

    & (Join-Path $safeRoot '.ai-spec\tests\template.tests.ps1') *> $null

    $gitPlan = & $installer -TargetRoot $safeRoot -Mode existing -Tools 'generic' -Onboard -ManageGit 6>&1
    $gitPlanText = [string]::Join("`n", @($gitPlan))
    Assert-Test ($gitPlanText.Contains('GIT init/add/initial-commit')) 'ManageGit dry-run did not plan the controlled initial commit'
    Assert-Test ($gitPlanText.Contains('GIT create branch chore/specforge-onboard')) 'ManageGit dry-run did not plan onboarding branch creation'

    $monoRoot = Join-Path $tempRoot 'multi-project'
    $frontend = Join-Path $monoRoot 'frontend'
    $backend = Join-Path $monoRoot 'backend'
    New-Item -ItemType Directory -Force -Path $frontend | Out-Null
    New-Item -ItemType Directory -Force -Path $backend | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $frontend 'package.json'), '{"dependencies":{"react":"latest","vite":"latest"}}', [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $backend 'go.mod'), "module example.com/backend`n", [System.Text.UTF8Encoding]::new($false))

    & $installer -TargetRoot $monoRoot -Mode auto -Tools 'codex' -Onboard -Apply *> $null

    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $monoRoot '.ai-spec'))) 'Onboard mode installed a parent .ai-spec for a multi-project root'
    Assert-Test (Test-Path -LiteralPath (Join-Path $monoRoot '.specforge.json')) 'Onboard mode did not create parent .specforge.json'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\AI-START.md')) 'Onboard mode did not install frontend .ai-spec'
    Assert-Test (Test-Path -LiteralPath (Join-Path $backend '.ai-spec\AI-START.md')) 'Onboard mode did not install backend .ai-spec'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend 'AGENTS.md')) 'Onboard mode did not create frontend Codex entry'
    Assert-Test (Test-Path -LiteralPath (Join-Path $backend 'AGENTS.md')) 'Onboard mode did not create backend Codex entry'

    $index = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $monoRoot '.specforge.json') | ConvertFrom-Json
    Assert-Test ($index.templateVersion -eq 2) 'Parent .specforge.json missing templateVersion'
    Assert-Test ($index.templateSource -eq 'SpecForge') 'Parent .specforge.json missing templateSource'
    Assert-Test (-not [string]::IsNullOrWhiteSpace([string]$index.multiProjectId)) 'Parent .specforge.json missing multiProjectId'
    Assert-Test ($index.projects.Count -eq 2) 'Parent .specforge.json should contain two projects'
    Assert-Test (@($index.projects.path) -contains 'frontend') 'Parent .specforge.json missing frontend project'
    Assert-Test (@($index.projects.path) -contains 'backend') 'Parent .specforge.json missing backend project'

    $frontendProfile = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $frontend '.ai-spec\ai-spec.yaml')
    Assert-Test ($frontendProfile.Contains('templateVersion: 2')) 'Frontend profile did not record templateVersion'
    Assert-Test ($frontendProfile.Contains('type: frontend')) 'Frontend profile did not record frontend type'
    Assert-Test ($frontendProfile.Contains("multiProjectId: $($index.multiProjectId)")) 'Frontend profile did not receive shared multiProjectId'
    Assert-Test ($frontendProfile.Contains('quickRefStatus: TEMPLATE_PLACEHOLDER')) 'Frontend profile missing quick-ref placeholder status'
    Assert-Test ($frontendProfile.Contains('projectSize: tiny')) 'Frontend profile did not record tiny project size'
    Assert-Test ($frontendProfile.Contains('fileCount: 1')) 'Frontend profile did not record project file count'
    Assert-Test ($frontendProfile.Contains('hasApi: false')) 'Frontend profile did not record API signal'
    Assert-Test ($frontendProfile.Contains('hasAuth: false')) 'Frontend profile did not record auth signal'
    $frontendQuickRef = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $frontend '.ai-spec\business\quick-ref.md')
    Assert-Test ($frontendQuickRef.Contains('TEMPLATE_PLACEHOLDER')) 'Installed quick-ref missing placeholder status'
    Assert-Test ($frontendQuickRef.Contains('dailyEntry: true')) 'Installed quick-ref is not the daily startup entry'
    Assert-Test ($frontendQuickRef.Contains('dynamicContextGate: true')) 'Installed quick-ref missing dynamic context gate'
    Assert-Test ($frontendQuickRef.Contains('projectSize: tiny')) 'Installed quick-ref missing project size'
    Assert-Test ($frontendQuickRef.Contains('sizeStrategy: ultra-lite')) 'Installed quick-ref missing tiny size strategy'

    $frontendRules = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $frontend '.ai-spec\business\business-rules.md')
    Assert-Test ($frontendRules.Contains('omittedSections:')) 'Installed business-rules should record omitted sections'
    Assert-Test ($frontendRules.Contains('section: business-positioning')) 'Installed business-rules missing required positioning section'
    Assert-Test ($frontendRules.Contains('section: business-domains')) 'Installed business-rules missing required domain section'
    Assert-Test ($frontendRules.Contains('section: data-write-rules')) 'Installed business-rules missing required write-rules section'
    Assert-Test ($frontendRules.Contains('section: business-invariants')) 'Installed business-rules missing required invariants section'
    Assert-Test (-not $frontendRules.Contains('section: organization-identity')) 'Business-rules kept organization section without auth signal'
    Assert-Test (-not $frontendRules.Contains('section: kpi-metrics')) 'Business-rules kept KPI section without analytics signal'
    Assert-Test (-not $frontendRules.Contains('section: state-machines')) 'Business-rules kept state-machine section without state signal'
    Assert-Test (-not $frontendRules.Contains('section: menu-permissions')) 'Business-rules kept permission menu section without admin/auth signal'
    Assert-Test (-not $frontendRules.Contains('section: external-integrations')) 'Business-rules kept external integration section without integration signal'

    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\stacks\frontend-general.md')) 'Frontend stack was not retained'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\stacks\backend-general.md'))) 'Frontend stack slimming kept backend rules'
    Assert-Test (Test-Path -LiteralPath (Join-Path $backend '.ai-spec\stacks\backend-general.md')) 'Backend stack was not retained'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $backend '.ai-spec\stacks\frontend-general.md'))) 'Backend stack slimming kept frontend rules'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\core-lite\delivery-lite.md')) 'Onboard mode did not keep delivery-lite'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\core-lite\security-lite.md')) 'Onboard mode did not keep security-lite'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\core-lite\testing-lite.md')) 'Onboard mode did not keep testing-lite'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\tests'))) 'Onboard mode did not remove template self-tests'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\scripts\install.ps1'))) 'Onboard mode did not remove one-time installer'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\scripts\validate.ps1')) 'Onboard mode removed validate.ps1'
    Assert-Test (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\adapters\codex')) 'Onboard mode did not retain selected adapter'
    Assert-Test (-not (Test-Path -LiteralPath (Join-Path $frontend '.ai-spec\adapters\cursor'))) 'Onboard mode kept unused adapter'
    & (Join-Path $frontend '.ai-spec\scripts\validate.ps1') *> $null

    $frontendStart = Join-Path $frontend '.ai-spec\AI-START.md'
    $frontendRulesPath = Join-Path $frontend '.ai-spec\business\business-rules.md'
    $frontendProfilePath = Join-Path $frontend '.ai-spec\ai-spec.yaml'
    [System.IO.File]::WriteAllText($frontendStart, 'old-start', [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($frontendRulesPath, 'project-owned-business-rules', [System.Text.UTF8Encoding]::new($false))
    $profileBeforeSync = Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendProfilePath

    $syncPlan = & $installer -TargetRoot $monoRoot -Sync 6>&1
    $syncPlanText = [string]::Join("`n", @($syncPlan))
    Assert-Test ($syncPlanText.Contains('SYNC')) 'Sync dry-run did not report planned core-file updates'
    Assert-Test ((Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendStart) -eq 'old-start') 'Sync dry-run modified AI-START.md'

    & $installer -TargetRoot $monoRoot -Sync -Apply *> $null

    Assert-Test ((Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendStart).Contains('Startup Protocol')) 'Sync did not refresh AI-START.md'
    Assert-Test ((Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendRulesPath) -eq 'project-owned-business-rules') 'Sync overwrote project-owned business rules'
    Assert-Test ((Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendProfilePath) -eq $profileBeforeSync) 'Sync overwrote ai-spec.yaml'

    Write-Host 'Installer integration tests passed.' -ForegroundColor Green
}
finally {
    $resolvedTempBase = [System.IO.Path]::GetFullPath($env:TEMP)
    if ($tempRoot.StartsWith($resolvedTempBase) -and (Split-Path -Leaf $tempRoot).StartsWith('ai-spec-v2-test-')) {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }
}
