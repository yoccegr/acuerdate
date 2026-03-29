import json
import logging
from pathlib import Path

from pydantic import ValidationError

from models.internal import Product

logger = logging.getLogger(__name__)

# Categorías válidas del MVP. Definidas y congeladas en Fase 0.
_VALID_CATEGORIES: frozenset[str] = frozenset({
    "alimentos",
    "bebidas",
    "limpieza",
    "cuidado_personal",
    "hogar",
    "mascotas",
    "bebe",
    "snacks",
    "otros",
})


def load_products(path: str) -> list[Product]:
    """
    Lee products.json desde disco y devuelve una lista de objetos Product.

    Valida:
      - que el archivo existe y es legible
      - que el contenido es JSON válido
      - que la estructura raíz contiene la clave "products"
      - que cada producto tiene norm, category y synonyms bien formados
      - que cada category pertenece al conjunto definido en Fase 0

    Raises:
      FileNotFoundError  — el archivo no existe en la ruta indicada
      ValueError         — JSON inválido, estructura incorrecta, o productos mal formados
    """
    resolved = _resolve_path(path)
    raw = _read_file(resolved)
    data = _parse_json(raw, resolved)
    products = _extract_products(data, resolved)
    return products


# ---------------------------------------------------------------------------
# Helpers privados — cada uno tiene una sola responsabilidad
# ---------------------------------------------------------------------------

def _resolve_path(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(
            f"Diccionario no encontrado: '{path}'\n"
            f"Ruta resuelta: {resolved}"
        )
    if not resolved.is_file():
        raise FileNotFoundError(
            f"La ruta existe pero no es un archivo: {resolved}"
        )
    return resolved


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(
            f"No se pudo leer el archivo '{path}': {e}"
        ) from e


def _parse_json(raw: str, path: Path) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"El archivo '{path}' contiene JSON inválido.\n"
            f"Detalle: {e}"
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"El archivo '{path}' debe contener un objeto JSON en la raíz, "
            f"se encontró: {type(data).__name__}"
        )
    return data


def _extract_products(data: dict, path: Path) -> list[Product]:
    if "products" not in data:
        raise ValueError(
            f"El archivo '{path}' no contiene la clave 'products'."
        )

    raw_products = data["products"]

    if not isinstance(raw_products, list):
        raise ValueError(
            f"'products' debe ser una lista, "
            f"se encontró: {type(raw_products).__name__}"
        )

    if len(raw_products) == 0:
        raise ValueError(
            f"El archivo '{path}' contiene una lista 'products' vacía. "
            f"El clasificador no puede operar sin diccionario."
        )

    products: list[Product] = []
    errors: list[str] = []

    for i, raw in enumerate(raw_products):
        result = _parse_single_product(raw, index=i)
        if isinstance(result, str):
            errors.append(result)
        else:
            products.append(result)

    if errors:
        error_lines = "\n".join(f"  [{e}]" for e in errors)
        raise ValueError(
            f"Se encontraron {len(errors)} producto(s) mal formados "
            f"en '{path}':\n{error_lines}"
        )

    logger.info(
        "Diccionario cargado: %d productos desde '%s'",
        len(products),
        path,
    )
    return products


def _parse_single_product(raw: object, index: int) -> Product | str:
    """
    Intenta construir un Product desde un elemento crudo del JSON.
    Devuelve el Product si es válido, o un string de error si no lo es.
    Acumular errores (en lugar de fallar en el primero) permite reportar
    todos los productos mal formados en una sola ejecución.
    """
    if not isinstance(raw, dict):
        return (
            f"índice {index}: se esperaba un objeto, "
            f"se encontró {type(raw).__name__}"
        )

    try:
        product = Product.model_validate(raw)
    except ValidationError as e:
        # Pydantic ya produce un mensaje claro con los campos que fallaron
        return f"índice {index} (norm='{raw.get('norm', '?')}'): {e}"

    category_error = _validate_category(product, index)
    if category_error:
        return category_error

    return product


def _validate_category(product: Product, index: int) -> str | None:
    """
    Verifica que la categoría del producto pertenezca al conjunto definido
    en Fase 0. Pydantic valida la estructura del campo pero no su valor
    semántico — esa validación vive aquí.
    """
    if product.category not in _VALID_CATEGORIES:
        return (
            f"índice {index} (norm='{product.norm}'): "
            f"categoría desconocida '{product.category}'. "
            f"Válidas: {sorted(_VALID_CATEGORIES)}"
        )
    return None
