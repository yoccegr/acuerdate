import logging
from typing import NamedTuple

from config.settings import Settings
from models.internal import ClassificationResult, ClassifiedItem, SearchProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tipos de tienda especializadas — orden de evaluación estable
# ---------------------------------------------------------------------------

_SPECIALISTS: list[str] = ["farmacia", "botilleria", "panaderia"]

# ---------------------------------------------------------------------------
# Mapa de cobertura por categoría
#
# Botillería y farmacia cubren por categoría: sus categorías asignadas
# son coherentes con lo que realmente venden.
#
# Panadería usa filtro por norm: su categoría asignada ("alimentos") es
# demasiado amplia. Una panadería no resuelve arroz, atún ni aceite.
# Solo se activa para ítems cuyo norm esté explícitamente en su lista.
# ---------------------------------------------------------------------------

_COVERAGE_BY_CATEGORY: dict[str, set[str]] = {
    "supermercado": {
        "alimentos", "bebidas", "limpieza", "cuidado_personal",
        "hogar", "mascotas", "bebe", "snacks", "otros",
    },
    "botilleria": {"bebidas"},
    "farmacia": {"cuidado_personal", "bebe"},
    # panaderia no tiene entrada aquí — usa filtro por norm (ver abajo)
}

_PANADERIA_COMPATIBLE_NORMS: frozenset[str] = frozenset({
    "pan",
    "pan de molde",
})


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def evaluate(
    result: ClassificationResult,
    settings: Settings,
) -> SearchProfile:
    """
    Decide qué tipo(s) de tienda recomendar dado el resultado del clasificador.

    Aplica las tres reglas en orden. La primera que se activa produce
    el SearchProfile y termina la evaluación.

    No hace I/O. No llama APIs externas. No tiene estado propio.
    """
    total = len(result.items)

    if total == 0:
        logger.warning("evaluate() recibió lista vacía — aplicando fallback absoluto")
        return _rule_fallback()

    coverages = _compute_all_coverages(result.items, total)

    _log_coverages(coverages, total, settings)

    # ── Regla 1: especialista clara ──────────────────────────────────────────
    specialist = _find_specialist(
        coverages=coverages,
        total=total,
        threshold=settings.specialist_coverage_threshold,
        max_items=settings.specialist_max_items,
    )
    if specialist is not None:
        logger.info(
            "Regla 1 activada: specialist_clear → primary=%s (cobertura=%.2f, total=%d)",
            specialist,
            coverages[specialist].coverage,
            total,
        )
        return SearchProfile(
            primary=[specialist],
            fallback=["supermercado"],
            optional=[],
            rule_applied="specialist_clear",
        )

    # ── Regla 2: supermercado con opcionales ─────────────────────────────────
    optionals = _find_optionals(
        coverages=coverages,
        threshold=settings.optional_coverage_threshold,
    )
    logger.info(
        "Regla 2 activada: supermarket_with_optional → optional=%s",
        optionals,
    )
    return SearchProfile(
        primary=["supermercado"],
        fallback=[],
        optional=optionals,
        rule_applied="supermarket_with_optional",
    )


# ---------------------------------------------------------------------------
# Cálculo de cobertura
# ---------------------------------------------------------------------------

class _CoverageEntry(NamedTuple):
    items_covered: int
    coverage: float  # fracción entre 0.0 y 1.0


def _compute_all_coverages(
    items: list[ClassifiedItem],
    total: int,
) -> dict[str, _CoverageEntry]:
    """
    Calcula cobertura para cada tipo de tienda.
    Supermercado siempre cubre todo — se calcula igual para consistencia
    de logging y para que el contrato sea uniforme.
    """
    all_types = _SPECIALISTS + ["supermercado"]
    return {
        store_type: _coverage_for_type(store_type, items, total)
        for store_type in all_types
    }


def _coverage_for_type(
    store_type: str,
    items: list[ClassifiedItem],
    total: int,
) -> _CoverageEntry:
    """
    Devuelve la cobertura de un tipo de tienda sobre la lista.

    Panadería usa filtro por norm en lugar de filtro por categoría.
    El resto usa el mapa de categorías.
    """
    if store_type == "panaderia":
        covered = _items_covered_panaderia(items)
    else:
        covered = _items_covered_by_category(store_type, items)

    return _CoverageEntry(
        items_covered=covered,
        coverage=covered / total,
    )


def _items_covered_by_category(
    store_type: str,
    items: list[ClassifiedItem],
) -> int:
    valid_categories = _COVERAGE_BY_CATEGORY.get(store_type, set())
    return sum(1 for item in items if item.category in valid_categories)


def _items_covered_panaderia(items: list[ClassifiedItem]) -> int:
    """
    Panadería solo cuenta ítems cuyo norm esté en la lista de norms
    compatibles. Ítems unknown (norm=None) nunca se cuentan.
    """
    return sum(
        1 for item in items
        if item.norm is not None and item.norm in _PANADERIA_COMPATIBLE_NORMS
    )


# ---------------------------------------------------------------------------
# Reglas de decisión
# ---------------------------------------------------------------------------

def _find_specialist(
    coverages: dict[str, _CoverageEntry],
    total: int,
    threshold: float,
    max_items: int,
) -> str | None:
    """
    Regla 1: devuelve el tipo especialista que supera el umbral de cobertura
    con una lista suficientemente corta.

    Si más de un especialista supera el umbral, gana el de mayor cobertura.
    En empate de cobertura, gana el de mayor items_covered absolutos.
    Si persiste el empate, se conserva el primero en orden de _SPECIALISTS.
    """
    if total > max_items:
        return None

    candidates = [
        store_type for store_type in _SPECIALISTS
        if coverages[store_type].coverage >= threshold
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    return max(
        candidates,
        key=lambda t: (coverages[t].coverage, coverages[t].items_covered),
    )


def _find_optionals(
    coverages: dict[str, _CoverageEntry],
    threshold: float,
) -> list[str]:
    """
    Regla 2: especialistas con cobertura suficiente para aparecer como
    parada complementaria opcional. El supermercado nunca es opcional
    porque ya es el primary en Regla 2.
    """
    return [
        store_type for store_type in _SPECIALISTS
        if coverages[store_type].coverage >= threshold
    ]


def _rule_fallback() -> SearchProfile:
    """Regla 3: fallback absoluto para casos extremos (lista vacía, etc.)."""
    return SearchProfile(
        primary=["supermercado"],
        fallback=[],
        optional=[],
        rule_applied="fallback",
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log_coverages(
    coverages: dict[str, _CoverageEntry],
    total: int,
    settings: Settings,
) -> None:
    lines = [f"Cobertura sobre {total} ítem(s):"]
    for store_type, entry in coverages.items():
        lines.append(
            f"  {store_type:<14} {entry.items_covered}/{total} "
            f"({entry.coverage:.0%})"
        )
    lines.append(
        f"  umbrales → specialist={settings.specialist_coverage_threshold:.0%} "
        f"max_items={settings.specialist_max_items} "
        f"optional={settings.optional_coverage_threshold:.0%}"
    )
    logger.debug("\n".join(lines))
