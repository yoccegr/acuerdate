"""
Pruebas unitarias para ClassifierIndex y classify_list.
Ejecutar desde backend/ con: pytest tests/test_classifier.py -v
"""
import pytest

from models.internal import Product
from modules.classifier_index import ClassifierIndex, normalize
from modules.classifier import classify_list, classify_item


@pytest.fixture
def sample_products() -> list[Product]:
    return [
        Product(norm="leche", category="alimentos", synonyms=["leche entera", "leche descremada"]),
        Product(norm="yogur", category="alimentos", synonyms=["yogurt", "yoghurt", "yogur griego"]),
        Product(norm="sal", category="alimentos", synonyms=["sal de mesa", "sal fina"]),
        Product(norm="salsa de soya", category="alimentos", synonyms=["salsa soja", "salsa de soja"]),
        Product(norm="shampoo", category="cuidado_personal", synonyms=["champu", "shampoo cabello seco", "shampoo cabello graso"]),
        Product(norm="atun", category="alimentos", synonyms=["atun en lata", "atun al agua"]),
        Product(norm="pan", category="alimentos", synonyms=["pan de molde", "pan blanco", "pan integral"]),
        Product(norm="cotonitos", category="cuidado_personal", synonyms=["cotonetes", "bastoncillos", "qtips"]),
    ]


@pytest.fixture
def index(sample_products) -> ClassifierIndex:
    return ClassifierIndex(sample_products)


def test_normalize():
    assert normalize("Atún") == "atun"
    assert normalize("q-tips") == "qtips"
    assert normalize("  leche  ") == "leche"


def test_match_norm(index):
    result = classify_item("leche", index)
    assert result.norm == "leche"
    assert result.match_type == "norm"


def test_match_synonym(index):
    result = classify_item("yogurt", index)
    assert result.norm == "yogur"
    assert result.match_type == "synonym"


def test_match_partial(index):
    result = classify_item("shampoo cabello graso con keratina", index)
    assert result.norm == "shampoo"
    assert result.match_type == "partial"


def test_unknown(index):
    result = classify_item("tahini", index)
    assert result.norm is None
    assert result.category == "otros"
    assert result.match_type == "unknown"


def test_sal_no_es_salsa(index):
    result = classify_item("salsa de tomate casera", index)
    assert result.norm != "sal"


def test_index_top_level_inmutable(index):
    with pytest.raises((TypeError, AttributeError)):
        index.index["nueva_clave"] = {}  # type: ignore[index]


def test_index_nested_entry_inmutable(index):
    with pytest.raises(TypeError):
        index["leche"]["norm"] = "otra"  # type: ignore[index]


def test_classify_list(index):
    result = classify_list(["leche", "yogurt", "tahini", "atún"], index)
    assert len(result.items) == 4
    assert len(result.unrecognized) == 1
