[CmdletBinding()]
param(
    [ValidateSet("major", "feature", "patch")]
    [string]$BumpType = "",

    [string]$FinalizeExistingTag = "",

    [string]$WorkspaceRoot = "",
    [string]$SourceRoot = "",
    [string]$LiveAddinRoot = "",
    [string]$RepoSlug = "macifoxispurple/FusionBetterParameters",
    [string]$NotesFile = "",

    [switch]$FusionTested,
    [switch]$SkipPush,
    [switch]$SkipRelease
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = Join-Path $WorkspaceRoot "BetterParameters"
}
if ([string]::IsNullOrWhiteSpace($LiveAddinRoot)) {
    $LiveAddinRoot = [string]$env:BP_LIVE_ADDIN_ROOT
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Tool([string]$ToolName) {
    if (-not (Get-Command $ToolName -ErrorAction SilentlyContinue)) {
        throw "Required tool not found on PATH: $ToolName"
    }
}

function Invoke-Checked([scriptblock]$Script, [string]$ErrorMessage) {
    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "$ErrorMessage (exit code $LASTEXITCODE)"
    }
}

function Get-BumpedVersion([string]$CurrentVersion, [string]$Mode) {
    $parts = $CurrentVersion -split "\."
    if ($parts.Count -ne 3) {
        throw "Unexpected version format: $CurrentVersion"
    }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    $patch = [int]$parts[2]
    switch ($Mode) {
        "major"   { return "{0}.0.0" -f ($major + 1) }
        "feature" { return "{0}.{1}.0" -f $major, ($minor + 1) }
        "patch"   { return "{0}.{1}.{2}" -f $major, $minor, ($patch + 1) }
        default   { throw "Unsupported bump mode: $Mode" }
    }
}

function Test-TagExistsRemote([string]$RepoPath, [string]$Tag) {
    & git -C $RepoPath ls-remote --tags origin "refs/tags/$Tag" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to check remote tags for $Tag."
    }
    $result = & git -C $RepoPath ls-remote --tags origin "refs/tags/$Tag"
    return -not [string]::IsNullOrWhiteSpace($result)
}

function Set-Utf8NoBomFile([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Get-PreviousVersionTag([string]$RepoPath, [string]$CurrentTag) {
    $tags = @(& git -C $RepoPath tag --list "v*" --sort=v:refname)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list tags for release note generation."
    }
    if (-not $tags -or $tags.Count -eq 0) {
        return ""
    }
    $index = [Array]::IndexOf($tags, $CurrentTag)
    if ($index -gt 0) {
        return [string]$tags[$index - 1]
    }
    return ""
}

function Get-AutoReleaseHighlights([string]$RepoPath, [string]$CurrentTag) {
    $previousTag = Get-PreviousVersionTag -RepoPath $RepoPath -CurrentTag $CurrentTag
    if ([string]::IsNullOrWhiteSpace($previousTag)) {
        return @("- Initial release.")
    }

    $subjects = @(& git -C $RepoPath log --pretty=format:%s "$previousTag..HEAD")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to collect commit subjects for release notes."
    }
    $meaningfulSubjects = @(
        $subjects |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            $_ -notmatch '^Release v\d+\.\d+\.\d+$'
        } |
        Select-Object -Unique
    )
    if ($meaningfulSubjects.Count -gt 0) {
        return @($meaningfulSubjects | ForEach-Object { "- $_" })
    }

    $highlights = @()
    $shortStat = (& git -C $RepoPath diff --shortstat "$previousTag..HEAD").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to collect diff stats for release notes."
    }
    if (-not [string]::IsNullOrWhiteSpace($shortStat)) {
        $highlights += "- $shortStat"
    }

    $changedFiles = @(& git -C $RepoPath diff --name-only "$previousTag..HEAD")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to collect changed files for release notes."
    }
    $changedFiles = @($changedFiles | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($changedFiles.Count -gt 0) {
        $top = @($changedFiles | Select-Object -First 6)
        $line = "- Updated files: " + ($top -join ", ")
        if ($changedFiles.Count -gt $top.Count) {
            $remaining = $changedFiles.Count - $top.Count
            $line += ", +$remaining more"
        }
        $highlights += $line
    }

    if ($highlights.Count -eq 0) {
        $highlights += "- Internal maintenance changes."
    }
    return $highlights
}

function Test-LowSignalHighlights([string[]]$Highlights) {
    if (-not $Highlights -or $Highlights.Count -eq 0) {
        return $true
    }
    $genericPattern = '^- (Initial release\.|Internal maintenance changes\.|\d+ files changed, .*|Updated files: .*)$'
    $meaningful = @(
        $Highlights |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            $_ -notmatch $genericPattern
        }
    )
    return ($meaningful.Count -eq 0)
}

function Test-GitHubReleaseExists([string]$Tag, [string]$Repo) {
    $stdoutPath = Join-Path $env:TEMP ("bp_release_view_{0}_out.log" -f ([guid]::NewGuid().ToString("N")))
    $stderrPath = Join-Path $env:TEMP ("bp_release_view_{0}_err.log" -f ([guid]::NewGuid().ToString("N")))
    try {
        $proc = Start-Process -FilePath "gh" `
            -ArgumentList @("release", "view", $Tag, "--repo", $Repo) `
            -NoNewWindow -PassThru -Wait `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath
        return ($proc.ExitCode -eq 0)
    }
    finally {
        if (Test-Path $stdoutPath) { Remove-Item -Force $stdoutPath }
        if (Test-Path $stderrPath) { Remove-Item -Force $stderrPath }
    }
}

function New-ReleaseNotesTemp(
    [string]$RepoPath,
    [string]$Tag,
    [string]$Version,
    [string]$ProvidedNotesFile,
    [string]$WorkspacePath,
    [string]$ScriptRoot,
    [string]$RerunHint
) {
    $notesTemp = Join-Path $env:TEMP "bp_release_notes_$Version.md"
    $effectiveNotesFile = $ProvidedNotesFile
    $defaultNotesFile = Join-Path $WorkspacePath "scripts\release_notes_pending.md"

    if ([string]::IsNullOrWhiteSpace($effectiveNotesFile) -and (Test-Path $defaultNotesFile)) {
        $effectiveNotesFile = $defaultNotesFile
    }

    if ([string]::IsNullOrWhiteSpace($effectiveNotesFile)) {
        $autoHighlights = Get-AutoReleaseHighlights -RepoPath $RepoPath -CurrentTag $Tag
        if (Test-LowSignalHighlights -Highlights $autoHighlights) {
            $msg = @"
Auto-generated release notes are low-signal for $Tag.
Create curated notes and rerun:
$RerunHint
"@
            throw $msg.Trim()
        }

        $highlightsText = ($autoHighlights -join "`r`n")
        $templatePath = Join-Path $ScriptRoot "release_notes_template.md"
        if (Test-Path $templatePath) {
            $templateText = Get-Content -Raw $templatePath
        }
        else {
            $templateText = "BetterParameters v{{VERSION}}`r`n`r`nHighlights:`r`n{{AUTO_HIGHLIGHTS}}"
        }
        $notesText = $templateText.Replace("{{VERSION}}", $Version)
        if ($notesText.Contains("{{AUTO_HIGHLIGHTS}}")) {
            $notesText = $notesText.Replace("{{AUTO_HIGHLIGHTS}}", $highlightsText)
        }
        elseif (
            $notesText -match "<feature 1>" -or
            $notesText -match "<feature 2>" -or
            $notesText -match "<fixes/perf notes>" -or
            $notesText -match "<item 1>" -or
            $notesText -match "<item 2>"
        ) {
            $notesText = "BetterParameters v$Version`r`n`r`nHighlights:`r`n$highlightsText"
        }
        elseif ($notesText -notmatch "(?im)^\s*Highlights:\s*$") {
            $notesText = $notesText.TrimEnd() + "`r`n`r`nHighlights:`r`n$highlightsText"
        }
        Set-Utf8NoBomFile -Path $notesTemp -Text $notesText
        return $notesTemp
    }

    if (-not (Test-Path $effectiveNotesFile)) {
        throw "Notes file not found: $effectiveNotesFile"
    }
    $notesText = Get-Content -Raw $effectiveNotesFile
    Set-Utf8NoBomFile -Path $notesTemp -Text $notesText
    return $notesTemp
}

function Assert-ReleaseZip([string]$ZipPath, [string]$ExpectedVersion, [string[]]$AllowedTopLevelEntries = @()) {
    if (-not (Test-Path $ZipPath)) {
        throw "Zip was not created: $ZipPath"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $allowedSet = @{}
        foreach ($entryName in @($AllowedTopLevelEntries)) {
            if (-not [string]::IsNullOrWhiteSpace($entryName)) {
                $allowedSet[$entryName] = $true
            }
        }
        $badEntry = $zip.Entries | Where-Object {
            $normalized = ($_.FullName -replace '\\', '/').TrimEnd('/')
            if ([string]::IsNullOrWhiteSpace($normalized)) {
                return $false
            }
            if ($normalized.StartsWith("BetterParameters/")) {
                return $false
            }
            return (-not $allowedSet.ContainsKey($normalized))
        } | Select-Object -First 1
        if ($badEntry) {
            throw "Zip contains unexpected entry outside BetterParameters/ root: $($badEntry.FullName)"
        }

        $manifestEntry = $zip.Entries | Where-Object {
            ($_.FullName -replace '\\', '/') -eq "BetterParameters/BetterParameters.manifest"
        } | Select-Object -First 1
        if (-not $manifestEntry) {
            throw "Zip missing BetterParameters/BetterParameters.manifest"
        }

        $stream = $manifestEntry.Open()
        $reader = New-Object System.IO.StreamReader($stream)
        $zipManifest = $reader.ReadToEnd()
        $reader.Dispose()
        $stream.Dispose()

        if (-not [regex]::IsMatch($zipManifest, '"version"\s*:\s*"' + [regex]::Escape($ExpectedVersion) + '"')) {
            throw "Zip manifest version mismatch. Expected $ExpectedVersion."
        }
    }
    finally {
        $zip.Dispose()
    }
}

function Get-LockedFiles([string]$RootPath, [int]$MaxResults = 8) {
    if (-not (Test-Path $RootPath)) {
        return @()
    }
    $locked = @()
    foreach ($file in (Get-ChildItem -Path $RootPath -File -Recurse -ErrorAction SilentlyContinue)) {
        try {
            $stream = [System.IO.File]::Open($file.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
            $stream.Dispose()
        }
        catch {
            $locked += $file.FullName
            if ($locked.Count -ge $MaxResults) {
                break
            }
        }
    }
    return $locked
}

function Build-DeterministicPackage(
    [string]$SourceRootPath,
    [string]$StageRootPath,
    [string]$PackageRootPath,
    [string]$ZipRootPath,
    [string]$ZipPath,
    [string]$ExpectedVersion,
    [string]$ReleaseAssetsPath = ""
) {
    if (Test-Path $StageRootPath) {
        Get-ChildItem -Force $StageRootPath | Remove-Item -Recurse -Force
    }
    New-Item -ItemType Directory -Path $StageRootPath -Force | Out-Null
    New-Item -ItemType Directory -Path $ZipRootPath -Force | Out-Null

    if (Test-Path $PackageRootPath) {
        Remove-Item -Recurse -Force $PackageRootPath
    }
    if (Test-Path $ZipPath) {
        Remove-Item -Force $ZipPath
    }
    New-Item -ItemType Directory -Path $PackageRootPath | Out-Null

    & robocopy $SourceRootPath $PackageRootPath /E `
        /XD .git __pycache__ dev .release_stage _release_stage _releases_packages `
        /XF settings.json update_state.json *.zip .gitignore `
        /NFL /NDL /NJH /NJS /NC /NS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed while staging package (exit code $LASTEXITCODE)."
    }

    # Stage manifest is rewritten to target release version before zipping,
    # so package validation can run before source manifest bump/commit.
    $stagedManifestPath = Join-Path $PackageRootPath "BetterParameters.manifest"
    if (-not (Test-Path $stagedManifestPath)) {
        throw "Staged manifest missing: $stagedManifestPath"
    }
    $stagedManifestRaw = Get-Content -Raw $stagedManifestPath
    $stagedManifestNew = [regex]::Replace(
        $stagedManifestRaw,
        '"version"\s*:\s*"\d+\.\d+\.\d+"',
        """version"": ""$ExpectedVersion""",
        1
    )
    if ($stagedManifestNew -eq $stagedManifestRaw) {
        throw "Failed to set staged manifest version to $ExpectedVersion."
    }
    Set-Utf8NoBomFile -Path $stagedManifestPath -Text $stagedManifestNew

    $allowedTopLevelEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($ReleaseAssetsPath) -and (Test-Path $ReleaseAssetsPath)) {
        $releaseAssets = Get-ChildItem -Path $ReleaseAssetsPath -File -Force
        foreach ($asset in $releaseAssets) {
            $dest = Join-Path $StageRootPath $asset.Name
            Copy-Item -LiteralPath $asset.FullName -Destination $dest -Force
            $allowedTopLevelEntries += $asset.Name
        }
    }

    $zipCreated = $false
    $lastZipError = $null
    for ($attempt = 1; $attempt -le 6 -and -not $zipCreated; $attempt++) {
        $lockedFiles = Get-LockedFiles -RootPath $PackageRootPath -MaxResults 6
        if ($lockedFiles.Count -gt 0) {
            if ($attempt -lt 6) {
                Start-Sleep -Milliseconds (250 * $attempt)
                continue
            }
        }
        try {
            Compress-Archive -Path (Join-Path $StageRootPath "*") -DestinationPath $ZipPath -CompressionLevel Optimal -Force
            $zipCreated = $true
        }
        catch {
            $lastZipError = $_
            if ($attempt -lt 6) {
                Start-Sleep -Milliseconds (300 * $attempt)
            }
        }
    }

    if (-not $zipCreated) {
        try {
            if (Test-Path $ZipPath) {
                Remove-Item -Force $ZipPath
            }
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::CreateFromDirectory(
                $StageRootPath,
                $ZipPath,
                [System.IO.Compression.CompressionLevel]::Optimal,
                $false
            )
            $zipCreated = $true
        }
        catch {
            $lockedFiles = Get-LockedFiles -RootPath $PackageRootPath -MaxResults 6
            $lockedText = if ($lockedFiles.Count -gt 0) { $lockedFiles -join "; " } else { "none detected" }
            $baseMessage = if ($lastZipError) { $lastZipError.Exception.Message } else { "unknown zip error" }
            throw "Package zip creation failed after retries. Last error: $baseMessage. Locked files: $lockedText"
        }
    }

    Assert-ReleaseZip -ZipPath $ZipPath -ExpectedVersion $ExpectedVersion -AllowedTopLevelEntries $allowedTopLevelEntries
}

function New-ShipReport(
    [string]$WorkspacePath,
    [string]$Mode,
    [string]$Tag
) {
    $reportDir = Join-Path $WorkspacePath "scripts\_ship_reports"
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    $runId = Get-Date -Format "yyyyMMdd_HHmmss"
    return [ordered]@{
        runId = $runId
        mode = $Mode
        tag = $Tag
        startedAt = (Get-Date).ToString("o")
        endedAt = ""
        status = "running"
        releaseUrl = ""
        zipPath = ""
        steps = @()
        error = ""
        reportPath = (Join-Path $reportDir "ship_$runId.json")
    }
}

function Add-ShipReportStep(
    [hashtable]$Report,
    [string]$Step,
    [string]$Status,
    [string]$Detail = ""
) {
    $entry = [ordered]@{
        at = (Get-Date).ToString("o")
        step = $Step
        status = $Status
        detail = $Detail
    }
    $Report.steps += $entry
}

function Save-ShipReport([hashtable]$Report) {
    if (-not $Report -or -not $Report.reportPath) {
        return
    }
    $Report.endedAt = (Get-Date).ToString("o")
    $json = $Report | ConvertTo-Json -Depth 8
    Set-Utf8NoBomFile -Path $Report.reportPath -Text $json
}

$script:shipReport = $null
trap {
    if ($script:shipReport) {
        $script:shipReport.status = "failed"
        $script:shipReport.error = $_.Exception.Message
        Add-ShipReportStep -Report $script:shipReport -Step "fatal" -Status "failed" -Detail $_.Exception.Message
        Save-ShipReport -Report $script:shipReport
        Write-Host "Ship report: $($script:shipReport.reportPath)" -ForegroundColor Yellow
    }
    if ($tag -and $tag -match '^v\d+\.\d+\.\d+$') {
        Write-Host ("Recovery hint: powershell -ExecutionPolicy Bypass -File .\scripts\ship.ps1 -FinalizeExistingTag {0} -FusionTested -NotesFile .\scripts\release_notes_pending.md" -f $tag) -ForegroundColor Yellow
    }
    throw $_
}

Write-Step "Preflight checks"

if (-not $FusionTested) {
    throw "Missing -FusionTested. Run Fusion test cycle first, then re-run ship command with -FusionTested."
}

$isFinalizeMode = -not [string]::IsNullOrWhiteSpace($FinalizeExistingTag)
if ($isFinalizeMode -and -not [string]::IsNullOrWhiteSpace($BumpType)) {
    throw "Use either -BumpType or -FinalizeExistingTag, not both."
}
if (-not $isFinalizeMode -and [string]::IsNullOrWhiteSpace($BumpType)) {
    throw "Missing required mode. Use -BumpType <major|feature|patch> or -FinalizeExistingTag vX.Y.Z."
}

Assert-Tool "git"
Assert-Tool "gh"
Assert-Tool "python"

if (-not (Test-Path $WorkspaceRoot)) { throw "Workspace root missing: $WorkspaceRoot" }
if (-not (Test-Path $SourceRoot)) { throw "Source root missing: $SourceRoot" }
if (-not $isFinalizeMode -and [string]::IsNullOrWhiteSpace($LiveAddinRoot)) {
    throw "Live add-in root is required for non-finalize mode. Set -LiveAddinRoot or BP_LIVE_ADDIN_ROOT."
}
if (-not $isFinalizeMode -and -not (Test-Path $LiveAddinRoot)) { throw "Live add-in root missing: $LiveAddinRoot" }

$manifestPath = Join-Path $SourceRoot "BetterParameters.manifest"
$updateHelperPath = Join-Path $SourceRoot "update_helper.py"
if (-not (Test-Path $manifestPath)) { throw "Manifest missing: $manifestPath" }
if (-not (Test-Path $updateHelperPath)) { throw "update_helper.py missing: $updateHelperPath" }

Invoke-Checked { & gh auth status --hostname github.com } "GitHub CLI auth check failed"

$branch = (& git -C $WorkspaceRoot rev-parse --abbrev-ref HEAD).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) {
    throw "Could not determine git branch."
}

$manifestRaw = Get-Content -Raw $manifestPath
$versionMatch = [regex]::Match($manifestRaw, '"version"\s*:\s*"(?<ver>\d+\.\d+\.\d+)"')
if (-not $versionMatch.Success) {
    throw "Could not parse version from manifest."
}
$currentVersion = $versionMatch.Groups["ver"].Value
$newVersion = ""
$tag = ""

if ($isFinalizeMode) {
    $tag = $FinalizeExistingTag.Trim()
    if ($tag -notmatch '^v\d+\.\d+\.\d+$') {
        throw "Finalize tag must be in format vX.Y.Z (received: $FinalizeExistingTag)"
    }
    if (-not (Test-TagExistsRemote -RepoPath $WorkspaceRoot -Tag $tag)) {
        throw "Finalize target tag does not exist on remote: $tag"
    }
    $newVersion = $tag.Substring(1)
}
else {
    $newVersion = Get-BumpedVersion -CurrentVersion $currentVersion -Mode $BumpType
    $tag = "v$newVersion"
    if ((& git -C $WorkspaceRoot tag -l $tag)) {
        throw "Local tag already exists: $tag"
    }
    if (Test-TagExistsRemote -RepoPath $WorkspaceRoot -Tag $tag) {
        throw "Remote tag already exists: $tag"
    }
}

$zipName = "BetterParameters-$newVersion.zip"
$stageRoot = Join-Path $WorkspaceRoot "_release_stage"
$packageRoot = Join-Path $stageRoot "BetterParameters"
$zipRoot = Join-Path $WorkspaceRoot "_releases_packages"
$zipPath = Join-Path $zipRoot $zipName
$releaseAssetsPath = Join-Path $WorkspaceRoot "scripts\release_assets"
$allowedTopLevelReleaseAssets = @()
if (Test-Path $releaseAssetsPath) {
    $allowedTopLevelReleaseAssets = @((Get-ChildItem -Path $releaseAssetsPath -File -Force | ForEach-Object { $_.Name }))
}
$modeText = if ($isFinalizeMode) { "finalize" } else { "normal" }
$script:shipReport = New-ShipReport -WorkspacePath $WorkspaceRoot -Mode $modeText -Tag $tag
$script:shipReport.zipPath = $zipPath

Write-Host "Current version: $currentVersion"
if ($isFinalizeMode) {
    Write-Host "Finalize mode:   existing tag"
}
else {
    Write-Host "Next version:    $newVersion"
}
Write-Host "Branch:          $branch"
Write-Host "Tag:             $tag"
Add-ShipReportStep -Report $script:shipReport -Step "preflight" -Status "ok" -Detail "mode=$modeText; tag=$tag; branch=$branch"

$rerunHint = if ($isFinalizeMode) {
    "powershell -ExecutionPolicy Bypass -File .\scripts\ship.ps1 -FinalizeExistingTag $tag -FusionTested -NotesFile .\scripts\release_notes_pending.md"
}
else {
    "powershell -ExecutionPolicy Bypass -File .\scripts\ship.ps1 -BumpType $BumpType -FusionTested -NotesFile .\scripts\release_notes_pending.md"
}

Write-Step "Prepare release notes (preflight)"
$notesTemp = New-ReleaseNotesTemp `
    -RepoPath $WorkspaceRoot `
    -Tag $tag `
    -Version $newVersion `
    -ProvidedNotesFile $NotesFile `
    -WorkspacePath $WorkspaceRoot `
    -ScriptRoot $PSScriptRoot `
    -RerunHint $rerunHint
Add-ShipReportStep -Report $script:shipReport -Step "release_notes_preflight" -Status "ok" -Detail "notesTemp=$notesTemp"

if (-not $isFinalizeMode) {
    Write-Step "Sync source to live add-in"
    Invoke-Checked {
        & python $updateHelperPath `
            $SourceRoot `
            $LiveAddinRoot `
            settings.json update_state.json _pending_update .git BetterParameters.manifest
    } "Sync source->live failed"
    Add-ShipReportStep -Report $script:shipReport -Step "sync_source_to_live" -Status "ok"

    $syncCoreFiles = @("BetterParameters.py", "palette.html")
    foreach ($filename in $syncCoreFiles) {
        $sourceFile = Join-Path $SourceRoot $filename
        $liveFile = Join-Path $LiveAddinRoot $filename
        if (-not (Test-Path $liveFile)) {
            throw "Live sync validation failed; missing live file: $liveFile"
        }
        $srcHash = (Get-FileHash $sourceFile -Algorithm SHA256).Hash
        $liveHash = (Get-FileHash $liveFile -Algorithm SHA256).Hash
        if ($srcHash -ne $liveHash) {
            throw "Live sync validation failed for $filename (hash mismatch)."
        }
    }
    Add-ShipReportStep -Report $script:shipReport -Step "sync_hash_verify" -Status "ok" -Detail ("files=" + ($syncCoreFiles -join ","))

    Write-Step "Build deterministic package (pre-push)"
    Build-DeterministicPackage `
        -SourceRootPath $SourceRoot `
        -StageRootPath $stageRoot `
        -PackageRootPath $packageRoot `
        -ZipRootPath $zipRoot `
        -ZipPath $zipPath `
        -ExpectedVersion $newVersion `
        -ReleaseAssetsPath $releaseAssetsPath
    Add-ShipReportStep -Report $script:shipReport -Step "package_build_verify" -Status "ok" -Detail $zipPath

    Write-Step "Bump manifest version"
    $newManifestRaw = [regex]::Replace(
        $manifestRaw,
        '"version"\s*:\s*"\d+\.\d+\.\d+"',
        """version"": ""$newVersion""",
        1
    )
    if ($newManifestRaw -eq $manifestRaw) {
        throw "Manifest version replacement did not change content."
    }
    Set-Utf8NoBomFile -Path $manifestPath -Text $newManifestRaw

    $verifyRaw = Get-Content -Raw $manifestPath
    if (-not [regex]::IsMatch($verifyRaw, '"version"\s*:\s*"' + [regex]::Escape($newVersion) + '"')) {
        throw "Manifest version verification failed after write."
    }
    Add-ShipReportStep -Report $script:shipReport -Step "manifest_bump" -Status "ok" -Detail "version=$newVersion"

    Write-Step "Commit and tag"
    Invoke-Checked { & git -C $WorkspaceRoot add -A } "git add failed"
    & git -C $WorkspaceRoot diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        throw "No staged changes to commit."
    }
    Invoke-Checked { & git -C $WorkspaceRoot commit -m "Release $tag" } "git commit failed"
    Invoke-Checked { & git -C $WorkspaceRoot tag -a $tag -m "Release $tag" } "git tag failed"
    Add-ShipReportStep -Report $script:shipReport -Step "commit_and_tag" -Status "ok" -Detail $tag

    if (-not $SkipPush) {
        Write-Step "Push branch and tag"
        Invoke-Checked { & git -C $WorkspaceRoot push origin $branch } "git push branch failed"
        Invoke-Checked { & git -C $WorkspaceRoot push origin $tag } "git push tag failed"
        Add-ShipReportStep -Report $script:shipReport -Step "push" -Status "ok" -Detail ("branch=$branch; tag=$tag")
    }
}
else {
    Write-Step "Finalize existing tag (package verify + release publish)"
    Assert-ReleaseZip -ZipPath $zipPath -ExpectedVersion $newVersion -AllowedTopLevelEntries $allowedTopLevelReleaseAssets
    Add-ShipReportStep -Report $script:shipReport -Step "finalize_package_verify" -Status "ok" -Detail $zipPath
}

if (-not $SkipRelease) {
    Write-Step "Create or update GitHub release"
    $releaseExists = Test-GitHubReleaseExists -Tag $tag -Repo $RepoSlug

    if ($releaseExists) {
        Invoke-Checked { & gh release edit $tag --repo $RepoSlug --title $tag --notes-file $notesTemp } "gh release edit failed"
        Invoke-Checked { & gh release upload $tag $zipPath --repo $RepoSlug --clobber } "gh release upload failed"
    }
    else {
        Invoke-Checked { & gh release create $tag $zipPath --repo $RepoSlug --title $tag --notes-file $notesTemp } "gh release create failed"
    }

    Write-Step "Post-release verification"
    $releaseJson = & gh release view $tag --repo $RepoSlug --json tagName,url,assets
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch release for verification."
    }
    $release = $releaseJson | ConvertFrom-Json
    if ($release.tagName -ne $tag) {
        throw "Release tag mismatch. Expected $tag, got $($release.tagName)."
    }
    $assetNames = @($release.assets | ForEach-Object { $_.name })
    if ($assetNames -notcontains $zipName) {
        throw "Release asset missing expected zip: $zipName"
    }
    Write-Host "Release URL: $($release.url)"
    $script:shipReport.releaseUrl = [string]$release.url
    Add-ShipReportStep -Report $script:shipReport -Step "release_publish_verify" -Status "ok" -Detail $release.url
}

if (Test-Path $notesTemp) {
    Remove-Item -Force $notesTemp
}

Write-Step "Done"
Write-Host "Shipped $tag successfully."
Write-Host "Zip: $zipPath"
Write-Host "Stage: $packageRoot"
$script:shipReport.status = "success"
Add-ShipReportStep -Report $script:shipReport -Step "done" -Status "ok"
Save-ShipReport -Report $script:shipReport
Write-Host "Ship report: $($script:shipReport.reportPath)"
