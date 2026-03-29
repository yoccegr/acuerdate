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
#
# Cada entrada define los parámetros que se envían a Nearby Search.
# "type" es el tipo de lugar de Google; "keyword" refina dentro de ese tipo.
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

_NEARBY_SEARCH_URL = (
    "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
)

# Número máximo de alternativas incluidas en la salida (especificación §3.2)
_MAX_ALTERNATIVES = 2


# ---------------------------------------------------------------------------
# Función principal
#
# api_key y timeout se reciben como parámetros explícitos.
# No se leen desde settings aquí — esa lectura ocurre en RequestHandler,
# donde settings ya fue inicializado durante el arranque del servicio.
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
      1. Buscar tipo(s) primary en radio configurado.
      2. Si sin resultados y existe fallback distinto → buscar fallback.
      3. Si aún sin resultados → duplicar radio y repetir (una sola vez).
      4. Buscar optional de forma independiente.
      5. Construir MapsResult.

    Parámetros:
      profile       — salida de CoverageEngine.
      location      — coordenadas del usuario en el momento del request.
      radius_meters — radio inicial de búsqueda en metros.
      api_key       — Google Maps API key, leída de settings en RequestHandler.
      timeout       — segundos antes de lanzar MapsTimeoutError.
    """
    status = _new_status(radius_meters)

    primary_type  = profile.primary[0]  if profile.primary  else None
    fallback_type = profile.fallback[0] if profile.fallback else None

    recommendation: StoreResult | None = None
    alternatives:   list[StoreResult]  = []
    radius_used = radius_meters

    # ── Paso 1: buscar primary ───────────────────────────────────────────────
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

    # ── Paso 2: fallback si primary falló ────────────────────────────────────
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

    # ── Paso 4: buscar optional (siempre, independiente del primary) ─────────
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
    Consulta Google Maps Nearby Search para un tipo de tienda.
    Devuelve lista de StoreResult ordenada por distancia al usuario.
    Lista vacía si no hay resultados o si ocurre un error no crítico.
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
    valid.sort(key=lambda s: s.distance_m)

    logger.info(
        "Maps '%s' radio=%dm → %d resultado(s)",
        store_type, radius, len(valid),
    )
    return valid


# ---------------------------------------------------------------------------
# Selección de la más cercana y separación de alternativas
# ---------------------------------------------------------------------------

def select_nearest(
    stores:   list[StoreResult],
    location: UserLocation,  # noqa: ARG001 — firma pública según especificación
) -> StoreResult | None:
    """
    Devuelve la tienda más cercana de la lista.
    La lista ya viene ordenada por distancia desde search_by_type.
    location se mantiene en la firma por contrato de la especificación.
    """
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
    Distancia aproximada en metros entre dos coordenadas geográficas.

    Usa la fórmula de Haversine: precisa para distancias cortas (< 50 km),
    tiene en cuenta la curvatura de la Tierra.

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
    """
    Devuelve los parámetros de Places API para un tipo de tienda interno.
    Lanza KeyError si el tipo no está en STORE_TYPE_MAP.
    """
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
    Convierte un resultado crudo de la Places API en un StoreResult.
    Devuelve None si faltan campos obligatorios o la tienda está cerrada.
    """
    try:
        geometry  = place["geometry"]["location"]
        store_lat = geometry["lat"]
        store_lng = geometry["lng"]
    except (KeyError, TypeError):
        logger.warning(
            "Resultado de Maps sin geometry.location — ignorado: %s",
            place.get("name", "sin nombre"),
        )
        return None

    store_location = UserLocation(lat=store_lat, lng=store_lng)
    distance       = approximate_distance(user_location, store_location)

    opening_hours = place.get("opening_hours", {})
    open_now      = opening_hours.get("open_now")
    hours_unknown = open_now is None

    # Si la API confirma explícitamente que está cerrada, no se incluye
    if open_now is False:
        return None

    return StoreResult(
        place_id=      place.get("place_id", ""),
        name=          place.get("name", ""),
        address=       place.get("vicinity", ""),
        lat=           store_lat,
        lng=           store_lng,
        distance_m=    distance,
        hours_unknown= hours_unknown,
        type=          store_type,
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
    logger.error(
        "HTTP %d consultando Maps para tipo='%s': %s",
        code, store_type, error,
    )


def _handle_api_status(api_status: str, store_type: str) -> None:
    if api_status == "REQUEST_DENIED":
        raise MapsAuthError(
            f"Google Maps rechazó el request (REQUEST_DENIED) "
            f"para tipo='{store_type}'. Verificar API key y permisos."
        )
    if api_status == "OVER_QUERY_LIMIT":
        raise MapsQuotaError("Cuota de Google Maps API excedida (OVER_QUERY_LIMIT).")
    logger.warning(
        "Maps API status inesperado '%s' para tipo='%s' — tratado como sin resultados",
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
