# Cobertura y selección de tienda — Acuérdate! (Fase 1.5)

## Descripción
Esta etapa decide si conviene:
- consolidar la compra en supermercado
- o priorizar una tienda especializada

No decide la tienda específica, solo el tipo de tienda y orden de búsqueda.

---

## Parámetros del MVP

SPECIALIST_COVERAGE_THRESHOLD = 0.85
SPECIALIST_MAX_ITEMS = 6
OPTIONAL_COVERAGE_THRESHOLD = 0.50

---

## Tipos de tienda

- supermercado
- botilleria
- panaderia
- farmacia

---

## Compatibilidad por tienda

panaderia:
- solo items con norm "pan"

botilleria:
- category == "bebidas"

farmacia:
- category in ["cuidado_personal", "bebe"]

supermercado:
- cubre todo

---

## Función de cobertura

panaderia:
- contar items con norm "pan"

botilleria:
- contar items con category "bebidas"

farmacia:
- contar items con category "cuidado_personal" o "bebe"

---

## Reglas de decisión

### Regla 1 — Especialista clara

Si:
- cobertura >= 0.85
- total_items <= 6

Entonces:
- primary = especialista
- fallback = supermercado

---

### Regla 2 — Supermercado + opcionales

Siempre aplica si la Regla 1 no se cumple

- primary = supermercado
- optional = especialistas con cobertura >= 0.50

---

## Output esperado

{
  "primary": ["supermercado"],
  "fallback": [],
  "optional": ["botilleria"],
  "rule": "supermarket_with_optional"
}

---

## Principios

- minimizar número de paradas
- supermercado es fallback fuerte
- especialistas solo cuando hay alta concentración
- decisiones basadas en la lista real
