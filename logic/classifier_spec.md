# Clasificador de productos — Acuérdate! (Fase 1)

## Descripción
El clasificador recibe texto libre por ítem, lo resuelve contra el diccionario, y devuelve:
- norm
- category
- match_type

El motor de cobertura opera sobre categorías, no sobre texto libre.

---

## Flujo general

Para cada ítem:

1. Normalizar texto
2. Buscar coincidencia exacta (norm o synonym)
3. Si no hay → coincidencia parcial por tokens
4. Si no hay → fallback a "otros"
5. Devolver resultado estructurado

---

## Inicialización

El índice se construye UNA vez al iniciar el sistema.

```pseudo
MODULE_INDEX = NULL

FUNCTION classifier_init(products):
  IF MODULE_INDEX NOT NULL:
    LOG warning
    RETURN

  MODULE_INDEX = build_index(products)
```

---

## Construcción del índice

```pseudo
FUNCTION build_index(products):
  index = {}

  FOR product IN products:
    entries = [(product.norm, "norm")] + [(s, "synonym") FOR s IN product.synonyms]

    FOR (text, match_type) IN entries:
      key = normalize(text)

      IF key IN index:
        LOG "colisión"
        CONTINUE

      index[key] = {
        norm: product.norm,
        category: product.category,
        match_type: match_type
      }

  RETURN index
```

---

## Normalización

```pseudo
FUNCTION normalize(text):
  text = lowercase(text)
  text = remove_accents(text)
  text = remove_punctuation(text)
  text = collapse_spaces(text)
  text = trim(text)
  RETURN text
```

---

## Tokenización

```pseudo
FUNCTION tokenize(text):
  RETURN split(text, " ")
```

---

## Clasificación de ítem

```pseudo
FUNCTION classify_item(raw_input, index):
  key = normalize(raw_input)

  IF key IN index:
    RETURN { ... }

  input_tokens = tokenize(key)

  best_match = NULL
  best_score = 0

  FOR known_key IN index:
    known_tokens = tokenize(known_key)

    IF all_tokens_present(known_tokens, input_tokens):
      score = length(known_tokens)
      IF score > best_score:
        best_match = known_key
        best_score = score

  IF best_match NOT NULL:
    RETURN { ... }

  RETURN {
    input: raw_input,
    norm: NULL,
    category: "otros",
    match_type: "unknown"
  }
```

---

## Clasificación de lista

```pseudo
FUNCTION classify_list(items):
  IF MODULE_INDEX IS NULL:
    ERROR "init primero"

  results = []
  unknown = []

  FOR item IN items:
    r = classify_item(item, MODULE_INDEX)
    results.append(r)

    IF r.match_type == "unknown":
      unknown.append(item)

  RETURN {
    items: results,
    unrecognized: unknown
  }
```

---

## Reglas clave

- Exact match siempre tiene prioridad
- Partial match usa tokens (NO substring)
- Se prioriza la coincidencia más específica (más tokens)
- Unknown → categoría "otros"
- El flujo nunca se detiene por errores

---

## Notas importantes

- El índice NO se reconstruye por request
- Las colisiones se loguean, no se sobreescriben
- El diccionario es la única fuente de verdad
