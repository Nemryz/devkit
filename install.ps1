# install.ps1 - Instalador de devkit para Windows
# Uso: .\install.ps1
# O desde cualquier carpeta: powershell -File C:\ruta\devkit\install.ps1

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $raiz) { $raiz = (Get-Location).Path }

Write-Host "devkit - Instalador" -ForegroundColor Cyan
Write-Host "Raiz del proyecto: $raiz"

# 1. Sincronizar dependencias
Write-Host "Sincronizando dependencias..." -ForegroundColor Yellow
Push-Location $raiz
uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync fallo" }
Pop-Location

# 2. Descubrir directorio de ejecutables de uv
$binDir = $null
try {
    $binDir = (uv tool dir --bin 2>$null).Trim()
} catch { }
if (-not $binDir) { $binDir = Join-Path $env:USERPROFILE ".local\bin" }
if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }

# 3. Instalar como herramienta global (empaquetada, no editable)
$editable = $false
if ($args -contains '--editable') { $editable = $true }

Write-Host "Instalando dev como herramienta global..." -ForegroundColor Yellow
if ($editable) {
    uv tool install --editable $raiz --force
} else {
    uv tool install $raiz --force
}
if ($LASTEXITCODE -ne 0) { throw "uv tool install fallo" }

# 4. Verificar PATH
$devExe = Join-Path $binDir "dev.exe"
if (-not (Test-Path $devExe)) {
    Write-Host "ERROR: dev.exe no se encontro en $binDir" -ForegroundColor Red
    exit 1
}

# 5. Agregar al PATH del usuario si falta
$pathActual = [Environment]::GetEnvironmentVariable("Path", "User")
if ($pathActual -notlike "*$binDir*") {
    Write-Host "Agregando $binDir al PATH del usuario..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$pathActual;$binDir", "User")
    Write-Host "PATH actualizado. Reinicia la consola para usar dev desde cualquier carpeta." -ForegroundColor Green
} else {
    Write-Host "PATH ya contiene $binDir" -ForegroundColor Green
}

# 6. Verificar
Write-Host "Verificando instalacion..." -ForegroundColor Yellow
& $devExe --version
if ($LASTEXITCODE -ne 0) { throw "verificacion fallo" }

Write-Host ""
Write-Host "devkit instalado correctamente." -ForegroundColor Green
Write-Host "Usa 'dev --help' desde cualquier carpeta." -ForegroundColor Green
Write-Host "Si 'dev' no responde, reinicia la consola." -ForegroundColor Yellow
