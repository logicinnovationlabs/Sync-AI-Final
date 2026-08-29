<#
.SYNOPSIS
  Create a distribution archive that never includes secrets or local junk.

.DESCRIPTION
  Prefer `git archive` (honours .gitignore and only includes tracked files).
  Falls back to a filtered Compress-Archive with an explicit deny-list.

  NEVER zip the raw working tree with Explorer "Send to compressed folder".

.EXAMPLE
  .\scripts\package-safe-archive.ps1
  .\scripts\package-safe-archive.ps1 -OutFile "..\SnyQ_Phase_2-safe.zip"
#>

[CmdletBinding()]
param(
  [string]$OutFile = "",
  [switch]$AllowWorkingTreeFallback
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $OutFile) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $OutFile = Join-Path (Split-Path $Root -Parent) "SnyQ_Phase_2-safe-$stamp.zip"
}

$denyNamePatterns = @(
  "^\.env$",
  "^\.env\.",
  "\.pem$",
  "\.key$",
  "\.p12$",
  "\.pfx$",
  "credentials\.json$",
  "service-account.*\.json$",
  "token.*\.json$"
)

$denyPathSegments = @(
  "\.venv\",
  "\venv\",
  "\node_modules\",
  "\backend\keys\",
  "\keys\",
  "\.git\",
  "\__pycache__\",
  "\.pytest_cache\",
  "\.next\",
  "\dist\",
  "\htmlcov\"
)

$secretContentHints = @(
  "GOCSPX-",
  "BEGIN RSA PRIVATE KEY",
  "BEGIN PRIVATE KEY",
  "BEGIN OPENSSH PRIVATE KEY",
  "sk-or-v1-",
  "Azure AD client secret patterns are not scanned by prefix alone"
)

function Test-DeniedPath([string]$rel) {
  $norm = $rel -replace "/", "\"
  foreach ($seg in $denyPathSegments) {
    if ($norm -like "*$seg*" -or $norm.StartsWith($seg.TrimStart("\"))) { return $true }
  }
  $leaf = Split-Path $norm -Leaf
  foreach ($pat in $denyNamePatterns) {
    if ($leaf -match $pat) { return $true }
  }
  return $false
}

function Assert-NoSecretContent([string]$path) {
  if (-not (Test-Path $path -PathType Leaf)) { return }
  $ext = [IO.Path]::GetExtension($path).ToLowerInvariant()
  if ($ext -in @(".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".exe", ".dll", ".so", ".pyc")) {
    return
  }
  $relNorm = $path.Replace("\", "/").ToLowerInvariant()
  # Known fake / fixture markers (not live credentials).
  if ($relNorm -match "seed_fake_service_account\.py|/fixtures/|test_grounded_chat_prompt\.py") {
    return
  }
  try {
    $sample = Get-Content -LiteralPath $path -Raw -ErrorAction Stop
  } catch {
    return
  }
  if ($null -eq $sample) { return }
  if ($sample.Length -gt 2MB) { $sample = $sample.Substring(0, 2MB) }
  if ($sample -match "DEV_FAKE_PRIVATE_KEY_NOT_REAL|DO_NOT_USE_IN_PRODUCTION") {
    return
  }
  foreach ($hint in @("GOCSPX-", "BEGIN RSA PRIVATE KEY", "BEGIN PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY", "sk-or-v1-")) {
    if ($sample.Contains($hint)) {
      throw "Refusing to package '$path': matched secret marker '$hint'. Rotate that credential and keep it out of archives."
    }
  }
}

Write-Host "Packaging from: $Root"
Write-Host "Output:         $OutFile"

if (Test-Path $OutFile) { Remove-Item -Force $OutFile }

# Preferred path: git archive only ships tracked files (.gitignore already applied).
$gitOk = $false
try {
  git rev-parse --is-inside-work-tree 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $tmpTar = [IO.Path]::GetTempFileName() + ".tar"
    git archive --format=tar -o $tmpTar HEAD
    if ($LASTEXITCODE -ne 0) { throw "git archive failed" }

    # Convert tar -> zip without expanding secrets from the worktree.
    $tmpDir = Join-Path ([IO.Path]::GetTempPath()) ("snyq-archive-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    try {
      tar -xf $tmpTar -C $tmpDir
      Get-ChildItem -Path $tmpDir -Recurse -File | ForEach-Object {
        Assert-NoSecretContent $_.FullName
      }
      Compress-Archive -Path (Join-Path $tmpDir "*") -DestinationPath $OutFile -Force
      $gitOk = $true
      Write-Host "OK: created via git archive (tracked files only)."
    } finally {
      Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
      Remove-Item -Force $tmpTar -ErrorAction SilentlyContinue
    }
  }
} catch {
  Write-Warning "git archive path failed: $_"
}

if (-not $gitOk) {
  if (-not $AllowWorkingTreeFallback) {
    throw "git archive unavailable. Re-run with -AllowWorkingTreeFallback only if you accept a filtered worktree zip."
  }
  Write-Warning "Falling back to filtered working-tree zip (explicit deny-list)."
  $stage = Join-Path ([IO.Path]::GetTempPath()) ("snyq-wt-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $stage | Out-Null
  try {
    Get-ChildItem -Path $Root -Recurse -File -Force | ForEach-Object {
      $rel = $_.FullName.Substring($Root.Path.Length).TrimStart("\", "/")
      if (Test-DeniedPath $rel) { return }
      Assert-NoSecretContent $_.FullName
      $dest = Join-Path $stage $rel
      $destParent = Split-Path $dest -Parent
      if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Force -Path $destParent | Out-Null
      }
      Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
    }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $OutFile -Force
    Write-Host "OK: created via filtered working-tree fallback."
  } finally {
    Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
  }
}

$size = (Get-Item $OutFile).Length
Write-Host ("Archive size: {0:N0} bytes" -f $size)
Write-Host "Reminder: rotate Google OAuth client secret + JWT keys if a previous raw zip was shared."
