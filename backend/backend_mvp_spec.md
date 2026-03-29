# Backend MVP — Especificación técnica final

## 🧠 Visión general

El backend recibe una lista de texto libre y una ubicación, y devuelve una tienda concreta recomendada.

Flujo general:

cliente → clasificador → cobertura → Google Maps → respuesta

---

## ⚙️ Inicialización vs ejecución

### Inicialización (una sola vez)
- DictionaryLoader → carga JSON
- ClassifierIndex → construye índice
- Parámetros:
  - specialist_coverage_threshold = 0.85
  - specialist_max_items = 6
  - optional_coverage_threshold = 0.50
  - radius_meters = 1500

### Por request
- Classifier
- CoverageEngine
- MapsClient
- RequestHandler

---

## 🧱 Módulos

### DictionaryLoader
Carga diccionario desde archivo.

### ClassifierIndex
Construye índice inmutable.

### Classifier
Convierte texto → {norm, category, match_type}

### CoverageEngine
Decide tipo de tienda:
{ primary, fallback, optional, rule_applied }

### MapsClient
Busca tienda concreta usando:
(search_profile, user_location, radius_meters)

### RequestHandler
Orquesta todo el flujo.

---

## 🔄 Flujo por request

1. Validar request
2. Clasificar items
3. Calcular cobertura
4. Buscar en Maps
5. Construir response

---

## 📥 Request

```json
{
  "items": ["leche", "shampoo"],
  "location": {
    "lat": -33.44,
    "lng": -70.66
  }
}
```

---

## 📤 Response

```json
{
  "status": "ok",
  "engine": {
    "classification_summary": {
      "total_items": 2,
      "unrecognized": 0
    },
    "rule_applied": "specialist_clear"
  },
  "maps": {
    "recommendation": {
      "store": {
        "name": "Farmacia",
        "distance_m": 200
      }
    }
  }
}
```

---

## ❗ Manejo de errores

### 400 (request inválido)
- missing_items
- invalid_item_format
- missing_location
- invalid_coordinates

### 200 (no_results)
No hay tiendas disponibles

### 500 (errores internos)
- maps_timeout
- maps_quota_exceeded
- maps_auth_error
- internal_error

---

## 🔗 Contratos

Cada módulo solo conoce:
- su input
- su output

RequestHandler conecta todo.

---

## 🚫 Fuera de scope

- lenguaje backend
- autenticación
- cache
- infraestructura
- frontend
- notificaciones

---

## 🎯 Objetivo

Sistema backend simple, modular y listo para implementación.
