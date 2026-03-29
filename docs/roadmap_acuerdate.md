# 🛒 ROADMAP DEFINITIVO — Acuérdate!

---

## 🎯 Objetivo del Producto
Recomendar automáticamente la mejor tienda cercana donde el usuario pueda comprar la mayor parte (o todo) de su lista, minimizando esfuerzo y decisiones.

---

## 🧠 Principios del Sistema (No se rompen)

- El usuario solo escribe la lista  
- La app decide por él  
- Se prioriza menor fricción (menos paradas)  
- El sistema funciona sin historial  
- La inteligencia (boletas) es opcional  
- El supermercado es fallback natural  

---

# 🧱 Fase 0 — Definición Base (1–2 días)

### 🔹 Categorías funcionales (MVP)
- alimentos  
- bebidas  
- limpieza  
- cuidado_personal  
- hogar  
- mascotas  
- bebé  
- snacks  
- otros  

### 🔹 Tipos de tienda
- supermercado  
- botillería  
- panadería  
- farmacia  

### 🔹 Cobertura por tienda

| Tienda       | Categorías |
|-------------|-----------|
| supermercado | todas |
| botillería   | bebidas |
| panadería    | alimentos |
| farmacia     | cuidado_personal + bebé |

---

### 🔹 Regla de decisión (MVP)

1. Calcular cobertura por tienda  
2. Si supermercado cubre ≥ 70% → gana  
3. Si no:
   - elegir combinación con menos paradas  
4. Desempate → tienda más cercana  

✔️ Resultado: lógica completamente definida

---

# ⚙️ Fase 1 — Motor Base (Backend) (4–6 días)

### 🎯 Objetivo
Procesar lista → devolver mejor tienda

### 🔹 Flujo

1. Input  
```python
["pan", "cerveza", "lavaloza"]
```

2. Clasificación  
- pan → alimentos  
- cerveza → bebidas  
- lavaloza → limpieza  

3. Normalización  
```python
[
 {item: "pan", categoria: "alimentos"},
 {item: "cerveza", categoria: "bebidas"},
 {item: "lavaloza", categoria: "limpieza"}
]
```

4. Evaluación de cobertura  

| tienda       | cubre |
|-------------|------|
| supermercado | 3/3 |
| botillería   | 1/3 |
| panadería    | 1/3 |

5. Selección de tipo de tienda  

6. Integración con Google Maps  
- buscar tiendas cercanas  
- elegir la más cercana  

### 🔹 Output
```json
{
 "tienda": "Lider",
 "tipo": "supermercado",
 "distancia": "200m"
}
```

✔️ Resultado: motor funcional

---

# 📱 Fase 2 — Frontend MVP (Flutter) (5–7 días)

### 🎯 Objetivo
Flujo completo usuario → recomendación

### 🔹 Pantalla única

**Input**
- texto tipo WhatsApp  
- productos separados por coma o salto  

**Acción**
- botón: Guardar lista  

**Estado**
- lista guardada localmente  

**Trigger**
- botón: Ver recomendación  

**Output**
> “Compra todo en Lider 🛒”

✔️ Resultado: producto usable

---

# 📍 Fase 3 — Ubicación + Notificaciones (3–5 días)

### 🎯 Objetivo
Automatizar el momento correcto

### 🔹 Funcionalidades

1. Ubicación en background  
2. Geofencing (radio 300m)  
3. Trigger por proximidad  
4. Notificación  

> “Estás cerca de Lider 🛒  
> Puedes comprar todo lo de tu lista”

5. Control: 1 notificación por lista  

✔️ Resultado: experiencia automática

---

# 🧪 Fase 4 — Validación (3–7 días)

### 🎯 Objetivo
Confirmar utilidad real

### 🔹 Pruebas
- 5–10 usuarios  

### 🔹 Métricas
- uso real  
- feedback  
- repetición  

✔️ Resultado: validación inicial

---

# 🧠 Fase 5 — Expansión del Motor (4–7 días)

### 🎯 Objetivo
Mejorar precisión

### 🔹 Mejoras
- ampliar diccionario  
- agregar sinónimos  
- mejorar clasificación  

### 🔹 Manejo de desconocidos
- categoría “otros”  
- fallback: supermercado  

✔️ Resultado: motor robusto

---

# 🧾 Fase 6 — Boletas (OCR + Aprendizaje) (7–12 días)

### 🎯 Objetivo
Agregar inteligencia progresiva

### 🔹 Flujo
- input: imagen / PDF  
- OCR  
- extracción de datos  
- almacenamiento  
- uso para recomendaciones  

✔️ Resultado: sistema aprende

---

# 🔁 Fase 7 — Iteración Continua

### 🔹 Ajustes
- lógica  
- precisión  
- experiencia  

---

# ⏱️ Resumen General

| Fase | Tiempo |
|------|-------|
| Fase 0 | 1–2 días |
| Fase 1 | 4–6 días |
| Fase 2 | 5–7 días |
| Fase 3 | 3–5 días |
| Fase 4 | paralelo |
| Fase 5 | 4–7 días |
| Fase 6 | 7–12 días |

---

# 🎯 Orden de Ejecución

1. lógica  
2. motor  
3. frontend  
4. automatización  
5. validación  
6. inteligencia  

---

# 🧠 Definición Final

❌ No es una app de listas  
❌ No es un recordatorio  

👉 Es:

**Un sistema que decide por ti dónde comprar, en el momento correcto, con el menor esfuerzo posible**
