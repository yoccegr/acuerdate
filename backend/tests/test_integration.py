"""
Pruebas de integración del flujo completo.

Cubren el camino completo:
    request HTTP → clasificador → coverage engine → maps client → response

Autónomas: no requieren .env ni GOOGLE_MAPS_API_KEY real en el entorno.
Las variables de entorno mínimas se inyectan antes de importar la app.
Google Maps está mockeado en todos los tests.

Ejecutar desde backend/ con:
    pytest tests/test_integration.py -v
"""
import os
import importlib
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from models.internal import (
    MapsResult,
    SearchStatus,
    StoreResult,
)


# ---------------------------------------------------------------------------
# Inyección de entorno — debe ocurrir antes de importar main
#
# Settings() se evalúa cuando main.py se importa por primera vez.
# Parchear os.environ aquí, antes de cualquier import de main,
# garantiza que Settings() encuentre las variables necesarias sin .env.
# ---------------------------------------------------------------------------

_ENV_OVERRIDES = {
    "GOOGLE_MAPS_API_KEY":             "fake-key-for-tests",
    "SPECIALIST_COVERAGE_THRESHOLD":   "0.85",
    "SPECIALIST_MAX_ITEMS":            "6",
    "OPTIONAL_COVERAGE_THRESHOLD":     "0.50",
    "RADIUS_METERS":                   "1500",
    "PRODUCTS_PATH":                   "data/products.json",
    "REQUEST_TIMEOUT_SECONDS":         "10",
}

# Aplicar antes de que pytest importe cualquier fixture que toque main
for _key, _val in _ENV_OVERRIDES.items():
    os.environ.setdefault(_key, _val)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """
    TestClient con la app real.

    main se importa aquí, dentro del fixture, después de que os.environ
    ya tiene las variables necesarias. El lifespan carga el diccionario
    y construye el índice una sola vez para todos los tests del módulo.

    raise_server_exceptions=False hace que los errores 5xx devuelvan
    el response en lugar de re-lanzar la excepción en el test.
    """
    # Importación diferida: main no se importa hasta este punto,
    # momento en que os.environ ya está parcheado.
    import main as _main

    # Forzar recarga del módulo de settings para que lea el entorno
    # parcheado (necesario si settings fue importado antes en la sesión).
    import config.settings as _settings_module
    importlib.reload(_settings_module)
    _main.app.state  # acceso inocuo para confirmar que el atributo existe

    with TestClient(_main.app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(
    name:       str = "Tienda Test",
    store_type: str = "supermercado",
    distance_m: int = 450,
) -> StoreResult:
    return StoreResult(
        place_id=      f"ChIJ_{name.replace(' ', '_')}",
        name=          name,
        address=       "Calle Test 123, Santiago",
        lat=           -33.4400,
        lng=           -70.6600,
        distance_m=    distance_m,
        hours_unknown= False,
        type=          store_type,
    )


def _maps_ok(
    store:        StoreResult,
    alternatives: list[StoreResult] | None = None,
    optional:     list[StoreResult] | None = None,
) -> MapsResult:
    return MapsResult(
        recommendation=store,
        alternatives=alternatives or [],
        optional=optional or [],
        search_status=SearchStatus(
            primary_found=True,
            fallback_used=None,
            fallback_found=None,
            radius_expanded=False,
            radius_used_m=1500,
            location_available=True,
        ),
    )


def _maps_no_results() -> MapsResult:
    return MapsResult(
        recommendation=None,
        alternatives=[],
        optional=[],
        search_status=SearchStatus(
            primary_found=False,
            fallback_used=False,
            fallback_found=False,
            radius_expanded=True,
            radius_used_m=3000,
            location_available=True,
        ),
    )


LOCATION = {"lat": -33.4489, "lng": -70.6693}


def _body(items: list[str], location: dict = LOCATION) -> dict:
    return {"items": items, "location": location}


# ---------------------------------------------------------------------------
# 1. Caso exitoso — status: ok
# ---------------------------------------------------------------------------

class TestCasoExitoso:
    @patch("api.routes.search")
    def test_status_ok(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store("Jumbo", "supermercado"))

        r = client.post("/recommend", json=_body(["leche", "shampoo", "pañales"]))

        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    @patch("api.routes.search")
    def test_recommendation_no_nula(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store("Jumbo", "supermercado"))

        data = client.post("/recommend", json=_body(["leche", "shampoo", "pañales"])).json()

        assert data["maps"]["recommendation"] is not None
        assert data["maps"]["recommendation"]["store"]["name"] == "Jumbo"

    @patch("api.routes.search")
    def test_bloque_engine_presente(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post("/recommend", json=_body(["leche", "arroz"])).json()

        assert "engine" in data
        assert "classification_summary" in data["engine"]
        assert "rule_applied" in data["engine"]
        assert "params_used" in data["engine"]

    @patch("api.routes.search")
    def test_classification_summary_correcto(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post("/recommend", json=_body(["leche", "arroz", "shampoo"])).json()

        summary = data["engine"]["classification_summary"]
        assert summary["total_items"] == 3
        assert summary["unrecognized"] == 0

    @patch("api.routes.search")
    def test_bloque_maps_tiene_campos_clave(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store("Lider", "supermercado", 780))

        data = client.post("/recommend", json=_body(["leche"])).json()
        store = data["maps"]["recommendation"]["store"]

        assert store["name"] == "Lider"
        assert store["type"] == "supermercado"
        assert store["distance_m"] == 780
        assert "address" in store
        assert "hours_unknown" in store

    @patch("api.routes.search")
    def test_alternatives_en_response(self, mock_search, client):
        alt = _store("Santa Isabel", "supermercado", 920)
        mock_search.return_value = _maps_ok(
            _store("Lider", "supermercado"),
            alternatives=[alt],
        )

        data = client.post("/recommend", json=_body(["leche"])).json()
        alts = data["maps"]["recommendation"]["alternatives"]

        assert len(alts) == 1
        assert alts[0]["name"] == "Santa Isabel"

    @patch("api.routes.search")
    def test_optional_en_response(self, mock_search, client):
        opt = _store("Botillería El Ancla", "botilleria", 210)
        mock_search.return_value = _maps_ok(
            _store("Lider", "supermercado"),
            optional=[opt],
        )

        data = client.post("/recommend", json=_body(["leche", "cerveza"] * 4)).json()

        assert len(data["maps"]["optional"]) == 1
        assert data["maps"]["optional"][0]["type"] == "botilleria"

    @patch("api.routes.search")
    def test_search_status_en_response(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post("/recommend", json=_body(["leche"])).json()
        ss = data["maps"]["search_status"]

        assert ss["primary_found"] is True
        assert ss["location_available"] is True
        assert ss["radius_expanded"] is False

    @patch("api.routes.search")
    def test_params_used_refleja_configuracion(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post("/recommend", json=_body(["leche"])).json()
        params = data["engine"]["params_used"]

        assert "specialist_coverage_threshold" in params
        assert "specialist_max_items" in params
        assert "optional_coverage_threshold" in params

    @patch("api.routes.search")
    def test_lista_concentrada_bebidas_primary_botilleria(self, mock_search, client):
        """
        Lista corta y concentrada en bebidas → CoverageEngine activa Regla 1
        y Maps recibe SearchProfile con primary=botilleria.
        """
        mock_search.return_value = _maps_ok(_store("Botillería Génova", "botilleria", 210))

        data = client.post(
            "/recommend",
            json=_body(["cerveza", "vino", "agua con gas", "jugo"]),
        ).json()

        assert data["status"] == "ok"
        call_profile = mock_search.call_args.kwargs["profile"]
        assert call_profile.primary == ["botilleria"]

    @patch("api.routes.search")
    def test_maps_recibe_api_key_y_timeout(self, mock_search, client):
        """routes.py debe pasar api_key y timeout a maps_client.search."""
        mock_search.return_value = _maps_ok(_store())

        client.post("/recommend", json=_body(["leche"]))

        kwargs = mock_search.call_args.kwargs
        assert "api_key" in kwargs
        assert "timeout" in kwargs
        assert len(kwargs["api_key"]) > 0


# ---------------------------------------------------------------------------
# 2. Caso no_results
# ---------------------------------------------------------------------------

class TestNoResults:
    @patch("api.routes.search")
    def test_status_no_results(self, mock_search, client):
        mock_search.return_value = _maps_no_results()

        r = client.post("/recommend", json=_body(["leche", "arroz"]))

        assert r.status_code == 200
        assert r.json()["status"] == "no_results"

    @patch("api.routes.search")
    def test_recommendation_es_none(self, mock_search, client):
        mock_search.return_value = _maps_no_results()

        data = client.post("/recommend", json=_body(["leche"])).json()

        assert data["maps"]["recommendation"] is None

    @patch("api.routes.search")
    def test_engine_presente_aunque_sin_tienda(self, mock_search, client):
        """El bloque engine siempre se incluye — los módulos internos sí corrieron."""
        mock_search.return_value = _maps_no_results()

        data = client.post("/recommend", json=_body(["leche"])).json()

        assert data["engine"] is not None
        assert data["engine"]["classification_summary"]["total_items"] == 1

    @patch("api.routes.search")
    def test_search_status_refleja_expansion(self, mock_search, client):
        mock_search.return_value = _maps_no_results()

        data = client.post("/recommend", json=_body(["leche"])).json()
        ss = data["maps"]["search_status"]

        assert ss["primary_found"] is False
        assert ss["radius_expanded"] is True
        assert ss["radius_used_m"] == 3000

    @patch("api.routes.search")
    def test_optional_vacio_en_no_results(self, mock_search, client):
        mock_search.return_value = _maps_no_results()

        data = client.post("/recommend", json=_body(["leche"])).json()

        assert data["maps"]["optional"] == []


# ---------------------------------------------------------------------------
# 3. Request inválido → 400
# ---------------------------------------------------------------------------

class TestRequestInvalido:
    def test_items_vacios_400(self, client):
        r = client.post("/recommend", json=_body([]))

        assert r.status_code == 400
        assert r.json()["status"] == "error"

    def test_items_vacios_codigo_correcto(self, client):
        r = client.post("/recommend", json=_body([]))

        assert r.json()["error"]["code"] == "missing_items"

    def test_items_ausentes_400(self, client):
        r = client.post("/recommend", json={"location": LOCATION})

        assert r.status_code == 400

    def test_location_ausente_400(self, client):
        r = client.post("/recommend", json={"items": ["leche"]})

        assert r.status_code == 400
        assert r.json()["error"]["code"] == "missing_location"

    def test_lat_fuera_de_rango_400(self, client):
        r = client.post(
            "/recommend",
            json=_body(["leche"], location={"lat": 999, "lng": -70.6}),
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_coordinates"

    def test_lng_fuera_de_rango_400(self, client):
        r = client.post(
            "/recommend",
            json=_body(["leche"], location={"lat": -33.4, "lng": 999}),
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_coordinates"

    def test_item_solo_espacios_400(self, client):
        r = client.post("/recommend", json=_body(["   "]))

        assert r.status_code == 400

    def test_body_vacio_400(self, client):
        r = client.post("/recommend", json={})

        assert r.status_code == 400

    def test_respuesta_tiene_formato_del_sistema(self, client):
        """El 400 debe tener la estructura del sistema, no el formato de FastAPI."""
        data = client.post("/recommend", json=_body([])).json()

        assert "status" in data
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "detail" not in data


# ---------------------------------------------------------------------------
# 4. Ítems no reconocidos — flujo no se rompe
# ---------------------------------------------------------------------------

class TestItemsDesconocidos:
    @patch("api.routes.search")
    def test_unknown_no_rompe_el_flujo(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store("Jumbo", "supermercado"))

        r = client.post(
            "/recommend",
            json=_body(["tahini", "harissa", "za'atar"]),
        )

        assert r.status_code == 200

    @patch("api.routes.search")
    def test_unknown_contados_en_summary(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post(
            "/recommend",
            json=_body(["leche", "tahini", "harissa"]),
        ).json()

        summary = data["engine"]["classification_summary"]
        assert summary["total_items"] == 3
        assert summary["unrecognized"] == 2

    @patch("api.routes.search")
    def test_lista_puro_unknown_va_a_supermercado(self, mock_search, client):
        """Todos unknown → coverage engine activa fallback → primary=supermercado."""
        mock_search.return_value = _maps_ok(_store("Jumbo", "supermercado"))

        data = client.post(
            "/recommend",
            json=_body(["tahini", "za'atar", "harissa"]),
        ).json()

        call_profile = mock_search.call_args.kwargs["profile"]
        assert call_profile.primary == ["supermercado"]
        assert data["status"] == "ok"

    @patch("api.routes.search")
    def test_mezcla_conocidos_y_desconocidos(self, mock_search, client):
        mock_search.return_value = _maps_ok(_store())

        data = client.post(
            "/recommend",
            json=_body(["leche", "tahini", "arroz", "za'atar", "shampoo"]),
        ).json()

        summary = data["engine"]["classification_summary"]
        assert summary["total_items"] == 5
        assert summary["unrecognized"] == 2
        assert data["status"] == "ok"

    @patch("api.routes.search")
    def test_unknown_diluye_cobertura_especialista(self, mock_search, client):
        """
        1 bebida + 5 unknown → botillería 1/6 ≈ 0.17 < 0.85 → primary=supermercado.
        """
        mock_search.return_value = _maps_ok(_store())

        client.post(
            "/recommend",
            json=_body(["cerveza", "tahini", "harissa", "za'atar", "dukkah", "sumac"]),
        )

        call_profile = mock_search.call_args.kwargs["profile"]
        assert call_profile.primary == ["supermercado"]


# ---------------------------------------------------------------------------
# 5. Errores de Maps → 500 controlado
# ---------------------------------------------------------------------------

class TestErroresMaps:
    @patch("api.routes.search")
    def test_maps_timeout_devuelve_500(self, mock_search, client):
        from modules.maps_client import MapsTimeoutError
        mock_search.side_effect = MapsTimeoutError("timeout")

        r = client.post("/recommend", json=_body(["leche"]))

        assert r.status_code == 500
        assert r.json()["error"]["code"] == "maps_timeout"

    @patch("api.routes.search")
    def test_maps_auth_error_devuelve_500(self, mock_search, client):
        from modules.maps_client import MapsAuthError
        mock_search.side_effect = MapsAuthError("auth")

        r = client.post("/recommend", json=_body(["leche"]))

        assert r.status_code == 500
        assert r.json()["error"]["code"] == "maps_auth_error"

    @patch("api.routes.search")
    def test_maps_quota_devuelve_500(self, mock_search, client):
        from modules.maps_client import MapsQuotaError
        mock_search.side_effect = MapsQuotaError("quota")

        r = client.post("/recommend", json=_body(["leche"]))

        assert r.status_code == 500
        assert r.json()["error"]["code"] == "maps_quota_exceeded"

    @patch("api.routes.search")
    def test_error_500_tiene_formato_del_sistema(self, mock_search, client):
        from modules.maps_client import MapsUnavailableError
        mock_search.side_effect = MapsUnavailableError("unavailable")

        data = client.post("/recommend", json=_body(["leche"])).json()

        assert data["status"] == "error"
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "detail" not in data
