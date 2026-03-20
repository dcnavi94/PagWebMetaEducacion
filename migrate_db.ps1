# Script para aplicar migraciones de base de datos con Alembic

$ErrorActionPreference = "Stop"

Write-Host "Iniciando migración de base de datos..." -ForegroundColor Cyan

# Directorio donde se encuentra el backend
$backendDir = ".\backend"

# Verificar si la carpeta existe
if (-not (Test-Path $backendDir)) {
    Write-Error "No se encontró el directorio backend en $backendDir"
    exit
}

# Configurar PYTHONPATH para que Alembic encuentre la app
$env:PYTHONPATH = (Resolve-Path $backendDir).Path

# Cambiar al directorio del backend
Set-Location $backendDir

# Ejecutar la migración
try {
    Write-Host "Ejecutando: python -m alembic upgrade head" -ForegroundColor Yellow
    python -m alembic upgrade head
    Write-Host "Migración completada exitosamente." -ForegroundColor Green
} catch {
    Write-Error "Error al ejecutar la migración: $_"
}

# Regresar al directorio original
Set-Location ..
