"""
Pruebas unitarias para maps_client.
No requieren .env ni API key real — toda llamada HTTP está mockeada.
Ejecutar desde backend/ con: pytest tests/test_maps_client.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from models.internal import SearchProfile, UserLocation, MapsResult
from modules.maps_client import (
    approximate_distance,
    translate_type,
    select_nearest,
    search_by_type,
    search,
    _parse_place,
    MapsAuthError,
    MapsQuotaError,
    MapsTimeoutError,
    STORE_TYPE_MAP,
)


# ---------------------------------------------------------------------------
# Constantes de test
# ---------------------------------------------------------------------------

SANTIAGO   = UserLocation(lat=-33.4489, lng=-70.6693)
FAKE_KEY   = "test_api_key_no_real"
TIMEOUT    = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _place(
    name:     str   = "Tienda Test",
    lat:      float = -33.4400,
    lng:      float = -70.6600,
    open_now: bool | None = True,
    place_id: str   = "ChIJ_test_001",
    vicinity: str   = "Calle Test 123",
) -> dict:
    """Resultado crudo simulando la respuesta de Places API."""
    result: dict = {
        "place_id": place_id,
        "name":     name,
        "vicinity": vicinity,
        "geometry": {"location": {"lat": lat, "lng": lng}},
    }
    if open_now is not None:
        result["opening_hours"] = {"open_now": open_now}
    return result


def _api_response(places: list[dict], status: str = "OK") -> MagicMock:
    """Mock de respuesta HTTP exitosa de Places API."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"status": status, "results": places}
    return mock


def _profile(
    primary:  list[str] | None = None,
    fallback: list[str] | None = None,
    optional: list[str] | None = None,
) -> SearchProfile:
    return SearchProfile(
        primary=primary   or ["supermercado"],
        fallback=fallback or [],
        optional=optional or [],
        rule_applied="supermarket_with_optional",
    )


def _store_from_place(raw: dict, store_type: str = "farmacia") -> object:
    """Convierte un dict crudo a StoreResult usando el helper interno."""
    return _parse_place(raw, store_type, SANTIAGO)


# ---------------------------------------------------------------------------
# approximate_distance
# ---------------------------------------------------------------------------

class TestApproximateDistance:
    def test_mismo_punto_es_cero(self):
        assert approximate_distance(SANTIAGO, SANTIAGO) == 0

    def test_distancia_conocida_aprox(self):
        # Dos puntos en Santiago separados ~1 km en longitud
        loc_a = UserLocation(lat=-33.4489, lng=-70.6693)
        loc_b = UserLocation(lat=-33.4489, lng=-70.6593)
        dist  = approximate_distance(loc_a, loc_b)
        assert 800 < dist < 1200, f"Distancia inesperada: {dist}m"

    def test_es_simetrica(self):
        loc_b = UserLocation(lat=-33.4600, lng=-70.6800)
        assert approximate_distance(SANTIAGO, loc_b) == approximate_distance(loc_b, SANTIAGO)

    def test_devuelve_entero(self):
        loc_b = UserLocation(lat=-33.4600, lng=-70.6800)
        assert isinstance(approximate_distance(SANTIAGO, loc_b), int)


# ---------------------------------------------------------------------------
# translate_type
# ---------------------------------------------------------------------------

class TestTranslateType:
    def test_supermercado(self):
        assert translate_type("supermercado")["type"] == "supermarket"

    def test_farmacia(self):
        assert translate_type("farmacia")["type"] == "pharmacy"

    def test_botilleria_tiene_keyword(self):
        params = translate_type("botilleria")
        assert "keyword" in params
        assert "botillería" in params["keyword"]

    def test_panaderia_tiene_keyword(self):
        assert "keyword" in translate_type("panaderia")

    def test_tipo_desconocido_lanza_key_error(self):
        with pytest.raises(KeyError, match="desconocido"):
            translate_type("ferreteria")

    def test_todos_los_tipos_validos(self):
        for t in ["supermercado", "botilleria", "panaderia", "farmacia"]:
            assert "type" in translate_type(t)


# ---------------------------------------------------------------------------
# select_nearest
# ---------------------------------------------------------------------------

class TestSelectNearest:
    def test_devuelve_mas_cercana(self):
        near = _store_from_place(_place(name="Cerca", lat=-33.4400, lng=-70.6600))
        far  = _store_from_place(_place(name="Lejos", lat=-33.5000, lng=-70.7000))
        assert select_nearest([near, far], SANTIAGO).name == "Cerca"

    def test_lista_vacia_devuelve_none(self):
        assert select_nearest([], SANTIAGO) is None

    def test_un_elemento(self):
        store = _store_from_place(_place())
        assert select_nearest([store], SANTIAGO).name == "Tienda Test"


# ---------------------------------------------------------------------------
# search_by_type — mockeando httpx.get
# ---------------------------------------------------------------------------

class TestSearchByType:
    @patch("modules.maps_client.httpx.get")
    def test_ordena_por_distancia(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="Lejos", lat=-33.5000, lng=-70.7000),
            _place(name="Cerca", lat=-33.4400, lng=-70.6600),
        ])
        stores = search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert stores[0].name == "Cerca"
        assert stores[0].distance_m < stores[1].distance_m

    @patch("modules.maps_client.httpx.get")
    def test_zero_results_devuelve_lista_vacia(self, mock_get):
        mock_get.return_value = _api_response([], status="ZERO_RESULTS")
        assert search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT) == []

    @patch("modules.maps_client.httpx.get")
    def test_excluye_tiendas_cerradas(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="Abierta", open_now=True),
            _place(name="Cerrada", open_now=False),
        ])
        stores = search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        names  = [s.name for s in stores]
        assert "Abierta" in names
        assert "Cerrada" not in names

    @patch("modules.maps_client.httpx.get")
    def test_hours_unknown_cuando_falta_open_now(self, mock_get):
        mock_get.return_value = _api_response([_place(open_now=None)])
        stores = search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert len(stores) == 1
        assert stores[0].hours_unknown is True

    @patch("modules.maps_client.httpx.get")
    def test_hours_known_cuando_open_now_true(self, mock_get):
        mock_get.return_value = _api_response([_place(open_now=True)])
        stores = search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert stores[0].hours_unknown is False

    @patch("modules.maps_client.httpx.get")
    def test_request_denied_lanza_maps_auth_error(self, mock_get):
        mock_get.return_value = _api_response([], status="REQUEST_DENIED")
        with pytest.raises(MapsAuthError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_over_query_limit_lanza_maps_quota_error(self, mock_get):
        mock_get.return_value = _api_response([], status="OVER_QUERY_LIMIT")
        with pytest.raises(MapsQuotaError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_timeout_lanza_maps_timeout_error(self, mock_get):
        import httpx as _httpx
        mock_get.side_effect = _httpx.TimeoutException("timeout")
        with pytest.raises(MapsTimeoutError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_api_key_se_pasa_en_params(self, mock_get):
        """La API key recibida como parámetro debe llegar al request HTTP."""
        mock_get.return_value = _api_response([])
        search_by_type("farmacia", SANTIAGO, 1500, "mi_key_especifica", TIMEOUT)
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if call_kwargs.args else {}
        # params puede venir como kwarg o en el dict de params
        all_params = mock_get.call_args.kwargs.get("params", {})
        assert all_params.get("key") == "mi_key_especifica"


# ---------------------------------------------------------------------------
# search — flujo completo mockeando search_by_type
# ---------------------------------------------------------------------------

class TestSearch:
    @patch("modules.maps_client.search_by_type")
    def test_primary_encontrado(self, mock_sbt):
        store = _store_from_place(_place(name="Farmacia Cruz"), "farmacia")
        mock_sbt.return_value = [store]

        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Farmacia Cruz"
        assert result.search_status.primary_found is True
        assert result.search_status.fallback_used is None

    @patch("modules.maps_client.search_by_type")
    def test_fallback_cuando_primary_sin_resultados(self, mock_sbt):
        super_store = _store_from_place(_place(name="Jumbo"), "supermercado")
        mock_sbt.side_effect = [[], [super_store]]

        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.type == "supermercado"
        assert result.search_status.primary_found  is False
        assert result.search_status.fallback_used  is True
        assert result.search_status.fallback_found is True

    @patch("modules.maps_client.search_by_type")
    def test_expansion_radio_sin_fallback(self, mock_sbt):
        store = _store_from_place(_place(name="Lider"), "supermercado")
        # primera llamada vacía (radio normal), segunda con resultado (expandido)
        mock_sbt.side_effect = [[], [store]]

        result = search(
            _profile(primary=["supermercado"], fallback=[]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Lider"
        assert result.search_status.radius_expanded is True
        assert result.search_status.radius_used_m  == 3000

    @patch("modules.maps_client.search_by_type")
    def test_sin_resultados_ni_con_radio_expandido(self, mock_sbt):
        mock_sbt.return_value = []

        result = search(
            _profile(primary=["supermercado"], fallback=[]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation is None
        assert result.search_status.radius_expanded is True

    @patch("modules.maps_client.search_by_type")
    def test_optional_separado_del_primary(self, mock_sbt):
        super_store = _store_from_place(_place(name="Lider"),               "supermercado")
        botil_store = _store_from_place(_place(name="Botillería El Ancla"), "botilleria")
        mock_sbt.side_effect = [[super_store], [botil_store]]

        result = search(
            _profile(primary=["supermercado"], fallback=[], optional=["botilleria"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Lider"
        assert len(result.optional) == 1
        assert result.optional[0].name == "Botillería El Ancla"

    @patch("modules.maps_client.search_by_type")
    def test_alternativas_maximo_dos(self, mock_sbt):
        stores = [
            _store_from_place(
                _place(name=f"Farmacia {i}", lat=-33.44 + i * 0.001),
                "farmacia",
            )
            for i in range(5)
        ]
        mock_sbt.return_value = stores

        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation is not None
        assert len(result.alternatives) <= 2

    @patch("modules.maps_client.search_by_type")
    def test_optional_vacio_cuando_sin_resultados(self, mock_sbt):
        super_store = _store_from_place(_place(name="Lider"), "supermercado")
        mock_sbt.side_effect = [[super_store], []]

        result = search(
            _profile(primary=["supermercado"], fallback=[], optional=["botilleria"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.optional == []

    @patch("modules.maps_client.search_by_type")
    def test_location_available_siempre_true(self, mock_sbt):
        mock_sbt.return_value = []
        result = search(_profile(), SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert result.search_status.location_available is True

    @patch("modules.maps_client.search_by_type")
    def test_no_requiere_settings_ni_env(self, mock_sbt):
        """
        Este test verifica el fix principal: el módulo se importa y ejecuta
        sin necesidad de .env ni GOOGLE_MAPS_API_KEY en el entorno.
        La key se recibe como parámetro explícito.
        """
        mock_sbt.return_value = []
        # Si llegamos aquí sin ImportError ni ValidationError, el fix funciona
        result = search(_profile(), SANTIAGO, 1500, "cualquier_string", TIMEOUT)
        assert isinstance(result, MapsResult)
