import logging
import math
from typing import Any

import httpx

from models.internal import (
    MapsResult,
    SearchProfile,
    SearchStatus,
    StoreResult,
    UserLocation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabla de traducción: tipo interno → parámetros de Google Maps Places API
# ---------------------------------------------------------------------------

STORE_TYPE_MAP: dict[str, dict[str, str]] = {
    "supermercado": {
        "type": "supermarket",
    },
    "botilleria": {
        "type":    "liquor_store",
        "keyword": "botillería",
    },
    "panaderia": {
        "type":    "bakery",
        "keyword": "panadería",
    },
    "farmacia": {
        "type": "pharmacy",
    },
}

# ---------------------------------------------------------------------------
# Tipos de Google aceptables por tipo de tienda interno
#
# Todos los tipos tienen filtro explícito. Un resultado se acepta si su
# lista `types` contiene al menos uno de los valores del set.
#
# supermercado: solo "supermarket" y "grocery_or_supermarket". "food" excluido
#   porque la API lo asigna a restaurantes, food trucks y mercados de barrio.
#
# farmacia: solo "pharmacy" y "drugstore". "health" excluido porque spas
#   y gimnasios también lo llevan.
# ---------------------------------------------------------------------------

_ACCEPTED_GOOGLE_TYPES: dict[str, set[str]] = {
    "supermercado": {
        "supermarket",
        "grocery_or_supermarket",
    },
    "farmacia": {
        "pharmacy",
        "drugstore",
    },
    "botilleria": {
        "liquor_store",
        "bar",
        "convenience_store",
    },
    "panaderia": {
        "bakery",
        "cafe",
        "food",
    },
}

_NEARBY_SEARCH_URL = (
    "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
)

_MAX_ALTERNATIVES = 2

# ---------------------------------------------------------------------------
# Parámetros de ranking — heurísticas iniciales del MVP, ajustables en Fase 4
#
# _DISTANCE_TIE_THRESHOLD_M: diferencia máxima en metros para que dos
#   candidatos compitan por calidad en lugar de por distancia.
#   100m ≈ un bloque en Santiago. Solo tiendas en el mismo entorno inmediato
#   entran en competencia de calidad.
#
# _MIN_RATINGS_ESTABLISHED: mínimo de reseñas para considerar un lugar
#   con historial suficiente. No implica que el lugar sea malo si está por
#   debajo — solo tiene menos evidencia disponible en Maps.
# ---------------------------------------------------------------------------

_DISTANCE_TIE_THRESHOLD_M = 100
_MIN_RATINGS_ESTABLISHED  = 5


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def search(
    profile:       SearchProfile,
    location:      UserLocation,
    radius_meters: int,
    api_key:       str,
    timeout:       int,
) -> MapsResult:
    """
    Traduce un SearchProfile en una tienda concreta usando la Places API.

    Flujo (congelado en especificación):
      1. Buscar tipo primary en radio configurado.
      2. Sin resultados y existe fallback distinto → buscar fallback.
      3. Aún sin resultados → duplicar radio, reintentar una sola vez.
      4. Buscar optional independientemente.
      5. Construir MapsResult.

    api_key y timeout se reciben como parámetros explícitos — no se leen
    desde settings aquí. Esa lectura ocurre en RequestHandler al arranque.
    """
    status = _new_status(radius_meters)

    primary_type  = profile.primary[0]  if profile.primary  else None
    fallback_type = profile.fallback[0] if profile.fallback else None

    recommendation: StoreResult | None = None
    alternatives:   list[StoreResult]  = []
    radius_used = radius_meters

    # ── Paso 1: primary ──────────────────────────────────────────────────────
    if primary_type:
        candidates = search_by_type(
            primary_type, location, radius_meters, api_key, timeout
        )
        if candidates:
            recommendation, alternatives = _split_candidates(candidates, location)
            status["primary_found"] = True
            status["radius_used_m"] = radius_meters
        else:
            status["primary_found"] = False
            logger.info(
                "Sin resultados para primary='%s' en radio=%dm",
                primary_type, radius_meters,
            )

    # ── Paso 2: fallback ─────────────────────────────────────────────────────
    if recommendation is None and fallback_type and fallback_type != primary_type:
        status["fallback_used"] = True
        candidates = search_by_type(
            fallback_type, location, radius_meters, api_key, timeout
        )
        if candidates:
            recommendation, alternatives = _split_candidates(candidates, location)
            status["fallback_found"] = True
            status["radius_used_m"]  = radius_meters
            logger.info(
                "Fallback activado: '%s' → encontrado en radio=%dm",
                fallback_type, radius_meters,
            )
        else:
            status["fallback_found"] = False
            logger.info(
                "Sin resultados para fallback='%s' en radio=%dm",
                fallback_type, radius_meters,
            )

    # ── Paso 3: expansión de radio (una sola vez) ────────────────────────────
    if recommendation is None:
        expanded_radius = radius_meters * 2
        retry_type = _type_to_retry(
            primary_type=primary_type,
            fallback_type=fallback_type,
            fallback_used=status["fallback_used"],
            fallback_found=status["fallback_found"],
        )
        if retry_type:
            logger.info(
                "Expandiendo radio: %dm → %dm para tipo='%s'",
                radius_meters, expanded_radius, retry_type,
            )
            candidates = search_by_type(
                retry_type, location, expanded_radius, api_key, timeout
            )
            status["radius_expanded"] = True
            status["radius_used_m"]   = expanded_radius
            radius_used = expanded_radius

            if candidates:
                recommendation, alternatives = _split_candidates(candidates, location)
                if retry_type == primary_type:
                    status["primary_found"] = True
                else:
                    status["fallback_found"] = True

    # ── Paso 4: optional ─────────────────────────────────────────────────────
    optional_results: list[StoreResult] = []
    for opt_type in profile.optional:
        candidates = search_by_type(opt_type, location, radius_used, api_key, timeout)
        if candidates:
            nearest = select_nearest(candidates, location)
            if nearest:
                optional_results.append(nearest)

    return MapsResult(
        recommendation=recommendation,
        alternatives=alternatives,
        optional=optional_results,
        search_status=SearchStatus(**status),
    )


# ---------------------------------------------------------------------------
# Búsqueda por tipo
# ---------------------------------------------------------------------------

def search_by_type(
    store_type: str,
    location:   UserLocation,
    radius:     int,
    api_key:    str,
    timeout:    int,
) -> list[StoreResult]:
    """
    Consulta Nearby Search, aplica filtros de calidad y rankea candidatos.
    Devuelve lista vacía si no hay resultados válidos.
    """
    params = _build_params(store_type, location, radius, api_key)

    try:
        response = httpx.get(
            _NEARBY_SEARCH_URL,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.TimeoutException as e:
        logger.error(
            "Timeout consultando Maps para tipo='%s' radio=%dm",
            store_type, radius,
        )
        raise MapsTimeoutError(
            f"Timeout al consultar Google Maps para tipo '{store_type}'"
        ) from e
    except httpx.HTTPStatusError as e:
        _handle_http_status_error(e, store_type)
        return []
    except httpx.RequestError as e:
        logger.error("Error de red consultando Maps: %s", e)
        raise MapsUnavailableError(
            f"No se pudo conectar con Google Maps: {e}"
        ) from e

    data       = response.json()
    api_status = data.get("status", "")

    if api_status == "ZERO_RESULTS":
        return []

    if api_status != "OK":
        _handle_api_status(api_status, store_type)
        return []

    places = data.get("results", [])
    stores = [_parse_place(place, store_type, location) for place in places]
    valid  = [s for s in stores if s is not None]

    if not valid:
        logger.info(
            "Maps '%s' radio=%dm → 0 válidos (de %d crudos)",
            store_type, radius, len(places),
        )
        return []

    ranked = _rank_candidates(valid)
    logger.info(
        "Maps '%s' radio=%dm → %d resultado(s) válido(s)",
        store_type, radius, len(ranked),
    )
    return ranked


# ---------------------------------------------------------------------------
# Filtros de calidad
# ---------------------------------------------------------------------------

def _passes_hard_filters(
    place:      dict[str, Any],
    store_type: str,
) -> tuple[bool, str]:
    """
    Filtros duros. Devuelve (pasa, motivo_de_rechazo).

      1. place_id ausente o vacío           → resultado inválido.
      2. name ausente o vacío               → no presentable al usuario.
      3. business_status CLOSED_PERMANENTLY → negocio inexistente.
      4. open_now: False explícito          → cerrado ahora.
      5. Tipo de Google incompatible        → contaminación por búsqueda.
    """
    if not place.get("place_id", "").strip():
        return False, "sin place_id"

    if not place.get("name", "").strip():
        return False, "nombre vacío"

    if place.get("business_status") == "CLOSED_PERMANENTLY":
        return False, "CLOSED_PERMANENTLY"

    if (place.get("opening_hours") or {}).get("open_now") is False:
        return False, "cerrado ahora"

    accepted = _ACCEPTED_GOOGLE_TYPES.get(store_type, set())
    if accepted:
        result_types = set(place.get("types", []))
        if not result_types.intersection(accepted):
            return False, f"tipos incompatibles: {result_types}"

    return True, ""


# ---------------------------------------------------------------------------
# Scoring y ranking
# ---------------------------------------------------------------------------

def _quality_score(store: StoreResult) -> tuple:
    """
    Tupla de desempate por calidad — no contiene distance_m.

    Prioridades dentro de la zona de empate (menor = mejor):
      1. Dirección útil (has_address).
      2. Reputación establecida (>= _MIN_RATINGS_ESTABLISHED reseñas).
      3. Volumen de reseñas.
    """
    established = store.user_ratings_total >= _MIN_RATINGS_ESTABLISHED
    return (
        0 if store.has_address else 1,
        0 if established else 1,
        -store.user_ratings_total,
    )


def _rank_candidates(stores: list[StoreResult]) -> list[StoreResult]:
    """
    Ordena candidatos con dos regímenes explícitos:

    Fuera de la zona de empate (diferencia > _DISTANCE_TIE_THRESHOLD_M
    respecto al más cercano): la distancia decide sola.

    Dentro de la zona de empate (diferencia <= _DISTANCE_TIE_THRESHOLD_M):
    la calidad decide — dirección > reputación > volumen de reseñas.
    La distancia no aparece en el score de estos candidatos.
    """
    if len(stores) <= 1:
        return list(stores)

    min_dist = min(s.distance_m for s in stores)

    in_tie:  list[StoreResult] = []
    outside: list[StoreResult] = []

    for s in stores:
        if s.distance_m - min_dist <= _DISTANCE_TIE_THRESHOLD_M:
            in_tie.append(s)
        else:
            outside.append(s)

    return sorted(in_tie, key=_quality_score) + sorted(outside, key=lambda s: s.distance_m)


# ---------------------------------------------------------------------------
# Selección y separación
# ---------------------------------------------------------------------------

def select_nearest(
    stores:   list[StoreResult],
    location: UserLocation,  # noqa: ARG001 — firma pública según especificación
) -> StoreResult | None:
    return stores[0] if stores else None


def _split_candidates(
    stores:   list[StoreResult],
    location: UserLocation,
) -> tuple[StoreResult | None, list[StoreResult]]:
    nearest      = select_nearest(stores, location)
    alternatives = stores[1: 1 + _MAX_ALTERNATIVES]
    return nearest, alternatives


# ---------------------------------------------------------------------------
# Distancia aproximada
# ---------------------------------------------------------------------------

def approximate_distance(loc1: UserLocation, loc2: UserLocation) -> int:
    """
    Distancia aproximada en metros usando Haversine.
    No es distancia de ruta real — no considera calles ni tráfico.
    """
    R    = 6_371_000
    lat1 = math.radians(loc1.lat)
    lat2 = math.radians(loc2.lat)
    dlat = math.radians(loc2.lat - loc1.lat)
    dlng = math.radians(loc2.lng - loc1.lng)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


# ---------------------------------------------------------------------------
# Traducción de tipo
# ---------------------------------------------------------------------------

def translate_type(store_type: str) -> dict[str, str]:
    if store_type not in STORE_TYPE_MAP:
        raise KeyError(
            f"Tipo de tienda desconocido: '{store_type}'. "
            f"Válidos: {list(STORE_TYPE_MAP.keys())}"
        )
    return STORE_TYPE_MAP[store_type]


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _build_params(
    store_type: str,
    location:   UserLocation,
    radius:     int,
    api_key:    str,
) -> dict[str, str]:
    return {
        "location": f"{location.lat},{location.lng}",
        "radius":   str(radius),
        "key":      api_key,
        **translate_type(store_type),
    }


def _parse_place(
    place:         dict[str, Any],
    store_type:    str,
    user_location: UserLocation,
) -> StoreResult | None:
    """
    Convierte un resultado crudo en StoreResult.
    Aplica filtros duros y deriva has_address desde vicinity.
    has_address es obligatorio en StoreResult — siempre se calcula aquí.
    """
    passes, reason = _passes_hard_filters(place, store_type)
    if not passes:
        logger.debug(
            "Lugar descartado (%s): '%s'",
            reason, place.get("name", "sin nombre"),
        )
        return None

    try:
        geometry  = place["geometry"]["location"]
        store_lat = geometry["lat"]
        store_lng = geometry["lng"]
    except (KeyError, TypeError):
        logger.warning(
            "Resultado sin geometry.location — ignorado: %s",
            place.get("name", "sin nombre"),
        )
        return None

    distance = approximate_distance(
        user_location,
        UserLocation(lat=store_lat, lng=store_lng),
    )

    raw_vicinity = place.get("vicinity") or ""
    address      = raw_vicinity.strip()
    has_address  = bool(address)  # derivado de los datos de la API, nunca asumido

    open_now      = (place.get("opening_hours") or {}).get("open_now")
    hours_unknown = open_now is None

    user_ratings_total = place.get("user_ratings_total") or 0

    return StoreResult(
        place_id=           place["place_id"],
        name=               place["name"].strip(),
        address=            address,
        lat=                store_lat,
        lng=                store_lng,
        distance_m=         distance,
        hours_unknown=      hours_unknown,
        type=               store_type,
        has_address=        has_address,
        user_ratings_total= user_ratings_total,
    )


def _type_to_retry(
    primary_type:   str | None,
    fallback_type:  str | None,
    fallback_used:  bool | None,
    fallback_found: bool | None,
) -> str | None:
    if not fallback_used:
        return primary_type
    if fallback_found is False:
        return fallback_type
    return None


def _handle_http_status_error(
    error:      httpx.HTTPStatusError,
    store_type: str,
) -> None:
    code = error.response.status_code
    if code == 403:
        raise MapsAuthError(
            "Google Maps API key inválida o sin permisos suficientes."
        ) from error
    if code == 429:
        raise MapsQuotaError("Cuota de Google Maps API excedida.") from error
    logger.error("HTTP %d consultando Maps tipo='%s': %s", code, store_type, error)


def _handle_api_status(api_status: str, store_type: str) -> None:
    if api_status == "REQUEST_DENIED":
        raise MapsAuthError(
            f"Google Maps rechazó el request (REQUEST_DENIED) "
            f"para tipo='{store_type}'. Verificar API key y permisos."
        )
    if api_status == "OVER_QUERY_LIMIT":
        raise MapsQuotaError("Cuota de Google Maps API excedida (OVER_QUERY_LIMIT).")
    logger.warning(
        "Maps API status inesperado '%s' tipo='%s' — sin resultados",
        api_status, store_type,
    )


def _new_status(radius_meters: int) -> dict:
    return {
        "primary_found":      None,
        "fallback_used":      None,
        "fallback_found":     None,
        "radius_expanded":    False,
        "radius_used_m":      radius_meters,
        "location_available": True,
    }


# ---------------------------------------------------------------------------
# Excepciones controladas
# ---------------------------------------------------------------------------

class MapsTimeoutError(Exception):
    """El request a Google Maps no respondió dentro del timeout configurado."""

class MapsAuthError(Exception):
    """API key inválida o sin permisos para usar Places API."""

class MapsQuotaError(Exception):
    """Cuota de la Google Maps API excedida."""

class MapsUnavailableError(Exception):
    """No se pudo establecer conexión con Google Maps."""
