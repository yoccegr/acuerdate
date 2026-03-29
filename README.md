# 🛒 Acuérdate!

Acuérdate! es una app que ayuda a decidir automáticamente **dónde comprar una lista de productos**, minimizando esfuerzo y cantidad de paradas.

---

## 🎯 Problema que resuelve

Las personas suelen:
- olvidar comprar cosas
- comprar en múltiples lugares innecesariamente
- tomar decisiones poco eficientes

Acuérdate! elimina esa fricción.

---

## 💡 Solución

El usuario escribe su lista y el sistema:

1. interpreta los productos (clasificador)
2. agrupa por categorías
3. decide el mejor tipo de tienda (cobertura)
4. busca una tienda cercana (Google Maps)
5. recomienda automáticamente dónde comprar

---

## 🧠 Cómo funciona (arquitectura)

Input usuario
   ↓
Clasificador
   ↓
Cobertura (decisión de tienda)
   ↓
Google Maps (tienda concreta)
   ↓
Recomendación final

---

## 📦 Estructura del proyecto

acuerdate/
├── docs/        → definición del producto y roadmap
├── data/        → diccionario de productos
├── logic/       → lógica del sistema
├── backend/     → implementación futura
├── frontend/    → app (Flutter)

---

## ⚙️ Estado actual

- ✔️ Diccionario de productos definido
- ✔️ Clasificador de texto implementado (especificación)
- ✔️ Lógica de cobertura definida
- ✔️ Integración con Google Maps definida
- 🚧 Backend en construcción
- 🚧 Frontend pendiente

---

## 🚀 Roadmap

- Fase 0: Definición del sistema ✔️
- Fase 1: Clasificador ✔️
- Fase 1.5: Cobertura ✔️
- Fase 2: Google Maps ✔️
- Fase 3: Backend completo (en progreso)
- Fase 4: Frontend
- Fase 5: Validación con usuarios
- Fase 6: Expansión del motor
- Fase 7: OCR + aprendizaje

---

## 🧠 Principios del producto

- El usuario no decide → el sistema decide
- Minimizar número de paradas
- Priorizar simplicidad
- Funcionar sin historial
- El supermercado es fallback natural

---

## 🎯 Objetivo final

Construir un sistema que:

Decida por ti dónde comprar, en el momento correcto, con el menor esfuerzo posible.

---

## 🛠️ Tecnologías (planificadas)

- Frontend: Flutter
- Backend: (por definir)
- Maps: Google Maps API
- OCR (futuro): Tesseract / APIs externas

---

## 👩‍💻 Autora

Proyecto desarrollado por Yocce González  
Ingeniera en Automatización & futura Data Scientist 🚀

---

## 📌 Estado del proyecto

En desarrollo activo — MVP en construcción
