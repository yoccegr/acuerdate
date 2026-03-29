from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Diccionario
# ---------------------------------------------------------------------------

class Product(BaseModel):
    """Representa una entrada del diccionario products.json."""

    norm:     str
    category: str
    synonyms: list[str]


# ---------------------------------------------------------------------------
# Clasificador
# ---------------------------------------------------------------------------

MatchType = Literal["norm", "synonym", "partial", "unknown"]


class ClassifiedItem(BaseModel):
    """Resultado de clasificar un ítem de texto libre."""

    input:      str
    norm:       str | None
    category:   str
    match_type: MatchType


class ClassificationResult(BaseModel):
    """Salida completa del clasificador para una lista."""

    items:        list[ClassifiedItem]
    unrecognized: list[str]


# ---------------------------------------------------------------------------
# Motor de cobertura
# ---------------------------------------------------------------------------

StoreType = Literal["supermercado", "botilleria", "panaderia", "farmacia"]

RuleApplied = Literal[
    "specialist_clear",
    "supermarket_with_optional",
    "fallback",
]


class SearchProfile(BaseModel):
    """
    Perfil de recomendación producido por CoverageEngine.
    Entrada directa de MapsClient.
    """

    primary:      list[StoreType]
    fallback:     list[StoreType]
    optional:     list[StoreType]
    rule_applied: RuleApplied


# ---------------------------------------------------------------------------
# Ubicación del usuario
# ---------------------------------------------------------------------------

class UserLocation(BaseModel):
    """Coordenadas geográficas del usuario en el momento del request."""

    lat: float
    lng: float

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError(f"Latitud fuera de rango válido: {v}")
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError(f"Longitud fuera de rango válido: {v}")
        return v


# ---------------------------------------------------------------------------
# Maps client
# ---------------------------------------------------------------------------

class StoreResult(BaseModel):
    """Tienda concreta devuelta por Google Maps."""

    place_id:      str
    name:          str
    address:       str
    lat:           float
    lng:           float
    distance_m:    int
    hours_unknown: bool
    type:          StoreType


class SearchStatus(BaseModel):
    """Estado detallado del proceso de búsqueda en Maps."""

    primary_found:      bool | None
    fallback_used:      bool | None
    fallback_found:     bool | None
    radius_expanded:    bool
    radius_used_m:      int | None
    location_available: bool


class MapsResult(BaseModel):
    """Salida completa de MapsClient. Entrada directa de RequestHandler."""

    recommendation: StoreResult | None
    alternatives:   list[StoreResult]
    optional:       list[StoreResult]
    search_status:  SearchStatus
