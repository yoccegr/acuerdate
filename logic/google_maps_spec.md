# Google Maps — Especificación funcional (MVP)

## Descripción
Esta etapa toma el resultado de cobertura y selección de tipo de tienda, y lo transforma en una recomendación de tienda concreta.

No decide el tipo de tienda: eso ya fue resuelto en la etapa anterior.  
Aquí se decide **qué tienda específica recomendar** dentro del tipo ya definido.

---

## Qué recibe esta etapa

### Entrada esperada
- resultado de cobertura
- ubicación del usuario
- radio de búsqueda

### Ejemplo de entrada
```json
{
  "search_profile": {
    "primary": ["farmacia"],
    "fallback": ["supermercado"],
    "optional": []
  },
  "user_location": {
    "lat": -36.6067,
    "lng": -72.1034
  },
  "search_radius_m": 1000
}
```

---

## Qué decide esta etapa

1. Buscar tiendas cercanas según el tipo de tienda definido en `primary`
2. Elegir la mejor tienda del tipo principal
3. Si no hay resultados útiles, usar `fallback`
4. Si existen tipos `optional`, buscarlos y devolverlos como complementarios
5. Entregar una salida final lista para frontend y notificaciones

---

## Reglas de búsqueda

### 1. Búsqueda por tipo principal
- Se busca primero el tipo de tienda definido en `primary`
- Se consultan resultados dentro del radio indicado
- Se aceptan resultados con horario conocido y desconocido

### 2. Selección de la mejor tienda
Criterio principal:
- menor distancia aproximada calculada a partir de coordenadas

Importante:
- esta distancia es aproximada
- no representa ruta real ni tiempo real de traslado

### 3. Horarios
- Si el resultado trae `open_now`, se conserva
- Si no trae información de horario, el resultado sigue siendo válido
- En ese caso se marca:
```json
{
  "hours_unknown": true
}
```

### 4. Fallback
- Si no hay resultados útiles para `primary`, se intenta con `fallback`
- Si no existe fallback aplicable, se permite una única re-búsqueda con radio ampliado sobre el mismo tipo principal

### 5. Optional
- Si existen tipos opcionales, se buscan por separado
- No reemplazan la recomendación principal
- Se entregan como complemento

---

## Definiciones importantes

- `recommendation`: tienda recomendada principal
- `alternatives`: otras tiendas del mismo tipo recomendado
- `optional`: tiendas de tipos complementarios
- `fallback_used`: indica si la recomendación final vino desde fallback

---

## Flujo funcional

1. Recibir perfil de búsqueda, ubicación y radio
2. Buscar candidatos del tipo `primary`
3. Ordenar candidatos por distancia aproximada
4. Elegir el primero como `recommendation`
5. Guardar el resto como `alternatives`
6. Si no hay resultados:
   - intentar `fallback`
   - si no existe o falla, ampliar radio una sola vez
7. Buscar `optional` si aplica
8. Construir respuesta final

---

## Estructura de salida

```json
{
  "recommendation": {
    "name": "Farmacias Ahumada",
    "type": "farmacia",
    "distance_m": 180,
    "lat": -36.6061,
    "lng": -72.1028,
    "open_now": true,
    "hours_unknown": false
  },
  "alternatives": [
    {
      "name": "Cruz Verde",
      "type": "farmacia",
      "distance_m": 260,
      "lat": -36.6050,
      "lng": -72.1012,
      "open_now": null,
      "hours_unknown": true
    }
  ],
  "optional": [],
  "fallback_used": false,
  "search_status": "success"
}
```

---

## Estados posibles de búsqueda

- `success`
- `fallback_success`
- `expanded_radius_success`
- `no_results`
- `missing_location`

---

## Casos de ejemplo

### Caso A — Éxito con primary
Entrada:
- primary = farmacia
- fallback = supermercado
- optional = []

Resultado:
- se encuentra farmacia cercana
- se recomienda la más cercana
- `fallback_used = false`
- `search_status = success`

---

### Caso B — Primary falla, fallback funciona
Entrada:
- primary = panaderia
- fallback = supermercado

Resultado:
- no hay panadería cercana
- sí hay supermercado
- se recomienda supermercado
- `fallback_used = true`
- `search_status = fallback_success`

---

### Caso C — No hay primary ni fallback, radio ampliado
Entrada:
- primary = farmacia
- fallback = []

Resultado:
- no hay farmacia en radio inicial
- se amplía radio una vez
- aparece una farmacia
- `search_status = expanded_radius_success`

---

### Caso D — Sin ubicación
Entrada:
- ubicación faltante o inválida

Resultado:
- no se ejecuta búsqueda
- `search_status = missing_location`

---

### Caso E — Optional presente
Entrada:
- primary = supermercado
- optional = ["botilleria"]

Resultado:
- se recomienda supermercado
- además se devuelven botillerías cercanas en `optional`

---

## Límites de responsabilidad de esta etapa

Esta etapa:
- sí busca tiendas concretas
- sí ordena resultados
- sí selecciona la tienda recomendada

Esta etapa no:
- no clasifica productos
- no decide el tipo de tienda
- no calcula cobertura
- no decide notificaciones
- no calcula rutas reales
