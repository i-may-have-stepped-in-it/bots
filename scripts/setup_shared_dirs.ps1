#!/usr/bin/env powershell
<#
.SYNOPSIS
    Setup shared directories for Jennifer image generation backends.

.DESCRIPTION
    Creates the required directory structure for sharing models and outputs
    between Automatic1111, ComfyUI, and InvokeAI backends.

.EXAMPLE
    .\setup_shared_dirs.ps1
#>

$ErrorActionPreference = "Stop"

# Get the project root (scripts is in jennifer/scripts, so go up 2 levels)
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DataDir = Join-Path $ProjectRoot "data"
$OutputDir = Join-Path $ProjectRoot "output"

# Verify we're in the correct location
# docker-compose is in jennifer/ subdirectory
$DockerComposeFile = Join-Path (Join-Path $ProjectRoot "jennifer") "docker-compose-jennifer.yml"
if (-not (Test-Path $DockerComposeFile)) {
    Write-Host "ERROR: Cannot find docker-compose-jennifer.yml at: $DockerComposeFile" -ForegroundColor Red
    Write-Host "This script should be run from the stable-diffusion-webui-docker directory structure" -ForegroundColor Red
    Write-Host "Expected structure: stable-diffusion-webui-docker/jennifer/scripts/setup_shared_dirs.ps1"
    Write-Host ""
    Write-Host "Please run this script from the correct location." -ForegroundColor Yellow
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Shared Directories Setup for Jennifer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Define required directories
$RequiredDirs = @(
    # Core model directories (shared)
    "$DataDir\models\Stable-diffusion"
    "$DataDir\models\VAE"
    "$DataDir\models\Lora"
    "$DataDir\models\ControlNet"
    "$DataDir\models\ESRGAN"
    "$DataDir\models\hypernetworks"
    "$DataDir\embeddings"
    
    # Backend-specific app data
    "$DataDir\comfyui"
    "$DataDir\comfyui\custom_nodes"
    "$DataDir\invokeai"
    
    # Shared output
    "$OutputDir"
    "$OutputDir\txt2img"
    "$OutputDir\img2img"
    "$OutputDir\saved"
    
    # Config
    "$DataDir\config"
    "$ProjectRoot\config\sd-webui"
)

Write-Host "Creating required directories..." -ForegroundColor Yellow
Write-Host ""

$CreatedCount = 0
$ExistingCount = 0

foreach ($Dir in $RequiredDirs) {
    if (Test-Path $Dir) {
        Write-Host "  [EXISTS] $Dir" -ForegroundColor Gray
        $ExistingCount++
    } else {
        try {
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
            Write-Host "  [CREATE] $Dir" -ForegroundColor Green
            $CreatedCount++
        } catch {
            Write-Host "  [ERROR]  $Dir - $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Created:   $CreatedCount directories" -ForegroundColor Green
Write-Host "  Existing:  $ExistingCount directories" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verify critical paths
Write-Host "Verifying critical paths..." -ForegroundColor Yellow
Write-Host ""

$CriticalPaths = @{
    "Models (Stable-diffusion)" = "$DataDir\models\Stable-diffusion"
    "Models (VAE)" = "$DataDir\models\VAE"
    "Models (Lora)" = "$DataDir\models\Lora"
    "Output" = $OutputDir
    "ComfyUI Data" = "$DataDir\comfyui"
    "InvokeAI Data" = "$DataDir\invokeai"
}

$AllGood = $true
foreach ($Name in $CriticalPaths.Keys) {
    $Path = $CriticalPaths[$Name]
    if (Test-Path $Path) {
        Write-Host "  [OK] $Name -> $Path" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $Name -> $Path" -ForegroundColor Red
        $AllGood = $false
    }
}

Write-Host ""
if ($AllGood) {
    Write-Host "All critical directories are ready!" -ForegroundColor Green
} else {
    Write-Host "Some directories are missing. Please check errors above." -ForegroundColor Red
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Place your model files in: $DataDir\models\" -ForegroundColor White
Write-Host "  2. Start the desired backend with:" -ForegroundColor White
Write-Host "     docker compose --profile nvidia up -d" -ForegroundColor Yellow
Write-Host "     docker compose --profile comfyui-nvidia up -d" -ForegroundColor Yellow
Write-Host "     docker compose --profile invokeai-nvidia up -d" -ForegroundColor Yellow
Write-Host ""
