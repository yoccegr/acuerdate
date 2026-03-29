# Acuérdate! — Definición de producto

## Descripción

Acuérdate! es una app que permite al usuario escribir una lista de compras y automáticamente recomienda la mejor tienda cercana donde puede comprar la mayor parte o todo, minimizando esfuerzo y decisiones.

No es una app de listas. Es un sistema de decisión.

---

## Propuesta de valor

Decidir por el usuario dónde comprar, en el momento correcto, con la menor fricción posible.

---

## Principios del sistema

- El usuario solo escribe la lista
- La app decide por él
- Se prioriza menor cantidad de paradas
- El supermercado es fallback fuerte
- La app funciona sin historial
- La inteligencia (boletas) es opcional

---

## Componentes del sistema

### 1. Diccionario
Define:
- productos
- categorías
- sinónimos

Archivo:
`data/product_dictionary_v1.3.json`

---

### 2. Clasificador
Convierte texto libre en:
- norm
- category
- match_type

Archivo:
`logic/classifier_spec.md`

---

### 3. Cobertura y decisión
Determina:
- si conviene supermercado o especialista
- opcionales

Archivo:
`logic/coverage_spec.md`

---

## Flujo general

1. Usuario escribe lista
2. Clasificador interpreta items
3. Motor de cobertura decide tipo de tienda
4. (Siguiente fase) Google Maps encuentra tienda real
5. Se genera recomendación

---

## Estado actual

- Diccionario: definido
- Clasificador: definido
- Cobertura: definida
- Google Maps: pendiente
- Backend: pendiente
- Frontend: pendiente
