$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "src"
$dist = Join-Path $root "dist"
$pluginId = "upload_quality"
$staging = Join-Path $dist $pluginId
$zipPath = Join-Path $dist "$pluginId.zip"

if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

if (-not (Test-Path -LiteralPath $dist)) {
    New-Item -ItemType Directory -Path $dist | Out-Null
}

New-Item -ItemType Directory -Path $staging | Out-Null

Copy-Item -LiteralPath (Join-Path $source "__init__.py") -Destination $staging
Copy-Item -LiteralPath (Join-Path $source "PLUGININFO") -Destination $staging
Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination $staging

Compress-Archive -LiteralPath $staging -DestinationPath $zipPath

Write-Output "Created:"
Write-Output "  $staging"
Write-Output "  $zipPath"
