"""
Pruebas unitarias para maps_client.
No requieren .env ni API key real — toda llamada HTTP está mockeada.
Ejecutar desde backend/ con: pytest tests/test_maps_client.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from models.internal import SearchProfile, UserLocation, MapsResult, StoreResult
from modules.maps_client import (
    approximate_distance,
    translate_type,
    select_nearest,
    search_by_type,
    search,
    _parse_place,
    _passes_hard_filters,
    _rank_candidates,
    _quality_score,
    MapsAuthError,
    MapsQuotaError,
    MapsTimeoutError,
    STORE_TYPE_MAP,
    _ACCEPTED_GOOGLE_TYPES,
    _DISTANCE_TIE_THRESHOLD_M,
    _MIN_RATINGS_ESTABLISHED,
)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SANTIAGO  = UserLocation(lat=-33.4489, lng=-70.6693)
FAKE_KEY  = "test_api_key_no_real"
TIMEOUT   = 10
THRESHOLD = _DISTANCE_TIE_THRESHOLD_M


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _place(
    name:               str       = "Tienda Test",
    lat:                float     = -33.4400,
    lng:                float     = -70.6600,
    open_now:           bool|None = True,
    place_id:           str       = "ChIJ_test_001",
    vicinity:           str|None  = "Calle Test 123",
    types:              list[str] = None,
    business_status:    str       = "OPERATIONAL",
    user_ratings_total: int       = 50,
) -> dict:
    result: dict = {
        "place_id":           place_id,
        "name":               name,
        "vicinity":           vicinity,
        "geometry":           {"location": {"lat": lat, "lng": lng}},
        "types":              types or ["supermarket", "grocery_or_supermarket", "establishment"],
        "business_status":    business_status,
        "user_ratings_total": user_ratings_total,
    }
    if open_now is not None:
        result["opening_hours"] = {"open_now": open_now}
    return result


def _place_farmacia(**kw) -> dict:
    return _place(types=["pharmacy", "drugstore", "establishment"], **kw)


def _place_botilleria(**kw) -> dict:
    return _place(types=["liquor_store", "store", "establishment"], **kw)


def _place_panaderia(**kw) -> dict:
    return _place(types=["bakery", "food", "establishment"], **kw)


def _api_response(places: list[dict], status: str = "OK") -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"status": status, "results": places}
    return mock


def _profile(
    primary:  list[str]|None = None,
    fallback: list[str]|None = None,
    optional: list[str]|None = None,
) -> SearchProfile:
    return SearchProfile(
        primary=primary   or ["supermercado"],
        fallback=fallback or [],
        optional=optional or [],
        rule_applied="supermarket_with_optional",
    )


def _store(
    distance_m:         int  = 300,
    user_ratings_total: int  = 50,
    has_address:        bool = True,   # siempre explícito — sin default en StoreResult
    name:               str  = "Tienda",
    store_type:         str  = "supermercado",
) -> StoreResult:
    """
    Helper que construye un StoreResult para tests.
    has_address siempre se pasa explícitamente — StoreResult no tiene default
    para ese campo y cualquier omisión en producción sería un error.
    """
    return StoreResult(
        place_id=           f"id_{name}",
        name=               name,
        address=            "Calle Test 123" if has_address else "",
        lat=                -33.4400,
        lng=                -70.6600,
        distance_m=         distance_m,
        hours_unknown=      False,
        type=               store_type,
        has_address=        has_address,
        user_ratings_total= user_ratings_total,
    )


# ---------------------------------------------------------------------------
# StoreResult — has_address es obligatorio
# ---------------------------------------------------------------------------

class TestStoreResultHasAddress:
    def test_has_address_es_obligatorio(self):
        """
        StoreResult sin has_address debe fallar en validación.
        Garantiza que el campo no puede ser omitido silenciosamente.
        """
        import pydantic
        with pytest.raises((TypeError, pydantic.ValidationError)):
            StoreResult(
                place_id="x", name="y", address="", lat=0.0, lng=0.0,
                distance_m=0, hours_unknown=False, type="supermercado",
                # has_address deliberadamente omitido
            )

    def test_has_address_true_con_direccion(self):
        s = _store(has_address=True)
        assert s.has_address is True

    def test_has_address_false_sin_direccion(self):
        s = _store(has_address=False)
        assert s.has_address is False
        assert s.address == ""

    def test_user_ratings_total_tiene_default_cero(self):
        """user_ratings_total sí tiene default — es aceptable porque es métrica opcional."""
        s = StoreResult(
            place_id="x", name="y", address="Av. Test 1", lat=0.0, lng=0.0,
            distance_m=100, hours_unknown=False, type="supermercado",
            has_address=True,
        )
        assert s.user_ratings_total == 0


# ---------------------------------------------------------------------------
# _ACCEPTED_GOOGLE_TYPES
# ---------------------------------------------------------------------------

class TestAcceptedGoogleTypes:
    def test_todos_tienen_filtro_explicito(self):
        for t in ["supermercado", "farmacia", "botilleria", "panaderia"]:
            assert t in _ACCEPTED_GOOGLE_TYPES
            assert len(_ACCEPTED_GOOGLE_TYPES[t]) > 0, f"Set vacío para '{t}'"

    def test_supermercado_no_incluye_food(self):
        assert "food" not in _ACCEPTED_GOOGLE_TYPES["supermercado"]

    def test_farmacia_no_incluye_health(self):
        assert "health" not in _ACCEPTED_GOOGLE_TYPES["farmacia"]

    def test_supermercado_incluye_grocery(self):
        assert "grocery_or_supermarket" in _ACCEPTED_GOOGLE_TYPES["supermercado"]

    def test_farmacia_incluye_drugstore(self):
        assert "drugstore" in _ACCEPTED_GOOGLE_TYPES["farmacia"]


# ---------------------------------------------------------------------------
# _passes_hard_filters
# ---------------------------------------------------------------------------

class TestPassesHardFilters:
    def test_lugar_valido(self):
        ok, _ = _passes_hard_filters(_place(), "supermercado")
        assert ok is True

    def test_sin_place_id(self):
        ok, r = _passes_hard_filters(_place(place_id=""), "supermercado")
        assert not ok and "place_id" in r

    def test_nombre_vacio(self):
        ok, r = _passes_hard_filters(_place(name=""), "supermercado")
        assert not ok and "nombre" in r

    def test_nombre_solo_espacios(self):
        ok, r = _passes_hard_filters(_place(name="   "), "supermercado")
        assert not ok and "nombre" in r

    def test_closed_permanently(self):
        ok, r = _passes_hard_filters(
            _place(business_status="CLOSED_PERMANENTLY"), "supermercado"
        )
        assert not ok and "CLOSED_PERMANENTLY" in r

    def test_cerrado_ahora(self):
        ok, r = _passes_hard_filters(_place(open_now=False), "supermercado")
        assert not ok and "cerrado" in r

    def test_sin_open_now_pasa(self):
        ok, _ = _passes_hard_filters(_place(open_now=None), "supermercado")
        assert ok is True

    def test_supermercado_rechaza_gasolinera(self):
        ok, r = _passes_hard_filters(
            _place(types=["gas_station"]), "supermercado"
        )
        assert not ok and "incompatibles" in r

    def test_supermercado_rechaza_food_solo(self):
        ok, r = _passes_hard_filters(
            _place(types=["food", "restaurant"]), "supermercado"
        )
        assert not ok and "incompatibles" in r

    def test_farmacia_rechaza_health_solo(self):
        ok, r = _passes_hard_filters(
            _place(types=["health", "spa"]), "farmacia"
        )
        assert not ok and "incompatibles" in r

    def test_farmacia_acepta_pharmacy(self):
        ok, _ = _passes_hard_filters(_place_farmacia(types=["pharmacy"]), "farmacia")
        assert ok is True

    def test_farmacia_acepta_drugstore(self):
        ok, _ = _passes_hard_filters(_place_farmacia(types=["drugstore"]), "farmacia")
        assert ok is True

    def test_botilleria_acepta_liquor_store(self):
        ok, _ = _passes_hard_filters(
            _place_botilleria(types=["liquor_store"]), "botilleria"
        )
        assert ok is True

    def test_botilleria_rechaza_restaurante(self):
        ok, r = _passes_hard_filters(
            _place(types=["restaurant"]), "botilleria"
        )
        assert not ok and "incompatibles" in r

    def test_panaderia_acepta_bakery(self):
        ok, _ = _passes_hard_filters(_place_panaderia(types=["bakery"]), "panaderia")
        assert ok is True

    def test_panaderia_rechaza_ferreteria(self):
        ok, r = _passes_hard_filters(
            _place(types=["hardware_store"]), "panaderia"
        )
        assert not ok and "incompatibles" in r


# ---------------------------------------------------------------------------
# _parse_place — has_address derivado, nunca asumido
# ---------------------------------------------------------------------------

class TestParsePlace:
    def test_vicinity_presente_has_address_true(self):
        store = _parse_place(_place(vicinity="Av. Test 123"), "supermercado", SANTIAGO)
        assert store is not None
        assert store.has_address is True
        assert store.address == "Av. Test 123"

    def test_vicinity_none_has_address_false(self):
        store = _parse_place(_place(vicinity=None), "supermercado", SANTIAGO)
        assert store is not None
        assert store.has_address is False
        assert store.address == ""

    def test_vicinity_vacia_has_address_false(self):
        store = _parse_place(_place(vicinity=""), "supermercado", SANTIAGO)
        assert store.has_address is False

    def test_vicinity_solo_espacios_has_address_false(self):
        store = _parse_place(_place(vicinity="   "), "supermercado", SANTIAGO)
        assert store.has_address is False
        assert store.address == ""

    def test_user_ratings_capturado(self):
        store = _parse_place(_place(user_ratings_total=123), "supermercado", SANTIAGO)
        assert store.user_ratings_total == 123

    def test_user_ratings_none_normalizado_a_cero(self):
        raw = _place()
        raw["user_ratings_total"] = None
        assert _parse_place(raw, "supermercado", SANTIAGO).user_ratings_total == 0

    def test_user_ratings_ausente_produce_cero(self):
        raw = _place()
        raw.pop("user_ratings_total", None)
        assert _parse_place(raw, "supermercado", SANTIAGO).user_ratings_total == 0

    def test_nombre_vacio_produce_none(self):
        assert _parse_place(_place(name=""), "supermercado", SANTIAGO) is None

    def test_closed_permanently_produce_none(self):
        assert _parse_place(
            _place(business_status="CLOSED_PERMANENTLY"), "supermercado", SANTIAGO
        ) is None

    def test_tipo_incompatible_produce_none(self):
        assert _parse_place(
            _place(types=["restaurant"]), "botilleria", SANTIAGO
        ) is None

    def test_sin_geometry_produce_none(self):
        raw = _place()
        raw.pop("geometry")
        assert _parse_place(raw, "supermercado", SANTIAGO) is None

    def test_hours_unknown_sin_open_now(self):
        assert _parse_place(_place(open_now=None), "supermercado", SANTIAGO).hours_unknown is True

    def test_hours_known_con_open_now_true(self):
        assert _parse_place(_place(open_now=True), "supermercado", SANTIAGO).hours_unknown is False


# ---------------------------------------------------------------------------
# _quality_score — no contiene distance_m
# ---------------------------------------------------------------------------

class TestQualityScore:
    def test_con_direccion_mejor_que_sin_direccion(self):
        con = _store(has_address=True,  user_ratings_total=5)
        sin = _store(has_address=False, user_ratings_total=5)
        assert _quality_score(con) < _quality_score(sin)

    def test_establecido_mejor_que_nuevo(self):
        est  = _store(has_address=True, user_ratings_total=_MIN_RATINGS_ESTABLISHED)
        new_ = _store(has_address=True, user_ratings_total=_MIN_RATINGS_ESTABLISHED - 1)
        assert _quality_score(est) < _quality_score(new_)

    def test_mas_resenas_mejor_entre_establecidos(self):
        a = _store(has_address=True, user_ratings_total=10)
        b = _store(has_address=True, user_ratings_total=200)
        assert _quality_score(b) < _quality_score(a)

    def test_no_contiene_distancia(self):
        cerca = _store(distance_m=50,  has_address=True, user_ratings_total=10)
        lejos = _store(distance_m=500, has_address=True, user_ratings_total=10)
        assert _quality_score(cerca) == _quality_score(lejos)


# ---------------------------------------------------------------------------
# _rank_candidates
# ---------------------------------------------------------------------------

class TestRankCandidates:
    def test_un_solo_candidato(self):
        stores = [_store()]
        assert _rank_candidates(stores) == stores

    def test_vacio(self):
        assert _rank_candidates([]) == []

    def test_fuera_umbral_distancia_gana(self):
        cerca = _store(distance_m=100, has_address=False, user_ratings_total=0, name="Cerca")
        lejos = _store(distance_m=100 + THRESHOLD + 1, has_address=True, user_ratings_total=500, name="Lejos")
        assert _rank_candidates([cerca, lejos])[0].name == "Cerca"

    def test_dentro_umbral_direccion_gana_sobre_sin_direccion(self):
        sin_dir = _store(distance_m=100, has_address=False, user_ratings_total=200, name="SinDir")
        con_dir = _store(distance_m=100 + THRESHOLD, has_address=True, user_ratings_total=1, name="ConDir")
        assert _rank_candidates([sin_dir, con_dir])[0].name == "ConDir"

    def test_dentro_umbral_establecido_gana_sobre_nuevo(self):
        nuevo = _store(
            distance_m=50, has_address=True,
            user_ratings_total=_MIN_RATINGS_ESTABLISHED - 1, name="Nuevo",
        )
        establecido = _store(
            distance_m=50 + THRESHOLD, has_address=True,
            user_ratings_total=100, name="Establecido",
        )
        assert _rank_candidates([nuevo, establecido])[0].name == "Establecido"

    def test_dentro_umbral_mas_resenas_gana_entre_establecidos(self):
        pocas  = _store(distance_m=50, has_address=True, user_ratings_total=10,  name="Pocas")
        muchas = _store(distance_m=50 + THRESHOLD, has_address=True, user_ratings_total=300, name="Muchas")
        assert _rank_candidates([pocas, muchas])[0].name == "Muchas"

    def test_un_metro_fuera_umbral_distancia_gana(self):
        cerca = _store(distance_m=100, has_address=False, user_ratings_total=0, name="Cerca")
        casi  = _store(distance_m=100 + THRESHOLD + 1, has_address=True, user_ratings_total=500, name="Casi")
        assert _rank_candidates([cerca, casi])[0].name == "Cerca"

    def test_tres_candidatos_orden_por_calidad(self):
        sin_dir       = _store(distance_m=80,  has_address=False, user_ratings_total=500, name="SinDir")
        con_dir_nuevo = _store(distance_m=100, has_address=True,  user_ratings_total=1,   name="ConDirNuevo")
        con_dir_est   = _store(distance_m=120, has_address=True,  user_ratings_total=100, name="ConDirEst")
        ranked = _rank_candidates([sin_dir, con_dir_nuevo, con_dir_est])
        assert ranked[0].name == "ConDirEst"
        assert ranked[1].name == "ConDirNuevo"
        assert ranked[2].name == "SinDir"

    def test_fuera_de_zona_ordenados_por_distancia(self):
        base   = 100
        cerca  = _store(distance_m=base, has_address=False, user_ratings_total=0, name="Cerca")
        lejos1 = _store(distance_m=base + THRESHOLD + 100, has_address=True, user_ratings_total=500, name="Lejos1")
        lejos2 = _store(distance_m=base + THRESHOLD + 300, has_address=False, user_ratings_total=0, name="Lejos2")
        ranked = _rank_candidates([lejos2, lejos1, cerca])
        assert ranked[1].name == "Lejos1"
        assert ranked[2].name == "Lejos2"


# ---------------------------------------------------------------------------
# approximate_distance
# ---------------------------------------------------------------------------

class TestApproximateDistance:
    def test_mismo_punto(self):
        assert approximate_distance(SANTIAGO, SANTIAGO) == 0

    def test_distancia_conocida(self):
        loc_b = UserLocation(lat=-33.4489, lng=-70.6593)
        assert 800 < approximate_distance(SANTIAGO, loc_b) < 1200

    def test_simetrica(self):
        loc_b = UserLocation(lat=-33.4600, lng=-70.6800)
        assert approximate_distance(SANTIAGO, loc_b) == approximate_distance(loc_b, SANTIAGO)

    def test_entero(self):
        assert isinstance(approximate_distance(SANTIAGO, UserLocation(lat=-33.46, lng=-70.68)), int)


# ---------------------------------------------------------------------------
# translate_type
# ---------------------------------------------------------------------------

class TestTranslateType:
    def test_supermercado(self):
        assert translate_type("supermercado")["type"] == "supermarket"

    def test_farmacia(self):
        assert translate_type("farmacia")["type"] == "pharmacy"

    def test_botilleria_tiene_keyword(self):
        assert "keyword" in translate_type("botilleria")

    def test_panaderia_tiene_keyword(self):
        assert "keyword" in translate_type("panaderia")

    def test_desconocido(self):
        with pytest.raises(KeyError, match="desconocido"):
            translate_type("ferreteria")


# ---------------------------------------------------------------------------
# search_by_type
# ---------------------------------------------------------------------------

class TestSearchByType:
    @patch("modules.maps_client.httpx.get")
    def test_zero_results(self, mock_get):
        mock_get.return_value = _api_response([], status="ZERO_RESULTS")
        assert search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT) == []

    @patch("modules.maps_client.httpx.get")
    def test_excluye_cerradas(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="Abierta", open_now=True),
            _place(name="Cerrada", open_now=False, place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "Abierta" in names and "Cerrada" not in names

    @patch("modules.maps_client.httpx.get")
    def test_excluye_closed_permanently(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="OK"),
            _place(name="Cerrado", business_status="CLOSED_PERMANENTLY", place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "OK" in names and "Cerrado" not in names

    @patch("modules.maps_client.httpx.get")
    def test_excluye_gasolinera_en_supermercado(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="Jumbo", types=["supermarket"]),
            _place(name="Shell", types=["gas_station"], place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "Jumbo" in names and "Shell" not in names

    @patch("modules.maps_client.httpx.get")
    def test_excluye_food_sin_supermarket(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name="Super", types=["supermarket"]),
            _place(name="Resto", types=["food", "restaurant"], place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "Super" in names and "Resto" not in names

    @patch("modules.maps_client.httpx.get")
    def test_excluye_health_sin_pharmacy_en_farmacia(self, mock_get):
        mock_get.return_value = _api_response([
            _place_farmacia(name="Farmacia"),
            _place(name="Spa", types=["spa", "health"], place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "Farmacia" in names and "Spa" not in names

    @patch("modules.maps_client.httpx.get")
    def test_excluye_tipo_incompatible_botilleria(self, mock_get):
        mock_get.return_value = _api_response([
            _place_botilleria(name="Botillería"),
            _place(name="Restaurante", types=["restaurant"], place_id="ChIJ_002"),
        ])
        names = [s.name for s in search_by_type("botilleria", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)]
        assert "Botillería" in names and "Restaurante" not in names

    @patch("modules.maps_client.httpx.get")
    def test_vicinity_none_has_address_false(self, mock_get):
        mock_get.return_value = _api_response([_place(vicinity=None)])
        stores = search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert stores[0].has_address is False

    @patch("modules.maps_client.httpx.get")
    def test_vicinity_presente_has_address_true(self, mock_get):
        mock_get.return_value = _api_response([_place(vicinity="Av. Test 123")])
        stores = search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert stores[0].has_address is True

    @patch("modules.maps_client.httpx.get")
    def test_captura_ratings(self, mock_get):
        mock_get.return_value = _api_response([_place(user_ratings_total=77)])
        assert search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)[0].user_ratings_total == 77

    @patch("modules.maps_client.httpx.get")
    def test_todos_invalidos_devuelve_vacio(self, mock_get):
        mock_get.return_value = _api_response([
            _place(name=""),
            _place(name="X", place_id=""),
        ])
        assert search_by_type("supermercado", SANTIAGO, 1500, FAKE_KEY, TIMEOUT) == []

    @patch("modules.maps_client.httpx.get")
    def test_hours_unknown_sin_open_now(self, mock_get):
        mock_get.return_value = _api_response([_place(open_now=None)])
        assert search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)[0].hours_unknown is True

    @patch("modules.maps_client.httpx.get")
    def test_request_denied(self, mock_get):
        mock_get.return_value = _api_response([], status="REQUEST_DENIED")
        with pytest.raises(MapsAuthError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_quota(self, mock_get):
        mock_get.return_value = _api_response([], status="OVER_QUERY_LIMIT")
        with pytest.raises(MapsQuotaError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_timeout(self, mock_get):
        import httpx as _httpx
        mock_get.side_effect = _httpx.TimeoutException("t")
        with pytest.raises(MapsTimeoutError):
            search_by_type("farmacia", SANTIAGO, 1500, FAKE_KEY, TIMEOUT)

    @patch("modules.maps_client.httpx.get")
    def test_api_key_en_params(self, mock_get):
        mock_get.return_value = _api_response([])
        search_by_type("farmacia", SANTIAGO, 1500, "mi_key", TIMEOUT)
        assert mock_get.call_args.kwargs["params"]["key"] == "mi_key"


# ---------------------------------------------------------------------------
# search — flujo completo
# ---------------------------------------------------------------------------

class TestSearch:
    @patch("modules.maps_client.search_by_type")
    def test_primary_encontrado(self, mock_sbt):
        mock_sbt.return_value = [_store(name="Farmacia Cruz", store_type="farmacia")]
        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Farmacia Cruz"
        assert result.search_status.primary_found is True

    @patch("modules.maps_client.search_by_type")
    def test_fallback_cuando_primary_vacio(self, mock_sbt):
        mock_sbt.side_effect = [[], [_store(name="Jumbo", store_type="supermercado")]]
        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.type == "supermercado"
        assert result.search_status.fallback_used  is True
        assert result.search_status.fallback_found is True

    @patch("modules.maps_client.search_by_type")
    def test_expansion_radio(self, mock_sbt):
        mock_sbt.side_effect = [[], [_store(name="Lider")]]
        result = search(
            _profile(primary=["supermercado"], fallback=[]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Lider"
        assert result.search_status.radius_expanded is True
        assert result.search_status.radius_used_m  == 3000

    @patch("modules.maps_client.search_by_type")
    def test_sin_resultados(self, mock_sbt):
        mock_sbt.return_value = []
        result = search(_profile(), SANTIAGO, 1500, FAKE_KEY, TIMEOUT)
        assert result.recommendation is None
        assert result.search_status.radius_expanded is True

    @patch("modules.maps_client.search_by_type")
    def test_optional_separado(self, mock_sbt):
        mock_sbt.side_effect = [
            [_store(name="Lider",      store_type="supermercado")],
            [_store(name="Botillería", store_type="botilleria")],
        ]
        result = search(
            _profile(primary=["supermercado"], optional=["botilleria"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert result.recommendation.name == "Lider"
        assert result.optional[0].name == "Botillería"

    @patch("modules.maps_client.search_by_type")
    def test_alternativas_maximo_dos(self, mock_sbt):
        mock_sbt.return_value = [
            _store(name=f"F{i}", distance_m=100 + i * 10, has_address=True)
            for i in range(5)
        ]
        result = search(
            _profile(primary=["farmacia"], fallback=["supermercado"]),
            SANTIAGO, 1500, FAKE_KEY, TIMEOUT,
        )
        assert len(result.alternatives) <= 2

    @patch("modules.maps_client.search_by_type")
    def test_location_available_siempre_true(self, mock_sbt):
        mock_sbt.return_value = []
        assert search(_profile(), SANTIAGO, 1500, FAKE_KEY, TIMEOUT).search_status.location_available is True

    @patch("modules.maps_client.search_by_type")
    def test_no_requiere_env(self, mock_sbt):
        mock_sbt.return_value = []
        assert isinstance(search(_profile(), SANTIAGO, 1500, "key", TIMEOUT), MapsResult)
