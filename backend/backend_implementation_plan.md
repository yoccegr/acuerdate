# Backend Implementation Plan — Acuérdate! (MVP)

## Descripción
Guía paso a paso para implementar el backend siguiendo la arquitectura definida.

---

## Stack tecnológico
- Python
- FastAPI
- Pydantic
- httpx
- python-dotenv
- pytest

---

## Estructura del backend

backend/
├── main.py
├── .env
├── .env.example
├── requirements.txt
├── data/
│   └── products.json
├── config/
│   └── settings.py
├── models/
│   ├── request.py
│   ├── response.py
│   └── internal.py
├── modules/
│   ├── dictionary_loader.py
│   ├── classifier_index.py
│   ├── classifier.py
│   ├── coverage_engine.py
│   └── maps_client.py
├── api/
│   └── routes.py
└── tests/

---

## Orden de implementación

### Etapa 1
- settings.py
- modelos internos

### Etapa 2
- dictionary_loader

### Etapa 3
- classifier_index + classifier

### Etapa 4
- coverage_engine

### Etapa 5
- maps_client

### Etapa 6
- API + endpoint

### Etapa 7
- pruebas

---

## Principios

- cada módulo tiene responsabilidad única
- no mezclar lógica entre capas
- probar cada etapa antes de seguir
- no agregar features fuera del MVP

---

## Objetivo

Construir un backend modular, testeable y listo para integrarse con frontend Flutter.
