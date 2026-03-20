# Fase 3 - Cierre de Migracion y Compatibilidad

La Fase 3 se considera cerrada con estos entregables:

- alineacion tecnica documentada
- script de backfill desde `User` hacia `StudentEnrollment`
- conversion de grupos basados en texto hacia `Group` durante el backfill
- auditoria de conteos sobre el modelo nuevo
- compatibilidad temporal documentada para el frontend admin actual

## 1. Script operativo

Comando:

```bash
cd backend
python -m app.backfill_school_data --apply
```

Este script:

- localiza el ciclo destino
- revisa alumnos con datos legacy relevantes
- crea o reutiliza registros `Group`
- crea o actualiza `StudentEnrollment`
- reporta conteos de creacion, actualizacion y grupos reconciliados

## 2. Conversion de grupos legacy

La conversion de grupos basados en texto se resuelve en el mismo proceso de backfill:

- si `User.grupo` tiene valor
- y no existe un `Group` con el mismo nombre/modalidad
- se crea el grupo formal
- despues se asigna al `StudentEnrollment`

## 3. Compatibilidad temporal

Durante la convivencia de modelos:

- el frontend actual puede seguir trabajando con endpoints puente
- el backend sigue sincronizando campos legacy necesarios
- la fuente operativa nueva ya es `StudentEnrollment` y `CourseEnrollment`

Ver detalle en `docs/ADMIN_PHASE3_COMPATIBILITY.md`.

## 4. Resultado

Con esto, la Fase 3 queda cerrada y el proyecto puede pasar a las siguientes prioridades:

- Fase 5 frontend admin
- redefinicion de finanzas por inscripcion/cargos
- limpieza futura del puente legacy
