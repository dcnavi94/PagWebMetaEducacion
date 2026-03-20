# Política de limpieza y respaldos para `backend/uploads/`

## Alcance
- Carpeta de trabajo para archivos subidos por usuarios (`backend/uploads/usuarioId/archivo`).
- No debe versionarse en git ni sincronizarse fuera de entornos controlados.

## Retención
- Mantener archivos **30 días** por defecto.
- Conservar los marcados como evidencia o tickets abiertos; moverlos a `backend/uploads/retencion_larga/` antes de la limpieza mensual.

## Limpieza mensual (manual o cron)
1) Revisar pesos inusuales y carpetas vacías.
2) Eliminar archivos sin flag de retención con más de 30 días:
   - PowerShell: `Get-ChildItem backend/uploads -Recurse | Where-Object { -not $_.FullName.Contains('retencion_larga') -and $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force`
3) Borrar carpetas vacías: `Get-ChildItem backend/uploads -Recurse -Directory | Where-Object { -not $_.GetFileSystemInfos() } | Remove-Item`

## Respaldos
- Crear carpeta `backups/` en la raíz (excluida de git) y almacenar ZIP cifrados con fecha.
- Copia diaria recomendada en producción:
  - PowerShell: `Compress-Archive -Path backend/uploads/* -DestinationPath backups/uploads-$(Get-Date -Format yyyyMMdd).zip`
- Retener respaldos 90 días; rotar zips anteriores de forma automática o manual.
- Al restaurar, respetar la estructura por usuario para evitar colisiones.

## Seguridad
- Solo personal autorizado debe acceder a `uploads/` y `backups/`.
- Verificar antivirus/antimalware en los servidores que procesan archivos subidos.
- Validar tipo y tamaño de archivo en la API antes de guardar (pendiente en TODO de seguridad).

## Procedimiento rápido
- Semanal: revisar tamaño total (`du -sh backend/uploads` o equivalente en Windows).
- Mensual: ejecutar comando de limpieza y generar respaldo del estado previo.
- Incidentes: si se detecta malware, aislar el archivo, eliminarlo y generar respaldo limpio.
