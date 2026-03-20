# Decision de Dominio Financiero

Para cerrar la Fase 4 se adopta esta decision:

- **Se crea `Charge` como entidad nueva**
- `Payment` se conserva como registro de cobro y compatibilidad temporal

## Motivo

`Payment` por si solo no permite modelar correctamente el cargo escolar porque mezcla:

- obligacion de pago
- estatus de cobro
- relacion operativa con el alumno

Con `Charge` el sistema ya puede asociar el cargo a:

- alumno
- inscripcion del ciclo
- tipo de cargo
- periodo

Mientras tanto `Payment` sigue existiendo para no romper frontend ni flujos ya publicados.

## Regla tecnica adoptada

- `Charge` representa el cargo por inscripcion o periodo
- `Payment` representa el cobro asociado
- por compatibilidad actual se mantiene un `Payment` espejo por cada `Charge`

## Impacto esperado

Con esto ya se puede continuar despues con:

- tesoreria por ciclo
- cartera vencida real
- becas y descuentos recurrentes
- reportes de cargos emitidos vs cobrados
