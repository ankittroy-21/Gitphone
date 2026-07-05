#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sets up TELEGRAM_SECRET_TOKEN for Gitphone webhook security.

.DESCRIPTION
    1. Generates a cryptographically secure random token
    2. Appends it to backend/.env (skips if already set)
    3. Calls the Telegram setWebhook API to register the secret_token
    4. Verifies the webhook is properly configured

.USAGE
    From the repo root:
    .\setup_telegram_secret.ps1

    Or with a custom token:
    .\setup_telegram_secret.ps1 -Token "my_custom_token"
#>

param(
    [string]$Token = ""
)

$ErrorActionPreference = "Stop"

# --- Colors -------------------------------------------------------------------
function Write-Step  { param($msg) Write-Host "`n> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "  OK: $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  WARN: $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  FAIL: $msg" -ForegroundColor Red; exit 1 }

# --- Step 1: Load .env --------------------------------------------------------
Write-Step "Loading backend/.env"

$envFile = "backend/.env"
if (-not (Test-Path $envFile)) {
    Write-Fail ".env not found at $envFile -- copy .env.example and fill in your values first."
}

$envContent = Get-Content $envFile -Raw
$envLines   = Get-Content $envFile

# Parse key=value pairs
$envMap = @{}
foreach ($line in $envLines) {
    if ($line -match "^\s*([^#][^=]*?)\s*=\s*(.*)\s*$") {
        $envMap[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$botToken   = $envMap["TELEGRAM_BOT_TOKEN"]
$webhookUrl = $envMap["WEBHOOK_URL"]

if (-not $botToken)   { Write-Fail "TELEGRAM_BOT_TOKEN not found in .env" }
if (-not $webhookUrl) { Write-Fail "WEBHOOK_URL not found in .env" }

Write-Ok "Bot token found"
Write-Ok "Webhook URL: $webhookUrl"

# --- Step 2: Generate or use provided token -----------------------------------
Write-Step "Setting up TELEGRAM_SECRET_TOKEN"

if ($envMap.ContainsKey("TELEGRAM_SECRET_TOKEN") -and $envMap["TELEGRAM_SECRET_TOKEN"] -ne "" -and $Token -eq "") {
    $secretToken = $envMap["TELEGRAM_SECRET_TOKEN"]
    Write-Warn "TELEGRAM_SECRET_TOKEN already exists in .env -- using existing: $($secretToken.Substring(0, [Math]::Min(8, $secretToken.Length)))..."
} else {
    if ($Token -ne "") {
        $secretToken = $Token
        Write-Ok "Using provided custom token"
    } else {
        # Generate a cryptographically secure 32-byte hex token
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
        $rng.GetBytes($bytes)
        $rng.Dispose()
        $secretToken = [BitConverter]::ToString($bytes).Replace("-", "").ToLower()
        Write-Ok "Generated new secure token: $($secretToken.Substring(0, 8))..."
    }

    # Append or update in .env
    if ($envContent -match "TELEGRAM_SECRET_TOKEN=") {
        # Replace existing (possibly empty) value
        $newContent = $envContent -replace "TELEGRAM_SECRET_TOKEN=.*", "TELEGRAM_SECRET_TOKEN=$secretToken"
        Set-Content $envFile $newContent -NoNewline
        Write-Ok "Updated TELEGRAM_SECRET_TOKEN in .env"
    } else {
        # Append to end
        Add-Content $envFile "`nTELEGRAM_SECRET_TOKEN=$secretToken"
        Write-Ok "Appended TELEGRAM_SECRET_TOKEN to .env"
    }
}

# Validate token: Telegram requires 1-256 chars, only [A-Za-z0-9_-]
if ($secretToken -notmatch "^[A-Za-z0-9_-]{1,256}$") {
    Write-Fail "Token contains invalid characters. Telegram only allows: A-Z a-z 0-9 _ -"
}

# --- Step 3: Register secret_token with Telegram setWebhook -------------------
Write-Step "Registering webhook with Telegram (with secret_token)"

$webhookEndpoint = "$($webhookUrl.TrimEnd('/'))/webhook"
$telegramApiUrl  = "https://api.telegram.org/bot$botToken/setWebhook"

$body = @{
    url             = $webhookEndpoint
    allowed_updates = @("message", "callback_query")
    secret_token    = $secretToken
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri $telegramApiUrl -Method POST `
        -ContentType "application/json" -Body $body
} catch {
    Write-Fail "Telegram API call failed: $($_.Exception.Message)"
}

if ($response.ok -eq $true) {
    Write-Ok "Telegram setWebhook succeeded: $($response.description)"
} else {
    Write-Fail "Telegram setWebhook failed: $($response.description)"
}

# --- Step 4: Verify webhook info ----------------------------------------------
Write-Step "Verifying webhook configuration"

$infoUrl = "https://api.telegram.org/bot$botToken/getWebhookInfo"
$info    = Invoke-RestMethod -Uri $infoUrl -Method GET

Write-Ok "Webhook URL        : $($info.result.url)"
Write-Ok "Pending updates    : $($info.result.pending_update_count)"

if ($info.result.last_error_message) {
    Write-Warn "Last webhook error: $($info.result.last_error_message)"
}

# --- Summary ------------------------------------------------------------------
Write-Host ""
Write-Host "====================================================" -ForegroundColor Magenta
Write-Host "  TELEGRAM_SECRET_TOKEN setup complete!" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Token (first 8 chars): $($secretToken.Substring(0, [Math]::Min(8, $secretToken.Length)))..." -ForegroundColor White
Write-Host ""
Write-Host "  NEXT STEP (manual):" -ForegroundColor Yellow
Write-Host "  Add TELEGRAM_SECRET_TOKEN to your Render dashboard:" -ForegroundColor White
Write-Host "  https://dashboard.render.com --> your service --> Environment" -ForegroundColor Gray
Write-Host "  Value: $secretToken" -ForegroundColor Gray
Write-Host ""
