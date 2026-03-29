"""
Pruebas unitarias para coverage_engine.
Ejecutar desde backend/ con: pytest tests/test_coverage_engine.py -v
"""
from models.internal import ClassificationResult, ClassifiedItem
from modules.coverage_engine import evaluate


class _MockSettings:
    specialist_coverage_threshold: float = 0.85
    specialist_max_items: int = 6
    optional_coverage_threshold: float = 0.50


SETTINGS = _MockSettings()


def _item(category: str, norm: str | None = "mock") -> ClassifiedItem:
    return ClassifiedItem(
        input=norm or "unknown_input",
        norm=norm,
        category=category,
        match_type="norm" if norm else "unknown",
    )


def _pan_item() -> ClassifiedItem:
    return ClassifiedItem(
        input="pan",
        norm="pan",
        category="alimentos",
        match_type="norm",
    )


def _result(items: list[ClassifiedItem]) -> ClassificationResult:
    unrecognized = [i.input for i in items if i.match_type == "unknown"]
    return ClassificationResult(items=items, unrecognized=unrecognized)


class TestRule1SpecialistClear:
    def test_botilleria_lista_corta_100pct(self):
        items = [_item("bebidas")] * 4
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["botilleria"]
        assert profile.fallback == ["supermercado"]
        assert profile.optional == []
        assert profile.rule_applied == "specialist_clear"

    def test_farmacia_lista_corta_100pct(self):
        items = [_item("cuidado_personal")] * 2 + [_item("bebe")] * 2
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["farmacia"]
        assert profile.fallback == ["supermercado"]
        assert profile.rule_applied == "specialist_clear"

    def test_panaderia_activa_con_norms_compatibles(self):
        items = [_pan_item()] * 3
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["panaderia"]
        assert profile.rule_applied == "specialist_clear"

    def test_especialista_exactamente_en_umbral(self):
        items = [_item("bebidas")] * 5
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["botilleria"]
        assert profile.rule_applied == "specialist_clear"

    def test_especialista_exactamente_en_max_items(self):
        items = [_item("bebidas")] * 6
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["botilleria"]
        assert profile.rule_applied == "specialist_clear"


class TestRule1NotActivated:
    def test_lista_larga_bebidas_va_a_supermercado(self):
        items = [_item("bebidas")] * 8
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]
        assert profile.rule_applied == "supermarket_with_optional"

    def test_cobertura_insuficiente_va_a_supermercado(self):
        items = [_item("bebidas")] * 3 + [_item("alimentos")] * 3
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]

    def test_panaderia_no_activa_con_alimentos_genericos(self):
        items = [
            ClassifiedItem(input="leche", norm="leche", category="alimentos", match_type="norm"),
            ClassifiedItem(input="arroz", norm="arroz", category="alimentos", match_type="norm"),
            ClassifiedItem(input="harina", norm="harina", category="alimentos", match_type="norm"),
        ]
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]
        assert "panaderia" not in profile.optional


class TestRule2SupermarketWithOptional:
    def test_lista_mixta_sin_opcionales(self):
        items = [_item("alimentos")] * 2 + [_item("limpieza")] * 2 + [_item("cuidado_personal")] * 2
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]
        assert profile.optional == []
        assert profile.rule_applied == "supermarket_with_optional"

    def test_botilleria_aparece_como_opcional(self):
        items = [_item("bebidas")] * 4 + [_item("alimentos")] * 4
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]
        assert "botilleria" in profile.optional

    def test_farmacia_aparece_como_opcional(self):
        items = [_item("cuidado_personal")] * 4 + [_item("alimentos")] * 4
        profile = evaluate(_result(items), SETTINGS)
        assert "farmacia" in profile.optional


class TestRule3Fallback:
    def test_lista_vacia(self):
        profile = evaluate(_result([]), SETTINGS)
        assert profile.primary == ["supermercado"]
        assert profile.fallback == []
        assert profile.optional == []
        assert profile.rule_applied == "fallback"


class TestUnknownItems:
    def test_lista_puro_unknown_va_a_supermercado(self):
        items = [
            ClassifiedItem(input="tahini", norm=None, category="otros", match_type="unknown"),
            ClassifiedItem(input="harissa", norm=None, category="otros", match_type="unknown"),
        ]
        profile = evaluate(_result(items), SETTINGS)
        assert profile.primary == ["supermercado"]
