[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,

    [ValidateSet('auto', 'new', 'existing', 'in-progress')]
    [string]$Mode = 'auto',

    [string[]]$Tools = @('generic'),

    [switch]$Apply,

    [switch]$Onboard,

    [switch]$Sync,

    [switch]$ManageGit,

    [string]$BranchName = 'chore/specforge-onboard'
)

$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$targetFullPath = [System.IO.Path]::GetFullPath($TargetRoot)
$validTools = @('generic', 'claude-code', 'codex', 'cursor', 'github-copilot')
$Tools = @($Tools | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique)
$invalidTools = @($Tools | Where-Object { $_ -notin $validTools })
if ($invalidTools.Count -gt 0) {
    throw "Unsupported tool adapter: $($invalidTools -join ', '). Use generic for unknown tools."
}

if (-not (Test-Path -LiteralPath $targetFullPath -PathType Container)) {
    throw "Target project directory does not exist: $targetFullPath"
}

if ($targetFullPath -eq [System.IO.Path]::GetFullPath($sourceRoot)) {
    throw 'Target project cannot be the template source directory.'
}

$actions = [System.Collections.Generic.List[string]]::new()
$conflicts = [System.Collections.Generic.List[string]]::new()
$installReports = [System.Collections.Generic.List[hashtable]]::new()

function Get-TemplateVersion {
    $examplePath = Join-Path $sourceRoot 'ai-spec.example.yaml'
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $examplePath
    $match = [regex]::Match($content, '(?m)^  templateVersion:\s*(\d+)')
    if (-not $match.Success) {
        throw 'Cannot determine SpecForge templateVersion from ai-spec.example.yaml'
    }
    return [int]$match.Groups[1].Value
}

$templateVersion = Get-TemplateVersion

function Read-FileIfExists {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-Content -Raw -Encoding UTF8 -LiteralPath $Path)
    }
    return ''
}

function Test-PathAny {
    param([string]$RootDir, [string[]]$RelativePaths)
    foreach ($relativePath in $RelativePaths) {
        if (Test-Path -LiteralPath (Join-Path $RootDir $relativePath)) { return $true }
    }
    return $false
}

function Detect-Mode {
    param([string]$ProjectRoot)

    $gitDirectory = Join-Path $ProjectRoot '.git'
    if (Test-Path -LiteralPath $gitDirectory) {
        try {
            $status = & git -C $ProjectRoot status --short 2>$null
            if ($status) { return 'in-progress' }
        }
        catch { }
    }

    $signals = @(
        'package.json', 'pom.xml', 'build.gradle', 'build.gradle.kts',
        'pyproject.toml', 'requirements.txt', 'go.mod', 'Cargo.toml',
        'composer.json', 'mix.exs', 'src', 'app', 'backend', 'frontend'
    )
    foreach ($signal in $signals) {
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot $signal)) {
            return 'existing'
        }
    }

    return 'new'
}

function Detect-SubProjects {
    param([string]$RootDir)

    $buildFiles = @(
        'package.json', 'pom.xml', 'go.mod', 'Cargo.toml',
        'requirements.txt', 'pyproject.toml', 'Makefile',
        'build.gradle', 'build.gradle.kts', 'composer.json',
        'mix.exs', 'CMakeLists.txt', 'BUILD', 'WORKSPACE'
    )
    $sourceDirs = @('src', 'app', 'lib')

    $projects = [System.Collections.Generic.List[hashtable]]::new()
    $children = Get-ChildItem -LiteralPath $RootDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '^\.' -and $_.Name -notin @('node_modules', 'vendor') }

    foreach ($child in $children) {
        $isProject = $false
        $foundBuildFiles = [System.Collections.Generic.List[string]]::new()

        foreach ($buildFile in $buildFiles) {
            if (Test-Path -LiteralPath (Join-Path $child.FullName $buildFile)) {
                $isProject = $true
                $null = $foundBuildFiles.Add($buildFile)
            }
        }
        foreach ($sourceDir in $sourceDirs) {
            if (Test-Path -LiteralPath (Join-Path $child.FullName $sourceDir) -PathType Container) {
                $isProject = $true
            }
        }

        if ($isProject) {
            $projects.Add(@{
                path = $child.FullName
                name = $child.Name
                buildFiles = @($foundBuildFiles)
            })
        }
    }

    return @($projects)
}

function Detect-ProjectType {
    param([string]$ProjectRoot)

    if (Test-PathAny -RootDir $ProjectRoot -RelativePaths @('pubspec.yaml', 'android', 'ios')) {
        return 'mobile'
    }

    $packageJson = (Read-FileIfExists -Path (Join-Path $ProjectRoot 'package.json')).ToLowerInvariant()
    if ($packageJson) {
        $hasFrontend = $packageJson -match '"(react|vue|@angular/core|next|nuxt|svelte|vite)"'
        $hasBackend = $packageJson -match '"(express|fastify|@nestjs/core|koa|hapi)"'
        if ($hasFrontend -and $hasBackend) { return 'fullstack' }
        if ($hasFrontend) { return 'frontend' }
        if ($hasBackend) { return 'backend' }
        return 'frontend'
    }

    $pythonSignals = ((Read-FileIfExists -Path (Join-Path $ProjectRoot 'requirements.txt')) + "`n" + (Read-FileIfExists -Path (Join-Path $ProjectRoot 'pyproject.toml'))).ToLowerInvariant()
    if ($pythonSignals.Trim()) {
        if ($pythonSignals -match '(openai|langchain|llama-index|llamaindex|transformers|sentence-transformers|chromadb|faiss)') {
            return 'ai-llm'
        }
        return 'backend'
    }

    if (Test-PathAny -RootDir $ProjectRoot -RelativePaths @('pom.xml', 'build.gradle', 'build.gradle.kts', 'go.mod', 'composer.json', 'mix.exs')) {
        return 'backend'
    }

    if (Test-PathAny -RootDir $ProjectRoot -RelativePaths @('Cargo.toml', 'CMakeLists.txt', 'BUILD', 'WORKSPACE')) {
        return 'library-sdk'
    }

    if (Test-PathAny -RootDir $ProjectRoot -RelativePaths @('bin', '__main__.py', 'main.go', 'main.rs')) {
        return 'cli'
    }

    return 'generic'
}

function Get-StackFilesForType {
    param([string]$ProjectType)

    switch ($ProjectType) {
        'frontend' { return @('frontend-general.md') }
        'backend' { return @('backend-general.md') }
        'fullstack' { return @('frontend-general.md', 'backend-general.md') }
        'mobile' { return @('mobile-general.md') }
        'library-sdk' { return @('cli.md') }
        'cli' { return @('cli.md') }
        'data-platform' { return @('data-platform.md') }
        'ai-llm' { return @('ai-llm-app.md') }
        default { return @('ai-llm-app.md', 'backend-general.md', 'cli.md', 'data-platform.md', 'frontend-general.md', 'mobile-general.md') }
    }
}

function Add-FileFromSource {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        $script:conflicts.Add($Destination)
        return
    }

    $script:actions.Add("CREATE $Destination")
    if ($Apply) {
        $parent = Split-Path -Parent $Destination
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination
    }
}

function Add-RenderedFile {
    param(
        [string]$Source,
        [string]$Destination,
        [hashtable]$Variables
    )

    if (Test-Path -LiteralPath $Destination) {
        $script:conflicts.Add($Destination)
        return
    }

    $script:actions.Add("CREATE $Destination")
    if ($Apply) {
        $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $Source
        foreach ($key in $Variables.Keys) {
            $content = $content.Replace("{{$key}}", [string]$Variables[$key])
        }
        $parent = Split-Path -Parent $Destination
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        [System.IO.File]::WriteAllText($Destination, $content, [System.Text.UTF8Encoding]::new($false))
    }
}

function Remove-SpecPath {
    param(
        [string]$SpecRoot,
        [string]$RelativePath,
        [string]$Reason
    )

    $specFull = [System.IO.Path]::GetFullPath($SpecRoot).TrimEnd('\', '/')
    $target = Join-Path $SpecRoot $RelativePath
    $targetFull = [System.IO.Path]::GetFullPath($target)
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not ($targetFull -eq $specFull -or $targetFull.StartsWith($specFull + $separator))) {
        throw "Refusing to remove path outside .ai-spec: $targetFull"
    }

    if (Test-Path -LiteralPath $targetFull) {
        $script:actions.Add("REMOVE $targetFull ($Reason)")
        if ($Apply) {
            Remove-Item -LiteralPath $targetFull -Recurse -Force
        }
    }
}

function Write-AiSpecProfile {
    param(
        [string]$SpecRoot,
        [string]$ProjectRoot,
        [string]$Stage,
        [string]$ProjectType,
        [string]$MultiProjectId
    )

    $profileDestination = Join-Path $SpecRoot 'ai-spec.yaml'
    if (Test-Path -LiteralPath $profileDestination) {
        $script:conflicts.Add($profileDestination)
        return
    }

    $script:actions.Add("CREATE $profileDestination")
    if ($Apply) {
        $profile = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $sourceRoot 'ai-spec.example.yaml')
        $projectName = Split-Path -Leaf $ProjectRoot
        $multiValue = if ($MultiProjectId) { $MultiProjectId } else { 'null' }
        $toolsValue = '[' + ($Tools -join ', ') + ']'
        $inventory = Get-ProjectInventory -ProjectRoot $ProjectRoot -IsMultiProject ([bool]$MultiProjectId)

        $profile = $profile -replace '(?m)^  multiProjectId: null.*$', "  multiProjectId: $multiValue       # multi-project shared ID"
        $profile = $profile -replace '(?m)^  templateVersion:\s*\d+.*$', "  templateVersion: $templateVersion         # installed SpecForge template version"
        $profile = $profile -replace 'name: example-project', "name: $projectName"
        $profile = $profile -replace 'stage: new # new \| existing \| in-progress', "stage: $Stage # new | existing | in-progress"
        $profile = $profile -replace 'type: generic # backend \| frontend \| fullstack \| mobile \| library-sdk \| cli \| data-platform \| ai-llm \| generic', "type: $ProjectType # backend | frontend | fullstack | mobile | library-sdk | cli | data-platform | ai-llm | generic"
        $profile = $profile -replace 'tools: \[generic\]', "tools: $toolsValue"
        $profile = $profile -replace 'projectSize: auto # auto \| tiny \| small \| medium \| large \| enterprise', "projectSize: $($inventory.projectSize) # auto | tiny | small | medium | large | enterprise"
        $profile = $profile -replace 'fileCount: 0', "fileCount: $($inventory.fileCount)"
        $profile = $profile -replace 'buildFileCount: 0', "buildFileCount: $($inventory.buildFileCount)"
        $profile = $profile -replace 'hasDatabase: false', "hasDatabase: $($inventory.hasDatabase.ToString().ToLowerInvariant())"
        $profile = $profile -replace 'hasApi: false', "hasApi: $($inventory.hasApi.ToString().ToLowerInvariant())"
        $profile = $profile -replace 'hasAuth: false', "hasAuth: $($inventory.hasAuth.ToString().ToLowerInvariant())"
        $profile = $profile -replace 'hasCi: false', "hasCi: $($inventory.hasCi.ToString().ToLowerInvariant())"
        $profile = $profile -replace 'multiProject: false', "multiProject: $($inventory.multiProject.ToString().ToLowerInvariant())"

        [System.IO.File]::WriteAllText($profileDestination, $profile, [System.Text.UTF8Encoding]::new($false))
    }
}

function Add-AdapterEntrypoints {
    param([string]$ProjectRoot)

    $variables = @{
        'PROJECT_NAME' = (Split-Path -Leaf $ProjectRoot)
        'AI_SPEC_PATH' = '.ai-spec'
    }

    foreach ($tool in ($Tools | Select-Object -Unique)) {
        switch ($tool) {
            'claude-code' {
                Add-RenderedFile -Source (Join-Path $sourceRoot 'adapters\claude-code\CLAUDE.md.template') -Destination (Join-Path $ProjectRoot 'CLAUDE.md') -Variables $variables
                Add-FileFromSource -Source (Join-Path $sourceRoot 'adapters\claude-code\settings.json.template') -Destination (Join-Path $ProjectRoot '.claude\settings.json')
                foreach ($skill in @('product-architect', 'dev-implementation')) {
                    $sourceSkill = Join-Path $sourceRoot "skills\$skill"
                    Get-ChildItem -LiteralPath $sourceSkill -Recurse -File | ForEach-Object {
                        $skillRelative = $_.FullName.Substring($sourceSkill.Length + 1)
                        Add-FileFromSource -Source $_.FullName -Destination (Join-Path $ProjectRoot ".claude\skills\$skill\$skillRelative")
                    }
                }
            }
            'codex' {
                Add-RenderedFile -Source (Join-Path $sourceRoot 'adapters\codex\AGENTS.md.template') -Destination (Join-Path $ProjectRoot 'AGENTS.md') -Variables $variables
                foreach ($skill in @('product-architect', 'dev-implementation')) {
                    $sourceSkill = Join-Path $sourceRoot "skills\$skill"
                    Get-ChildItem -LiteralPath $sourceSkill -Recurse -File | ForEach-Object {
                        $skillRelative = $_.FullName.Substring($sourceSkill.Length + 1)
                        Add-FileFromSource -Source $_.FullName -Destination (Join-Path $ProjectRoot ".agents\skills\$skill\$skillRelative")
                    }
                }
            }
            'cursor' {
                Add-RenderedFile -Source (Join-Path $sourceRoot 'adapters\cursor\ai-spec.mdc.template') -Destination (Join-Path $ProjectRoot '.cursor\rules\ai-spec.mdc') -Variables $variables
            }
            'github-copilot' {
                Add-RenderedFile -Source (Join-Path $sourceRoot 'adapters\github-copilot\copilot-instructions.md.template') -Destination (Join-Path $ProjectRoot '.github\copilot-instructions.md') -Variables $variables
            }
            'generic' { }
        }
    }
}

function Copy-RuntimeSpec {
    param([string]$SpecRoot)

    $runtimeFiles = @(
        'AI-START.md',
        'README.md',
        'ai-spec.example.yaml'
    )

    foreach ($relativePath in $runtimeFiles) {
        Add-FileFromSource -Source (Join-Path $sourceRoot $relativePath) -Destination (Join-Path $SpecRoot $relativePath)
    }

    $runtimeDirectories = @(
        'adapters', 'business', 'contracts', 'core', 'core-lite', 'governance',
        'scripts', 'skills', 'stacks', 'tests', 'workflows'
    )

    foreach ($directory in $runtimeDirectories) {
        $sourceDirectory = Join-Path $sourceRoot $directory
        Get-ChildItem -LiteralPath $sourceDirectory -Recurse -File | ForEach-Object {
            $relativePath = $_.FullName.Substring($sourceRoot.Length + 1)
            Add-FileFromSource -Source $_.FullName -Destination (Join-Path $SpecRoot $relativePath)
        }
    }

    $guide = Join-Path $sourceRoot 'docs\使用指南.md'
    if (Test-Path -LiteralPath $guide) {
        Add-FileFromSource -Source $guide -Destination (Join-Path $SpecRoot 'docs\使用指南.md')
    }
}

function Test-ProjectSignal {
    param(
        [string]$ProjectRoot,
        [string[]]$PathSignals,
        [string[]]$TextSignals
    )

    if (Test-PathAny -RootDir $ProjectRoot -RelativePaths $PathSignals) { return $true }

    $candidateFiles = @('package.json', 'requirements.txt', 'pyproject.toml', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'go.mod')
    $text = ''
    foreach ($candidateFile in $candidateFiles) {
        $text += "`n" + (Read-FileIfExists -Path (Join-Path $ProjectRoot $candidateFile))
    }
    foreach ($signal in $TextSignals) {
        if ($text -match $signal) { return $true }
    }
    return $false
}

function Get-ProjectInventory {
    param(
        [string]$ProjectRoot,
        [bool]$IsMultiProject = $false
    )

    $ignoredDirs = @('.git', '.ai-spec', '.agents', '.claude', '.cursor', 'node_modules', 'vendor', 'dist', 'build', 'target', '.next', '.nuxt', 'coverage')
    $files = @(Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $relative = $_.FullName.Substring($ProjectRoot.Length).TrimStart('\', '/')
        $parts = @($relative -split '[\\/]')
        $skip = $false
        foreach ($part in $parts) {
            if ($part -in $ignoredDirs) { $skip = $true; break }
        }
        -not $skip
    })

    $buildFiles = @('package.json', 'pom.xml', 'go.mod', 'Cargo.toml', 'requirements.txt', 'pyproject.toml', 'Makefile', 'build.gradle', 'build.gradle.kts', 'composer.json', 'mix.exs', 'CMakeLists.txt', 'BUILD', 'WORKSPACE')
    $buildFileCount = 0
    foreach ($buildFile in $buildFiles) {
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot $buildFile) -PathType Leaf) { $buildFileCount++ }
    }

    $hasDatabase = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('prisma', 'migrations', 'db', 'database') -TextSignals @('prisma', 'typeorm', 'sequelize', 'sqlalchemy', 'hibernate', 'jdbc', 'postgres', 'mysql', 'sqlite', 'mongodb')
    $hasApi = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('api', 'routes', 'controllers', 'controller', 'server') -TextSignals @('api', 'route', 'controller', 'express', 'fastify', 'openapi', 'swagger')
    $hasAuth = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('auth', 'oauth', 'middleware', 'permission', 'permissions') -TextSignals @('auth', 'oauth', 'jwt', 'session', 'permission', 'tenant', 'rbac')
    $hasCi = Test-PathAny -RootDir $ProjectRoot -RelativePaths @('.github\workflows', '.gitlab-ci.yml', 'Jenkinsfile', 'azure-pipelines.yml', '.circleci', 'bitbucket-pipelines.yml')

    $fileCount = $files.Count
    $projectSize = 'enterprise'
    if ($fileCount -lt 30 -and $buildFileCount -le 1 -and -not $hasDatabase -and -not $hasApi -and -not $hasAuth -and -not $hasCi) {
        $projectSize = 'tiny'
    }
    elseif ($fileCount -lt 150) {
        $projectSize = 'small'
    }
    elseif ($fileCount -lt 800) {
        $projectSize = 'medium'
    }
    elseif ($fileCount -lt 3000) {
        $projectSize = 'large'
    }

    return @{
        fileCount = $fileCount
        buildFileCount = $buildFileCount
        hasDatabase = [bool]$hasDatabase
        hasApi = [bool]$hasApi
        hasAuth = [bool]$hasAuth
        hasCi = [bool]$hasCi
        multiProject = [bool]$IsMultiProject
        projectSize = $projectSize
    }
}

function Get-SizeStrategy {
    param([string]$ProjectSize)

    switch ($ProjectSize) {
        'tiny' { return 'ultra-lite' }
        'small' { return 'lite' }
        'medium' { return 'focused' }
        'large' { return 'mapped' }
        'enterprise' { return 'governed' }
        default { return 'auto' }
    }
}

function Get-ProjectSignalMatrix {
    param([string]$ProjectRoot)

    return @{
        organization = (Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('auth', 'user', 'users', 'tenant', 'role', 'roles', 'account', 'accounts') -TextSignals @('auth', 'user', 'tenant', 'role', 'rbac', 'oauth', 'session', 'jwt'))
        kpi = (Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('reports', 'report', 'analytics', 'dashboard', 'metrics', 'kpi') -TextSignals @('kpi', 'metric', 'analytics', 'dashboard', 'report', '统计', '报表'))
        stateMachine = (Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('workflow', 'workflows', 'state', 'states', 'approval', 'task', 'order') -TextSignals @('status', 'state', 'workflow', 'approval', 'pending', 'completed', 'canceled'))
        permissionMenu = (Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('admin', 'menu', 'menus', 'permission', 'permissions', 'role', 'roles') -TextSignals @('permission', 'menu', 'admin', 'role', 'rbac', '权限', '菜单'))
        externalIntegration = (Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('webhook', 'webhooks', 'callback', 'callbacks', 'integrations', 'integration', 'third-party') -TextSignals @('webhook', 'callback', 'integration', 'third-party', 'oauth', 'api key', 'external'))
    }
}

function New-BusinessRulesSkeleton {
    param(
        [string]$ProjectRoot,
        [string]$ProjectType
    )

    $signals = Get-ProjectSignalMatrix -ProjectRoot $ProjectRoot
    $optionalSections = @(
        @{ id = 'organization-identity'; include = [bool]$signals.organization; reason = 'no organization/auth/user/tenant signal' },
        @{ id = 'kpi-metrics'; include = [bool]$signals.kpi; reason = 'no KPI/report/analytics signal' },
        @{ id = 'state-machines'; include = [bool]$signals.stateMachine; reason = 'no state/workflow/status signal' },
        @{ id = 'menu-permissions'; include = [bool]$signals.permissionMenu; reason = 'no admin/menu/permission signal' },
        @{ id = 'external-integrations'; include = [bool]$signals.externalIntegration; reason = 'no webhook/callback/integration signal' }
    )

    $omitted = @($optionalSections | Where-Object { -not $_.include })
    $omittedLines = if ($omitted.Count -gt 0) {
        ($omitted | ForEach-Object { "- $($_.id): $($_.reason)" }) -join "`n"
    }
    else {
        "- none"
    }

    $content = @"
# Business Rules

> Trimmed skeleton generated by SpecForge onboarding.
> Record business semantics only. Do not record stack, commands, or transient chat context here.
> Add source/reliability markers when filling real rules.

metadata:
  projectType: $ProjectType
  generation: trimmed-skeleton
  omittedSections:
$omittedLines

---

<!-- section: business-positioning -->
## Business positioning

- Core users: TBD
- Core value: TBD
- Business model, if any: TBD

<!-- section: business-domains -->
## Business domains

| Domain | Description | Capabilities | Modules |
|---|---|---|---|
| TBD |  |  |  |

"@

    foreach ($section in $optionalSections) {
        if (-not $section.include) { continue }
        switch ($section.id) {
            'organization-identity' {
                $content += @"

<!-- section: organization-identity -->
## Organization identity

- Identity source: TBD
- User/tenant/role mapping: TBD
- Data-scope rule: TBD

"@
            }
            'kpi-metrics' {
                $content += @"

<!-- section: kpi-metrics -->
## KPI and metrics

| Metric | Time range | Data source | Exclusion rule |
|---|---|---|---|
| TBD |  |  |  |

"@
            }
            'state-machines' {
                $content += @"

<!-- section: state-machines -->
## State machines

- Entity: TBD
- State transitions: TBD
- Triggers and side effects: TBD

"@
            }
            'menu-permissions' {
                $content += @"

<!-- section: menu-permissions -->
## Menu and permissions

| Menu | Action | Permission code | Role |
|---|---|---|---|
| TBD |  |  |  |

"@
            }
            'external-integrations' {
                $content += @"

<!-- section: external-integrations -->
## External integrations

- External system: TBD
- Data flow: TBD
- Auth, idempotency, retry, audit: TBD

"@
            }
        }
    }

    $content += @"

<!-- section: data-write-rules -->
## Data write rules

- Writes must be idempotent.
- Sensitive changes must be traceable.
- Do not hard-code user, employee, department, role, company, or tenant IDs.
- Do not delete production data to "fix" a business problem.

<!-- section: business-invariants -->
## Business invariants

- TBD

<!-- section: uncategorized-business-rules -->
## Uncategorized business rules

> Append new rules to the matching section. If a task triggers an omitted section, restore that section first.
"@

    return $content
}

function Write-BusinessRulesSkeleton {
    param(
        [string]$ProjectRoot,
        [string]$SpecRoot,
        [string]$ProjectType
    )

    $rulesPath = Join-Path $SpecRoot 'business\business-rules.md'
    if (-not (Test-Path -LiteralPath $rulesPath -PathType Leaf)) { return }

    $existing = Get-Content -Raw -Encoding UTF8 -LiteralPath $rulesPath
    if ($existing.Contains('[📌 用户确认]')) {
        $script:conflicts.Add($rulesPath)
        return
    }

    $script:actions.Add("RENDER $rulesPath (trimmed business-rules skeleton)")
    if ($Apply) {
        $content = New-BusinessRulesSkeleton -ProjectRoot $ProjectRoot -ProjectType $ProjectType
        [System.IO.File]::WriteAllText($rulesPath, $content, [System.Text.UTF8Encoding]::new($false))
    }
}

function Write-QuickRefSkeleton {
    param(
        [string]$ProjectRoot,
        [string]$SpecRoot,
        [string]$ProjectType,
        [string]$ProjectSize,
        [string]$SizeStrategy
    )

    $quickRefPath = Join-Path $SpecRoot 'business\quick-ref.md'
    if (-not (Test-Path -LiteralPath $quickRefPath -PathType Leaf)) { return }

    $inventory = Get-ProjectInventory -ProjectRoot $ProjectRoot -IsMultiProject $false
    $script:actions.Add("RENDER $quickRefPath (project-size context strategy)")
    if ($Apply) {
        $content = @"
# Quick Ref

> daily startup entry: true
> status: TEMPLATE_PLACEHOLDER
> dailyEntry: true
> dynamicContextGate: true
> projectSize: $ProjectSize
> sizeStrategy: $SizeStrategy
> generated becomes GENERATED only after AI summarizes real project facts.

---

## Project positioning

- projectType: $ProjectType
- projectSize: $ProjectSize
- sizeStrategy: $SizeStrategy
- fileCount: $($inventory.fileCount)
- buildFileCount: $($inventory.buildFileCount)
- hasApi: $($inventory.hasApi.ToString().ToLowerInvariant())
- hasDatabase: $($inventory.hasDatabase.ToString().ToLowerInvariant())
- hasAuth: $($inventory.hasAuth.ToString().ToLowerInvariant())
- hasCi: $($inventory.hasCi.ToString().ToLowerInvariant())

## Size-based loading strategy

| Level | Default load | Upgrade when |
|---|---|---|
| L0 | this file only | project location is unclear |
| L1 | this file + exact target file/snippet | behavior changes |
| L2 | this file + core-lite/delivery-lite.md + related source | tests/security are touched |
| L3 | business-rules/contracts/full core as triggered | API/DB/Auth/business rules change |
| L4 | AI-START.md + full onboarding/audit context | user asks onboarding/audit/refactor |

## Business facts

- TBD: AI must fill this after reading real project facts.
"@
        [System.IO.File]::WriteAllText($quickRefPath, $content, [System.Text.UTF8Encoding]::new($false))
    }
}

function Invoke-SpecSlimming {
    param(
        [string]$ProjectRoot,
        [string]$SpecRoot,
        [string]$ProjectType
    )

    Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'tests' -Reason 'template self-tests are not needed in installed projects'
    Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'scripts\install.ps1' -Reason 'one-time installer is not needed after onboarding'

    $adaptersRoot = Join-Path $SpecRoot 'adapters'
    if (Test-Path -LiteralPath $adaptersRoot -PathType Container) {
        Get-ChildItem -LiteralPath $adaptersRoot -Directory | ForEach-Object {
            if ($_.Name -notin $Tools) {
                Remove-SpecPath -SpecRoot $SpecRoot -RelativePath ("adapters\" + $_.Name) -Reason 'unused adapter'
            }
        }
    }

    $keepStacks = @(Get-StackFilesForType -ProjectType $ProjectType)
    $stacksRoot = Join-Path $SpecRoot 'stacks'
    if (Test-Path -LiteralPath $stacksRoot -PathType Container) {
        Get-ChildItem -LiteralPath $stacksRoot -File | ForEach-Object {
            if ($_.Name -notin $keepStacks) {
                Remove-SpecPath -SpecRoot $SpecRoot -RelativePath ("stacks\" + $_.Name) -Reason "irrelevant for $ProjectType project"
            }
        }
    }

    $hasDatabase = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('prisma', 'migrations', 'db', 'database') -TextSignals @('prisma', 'typeorm', 'sequelize', 'sqlalchemy', 'hibernate', 'jdbc', 'postgres', 'mysql', 'sqlite', 'mongodb')
    if (-not $hasDatabase) {
        Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'core\data-migration-standard.md' -Reason 'no database or migration signal detected'
    }

    $hasCi = Test-PathAny -RootDir $ProjectRoot -RelativePaths @('.github\workflows', '.gitlab-ci.yml', 'Jenkinsfile', 'azure-pipelines.yml', '.circleci', 'bitbucket-pipelines.yml')
    if (-not $hasCi) {
        Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'core\cicd-standard.md' -Reason 'no CI signal detected'
    }

    $hasPermission = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('auth', 'oauth', 'middleware') -TextSignals @('auth', 'oauth', 'jwt', 'session', 'permission', 'tenant', 'rbac')
    if (-not $hasPermission) {
        Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'core\permission-standard.md' -Reason 'no auth or permission signal detected'
    }

    $hasObservability = Test-ProjectSignal -ProjectRoot $ProjectRoot -PathSignals @('monitoring', 'observability', 'prometheus', 'grafana') -TextSignals @('sentry', 'prometheus', 'opentelemetry', 'datadog', 'newrelic', 'grafana')
    if (-not $hasObservability) {
        Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'core\observability.md' -Reason 'no observability signal detected'
    }

    Remove-SpecPath -SpecRoot $SpecRoot -RelativePath 'core\gotchas.md' -Reason 'no project-specific gotchas have been modeled yet'
}

function Install-SpecInstance {
    param(
        [string]$ProjectRoot,
        [string]$Stage,
        [string]$ProjectType,
        [string]$MultiProjectId
    )

    $specRoot = Join-Path $ProjectRoot '.ai-spec'
    $inventory = Get-ProjectInventory -ProjectRoot $ProjectRoot -IsMultiProject ([bool]$MultiProjectId)
    $sizeStrategy = Get-SizeStrategy -ProjectSize $inventory.projectSize
    Copy-RuntimeSpec -SpecRoot $specRoot
    Write-AiSpecProfile -SpecRoot $specRoot -ProjectRoot $ProjectRoot -Stage $Stage -ProjectType $ProjectType -MultiProjectId $MultiProjectId
    Add-AdapterEntrypoints -ProjectRoot $ProjectRoot
    if ($Onboard) {
        Write-QuickRefSkeleton -ProjectRoot $ProjectRoot -SpecRoot $specRoot -ProjectType $ProjectType -ProjectSize $inventory.projectSize -SizeStrategy $sizeStrategy
        Write-BusinessRulesSkeleton -ProjectRoot $ProjectRoot -SpecRoot $specRoot -ProjectType $ProjectType
        Invoke-SpecSlimming -ProjectRoot $ProjectRoot -SpecRoot $specRoot -ProjectType $ProjectType
    }

    $script:installReports.Add(@{
        path = $ProjectRoot
        stage = $Stage
        type = $ProjectType
    })
}

function Write-SpecForgeIndex {
    param(
        [string]$RootDir,
        [string]$MultiProjectId,
        [array]$Projects
    )

    $indexPath = Join-Path $RootDir '.specforge.json'
    if (Test-Path -LiteralPath $indexPath) {
        $script:conflicts.Add($indexPath)
        return
    }

    $script:actions.Add("CREATE $indexPath")
    if ($Apply) {
        $installedAt = (Get-Date).ToUniversalTime().ToString('o')
        $indexProjects = @()
        foreach ($project in $Projects) {
            $indexProjects += [ordered]@{
                path = $project.name
                type = $project.type
                buildFiles = @($project.buildFiles)
                installedAt = $installedAt
            }
        }
        $index = [ordered]@{
            templateSource = 'SpecForge'
            templateVersion = $templateVersion
            multiProjectId = $MultiProjectId
            projects = $indexProjects
        }
        $json = $index | ConvertTo-Json -Depth 6
        [System.IO.File]::WriteAllText($indexPath, $json, [System.Text.UTF8Encoding]::new($false))
    }
}

function Get-SyncRelativePaths {
    $relativePaths = [System.Collections.Generic.List[string]]::new()
    foreach ($file in @('AI-START.md', 'README.md', 'scripts\validate.ps1')) {
        $relativePaths.Add($file)
    }

    foreach ($directory in @('core', 'core-lite', 'contracts', 'governance', 'skills', 'workflows')) {
        $sourceDirectory = Join-Path $sourceRoot $directory
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            Get-ChildItem -LiteralPath $sourceDirectory -Recurse -File | ForEach-Object {
                $relativePaths.Add($_.FullName.Substring($sourceRoot.Length + 1))
            }
        }
    }

    return @($relativePaths | Select-Object -Unique)
}

function Copy-SyncFile {
    param(
        [string]$SpecRoot,
        [string]$RelativePath
    )

    $source = Join-Path $sourceRoot $RelativePath
    $destination = Join-Path $SpecRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        return
    }

    $script:actions.Add("SYNC $destination")
    if ($Apply) {
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

function Sync-SpecInstance {
    param([string]$SpecRoot)

    if (-not (Test-Path -LiteralPath $SpecRoot -PathType Container)) {
        $script:conflicts.Add("Missing .ai-spec instance: $SpecRoot")
        return
    }

    foreach ($relativePath in Get-SyncRelativePaths) {
        Copy-SyncFile -SpecRoot $SpecRoot -RelativePath $relativePath
    }
}

function Update-SpecForgeIndexVersion {
    param([string]$IndexPath)

    $script:actions.Add("UPDATE $IndexPath templateVersion=$templateVersion")
    if ($Apply) {
        $index = Get-Content -Raw -Encoding UTF8 -LiteralPath $IndexPath | ConvertFrom-Json
        if (-not ($index.PSObject.Properties.Name -contains 'templateSource')) {
            $index | Add-Member -NotePropertyName 'templateSource' -NotePropertyValue 'SpecForge'
        }
        else {
            $index.templateSource = 'SpecForge'
        }
        if (-not ($index.PSObject.Properties.Name -contains 'templateVersion')) {
            $index | Add-Member -NotePropertyName 'templateVersion' -NotePropertyValue $templateVersion
        }
        else {
            $index.templateVersion = $templateVersion
        }
        $json = $index | ConvertTo-Json -Depth 8
        [System.IO.File]::WriteAllText($IndexPath, $json, [System.Text.UTF8Encoding]::new($false))
    }
}

function Invoke-SpecSync {
    param([string]$RootDir)

    $indexPath = Join-Path $RootDir '.specforge.json'
    if (Test-Path -LiteralPath $indexPath -PathType Leaf) {
        Update-SpecForgeIndexVersion -IndexPath $indexPath
        $index = Get-Content -Raw -Encoding UTF8 -LiteralPath $indexPath | ConvertFrom-Json
        foreach ($project in @($index.projects)) {
            $projectRoot = Join-Path $RootDir ([string]$project.path)
            Sync-SpecInstance -SpecRoot (Join-Path $projectRoot '.ai-spec')
        }
        return
    }

    $singleSpecRoot = Join-Path $RootDir '.ai-spec'
    if (Test-Path -LiteralPath $singleSpecRoot -PathType Container) {
        Sync-SpecInstance -SpecRoot $singleSpecRoot
        return
    }

    throw 'Sync requires either a parent .specforge.json or a local .ai-spec directory.'
}

function Invoke-GitOnboarding {
    param([string]$RepositoryRoot)

    $hasGit = Test-Path -LiteralPath (Join-Path $RepositoryRoot '.git')
    if (-not $hasGit) {
        $script:actions.Add("GIT init/add/initial-commit $RepositoryRoot (controlled exception for no-Git onboarding)")
        if ($Apply) {
            & git -C $RepositoryRoot init | Out-Null
            & git -C $RepositoryRoot add -A | Out-Null
            & git -C $RepositoryRoot commit -m 'chore: initial commit' | Out-Null
        }
    }

    $script:actions.Add("GIT create branch $BranchName")
    if ($Apply) {
        $branchExists = $false
        & git -C $RepositoryRoot show-ref --verify --quiet "refs/heads/$BranchName"
        if ($LASTEXITCODE -eq 0) { $branchExists = $true }
        if ($branchExists) {
            throw "Git branch already exists: $BranchName"
        }
        & git -C $RepositoryRoot switch -c $BranchName | Out-Null
    }
}

if ($Sync) {
    Invoke-SpecSync -RootDir $targetFullPath
    Write-Host "AI Spec sync plan" -ForegroundColor Cyan
    Write-Host "Target: $targetFullPath"
    Write-Host "TemplateVersion: $templateVersion"
    Write-Host "Apply: $([bool]$Apply)"
    foreach ($action in $actions) { Write-Host "- $action" }
    if ($conflicts.Count -gt 0) {
        Write-Host "Conflicts / warnings:" -ForegroundColor Yellow
        foreach ($conflict in $conflicts) { Write-Host "- $conflict" -ForegroundColor Yellow }
    }
    exit 0
}

if ($Onboard -and $ManageGit) {
    Invoke-GitOnboarding -RepositoryRoot $targetFullPath
}

$subProjects = if ($Onboard) { @(Detect-SubProjects -RootDir $targetFullPath) } else { @() }
$installTargets = [System.Collections.Generic.List[hashtable]]::new()
$multiProjectId = $null

if ($Onboard -and $subProjects.Count -ge 2) {
    $multiProjectId = [guid]::NewGuid().ToString()
    foreach ($project in $subProjects) {
        $projectType = Detect-ProjectType -ProjectRoot $project.path
        $project.type = $projectType
        $stage = if ($Mode -eq 'auto') { Detect-Mode -ProjectRoot $project.path } else { $Mode }
        $installTargets.Add(@{
            path = $project.path
            stage = $stage
            type = $projectType
            multiProjectId = $multiProjectId
        })
    }
    Write-SpecForgeIndex -RootDir $targetFullPath -MultiProjectId $multiProjectId -Projects $subProjects
}
elseif ($Onboard -and $subProjects.Count -eq 1 -and $Mode -eq 'auto') {
    $project = $subProjects[0]
    $projectType = Detect-ProjectType -ProjectRoot $project.path
    $installTargets.Add(@{
        path = $project.path
        stage = Detect-Mode -ProjectRoot $project.path
        type = $projectType
        multiProjectId = $null
    })
}
else {
    $projectType = if ($Onboard) { Detect-ProjectType -ProjectRoot $targetFullPath } else { 'generic' }
    $stage = if ($Mode -eq 'auto') { Detect-Mode -ProjectRoot $targetFullPath } else { $Mode }
    $installTargets.Add(@{
        path = $targetFullPath
        stage = $stage
        type = $projectType
        multiProjectId = $null
    })
}

foreach ($target in $installTargets) {
    Install-SpecInstance -ProjectRoot $target.path -Stage $target.stage -ProjectType $target.type -MultiProjectId $target.multiProjectId
}

Write-Host "AI Spec installation plan" -ForegroundColor Cyan
Write-Host "Target: $targetFullPath"
Write-Host "Mode: $Mode"
Write-Host "Onboard: $([bool]$Onboard)"
Write-Host "ManageGit: $([bool]$ManageGit)"
Write-Host "Tools: $($Tools -join ', ')"
Write-Host "Apply: $([bool]$Apply)"
Write-Host "Instances: $($installReports.Count)"
foreach ($report in $installReports) {
    Write-Host "- $($report.path) [$($report.stage) / $($report.type)]"
}
Write-Host "Actions: $($actions.Count)"
foreach ($action in $actions) { Write-Host "- $action" }

if ($conflicts.Count -gt 0) {
    Write-Host "Existing files kept unchanged: $($conflicts.Count)" -ForegroundColor Yellow
    foreach ($conflict in $conflicts) { Write-Host "- KEEP $conflict" }
    Write-Host 'Review and merge these files semantically; the installer never overwrites them.' -ForegroundColor Yellow
}

if (-not $Apply) {
    Write-Host 'Dry-run only. Re-run with -Apply to create missing files.' -ForegroundColor Yellow
}
elseif ($Onboard) {
    Write-Host 'Onboarding completed without overwriting existing user-owned files.' -ForegroundColor Green
}
else {
    Write-Host 'Installation completed without overwriting existing files.' -ForegroundColor Green
}
