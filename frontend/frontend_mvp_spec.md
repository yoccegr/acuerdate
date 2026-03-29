# Frontend MVP — Especificación funcional

## Descripción
Esta etapa define el frontend Flutter del MVP de Acuérdate!.

El frontend no toma decisiones de negocio. Su responsabilidad es:
- capturar la lista del usuario
- solicitar ubicación
- enviar el request al backend
- mostrar el resultado
- manejar errores y casos sin resultados

---

## Pantallas del MVP

### 1. ListScreen
Pantalla principal del MVP.

#### Objetivo
Permitir que el usuario ingrese su lista de productos y solicite una recomendación.

#### Componentes
- campo de texto multilinea para escribir productos
- botón principal: "Buscar mejor tienda"
- mensajes de error o validación
- indicador de carga cuando el request está en proceso

---

### 2. ResultScreen
Pantalla de resultado.

#### Objetivo
Mostrar la tienda recomendada y la información útil devuelta por el backend.

#### Componentes
- nombre de la tienda recomendada
- tipo de tienda
- distancia aproximada
- alternativas del mismo tipo
- opcionales si existen
- botón para volver

---

## Flujo del usuario

1. El usuario abre la app
2. Ve ListScreen
3. Escribe su lista
4. Presiona "Buscar mejor tienda"
5. La app solicita ubicación
6. Si la ubicación está disponible:
   - envía request al backend
7. Si el backend responde `ok`:
   - navega a ResultScreen
8. Si responde `no_results`:
   - muestra mensaje en ListScreen
9. Si hay error de ubicación o backend:
   - muestra mensaje en ListScreen

---

## Estados mínimos del frontend

- `idle`
- `loading`
- `success`
- `no_results`
- `error_location`
- `error_backend`

---

## Consumo del backend

### Request
```json
{
  "items": ["leche", "shampoo", "pañales"],
  "location": {
    "lat": -33.4489,
    "lng": -70.6693
  }
}
```

### Response esperado (éxito)
```json
{
  "status": "ok",
  "engine": {
    "classification_summary": {
      "total_items": 3,
      "unrecognized": 0
    },
    "rule_applied": "specialist_clear"
  },
  "maps": {
    "recommendation": {
      "store": {
        "name": "Farmacia Cruz Verde",
        "type": "farmacia",
        "distance_m": 340
      },
      "alternatives": []
    },
    "optional": [],
    "search_status": {
      "primary_found": true
    }
  }
}
```

---

## Información que debe mostrar el resultado

### Recomendación principal
- nombre de la tienda
- tipo de tienda
- distancia aproximada

### Alternativas
- otras tiendas del mismo tipo recomendado

### Opcionales
- tiendas complementarias si existen

### Información adicional útil
- mensaje claro del resultado
- posibilidad de volver a editar la lista

---

## Manejo de errores y casos borde

### Lista vacía
- no enviar request
- mostrar mensaje de validación en ListScreen

### Ubicación no disponible
- no enviar request
- mostrar mensaje de error de ubicación

### Error del backend
- mostrar mensaje de error genérico
- permitir reintento

### No hay resultados
- mostrar mensaje claro en ListScreen
- mantener la lista escrita

---

## Reglas importantes del frontend

- no clasifica productos
- no decide cobertura
- no elige tienda
- no reinterpreta el response
- solo consume y muestra

---

## Qué queda fuera del MVP frontend

- historial
- perfil
- onboarding
- configuración
- favoritos
- mapa interactivo
- edición de parámetros
- escaneo de boletas
- notificaciones
- autenticación

---

## Principios del frontend MVP

- mínimo número de pantallas
- mínima fricción
- mensajes claros
- resultado visible rápido
- lógica de negocio fuera del frontend

---

## Resultado esperado

Un frontend Flutter simple, claro y alineado con el backend, listo para implementación del MVP.
