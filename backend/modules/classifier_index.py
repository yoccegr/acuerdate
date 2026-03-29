import logging
import re
import unicodedata
from types import MappingProxyType
from typing import Mapping

from models.internal import Product

logger = logging.getLogger(__name__)

IndexEntry = Mapping[str, str]


class ClassifierIndex:
    """
    Índice de búsqueda construido a partir del diccionario de productos.

    Se construye una sola vez en el arranque del servicio y permanece
    inmutable durante toda la vida del proceso.

    Estructura:
        normalized_key -> {"norm": str, "category": str, "match_type": str}
    """

    def __init__(self, products: list[Product]) -> None:
        raw_index = self._build(products)
        self._index: MappingProxyType[str, IndexEntry] = MappingProxyType(raw_index)
        logger.info("ClassifierIndex construido: %d claves", len(self._index))

    @property
    def index(self) -> MappingProxyType[str, IndexEntry]:
        return self._index

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, key: object) -> bool:
        return key in self._index

    def __getitem__(self, key: str) -> IndexEntry:
        return self._index[key]

    def keys(self):
        return self._index.keys()

    def _build(self, products: list[Product]) -> dict[str, IndexEntry]:
        index: dict[str, IndexEntry] = {}

        for product in products:
            entries: list[tuple[str, str]] = [
                (product.norm, "norm"),
                *((syn, "synonym") for syn in product.synonyms),
            ]

            for text, match_type in entries:
                key = normalize(text)

                if not key:
                    logger.warning(
                        "Clave vacía tras normalizar '%s' en norm='%s' — ignorada",
                        text,
                        product.norm,
                    )
                    continue

                if key in index:
                    existing = index[key]
                    logger.warning(
                        "COLISIÓN en índice: clave='%s' | ganador='%s' (%s) | perdedor='%s' (%s) — se conserva el ganador",
                        key,
                        existing["norm"],
                        existing["match_type"],
                        product.norm,
                        match_type,
                    )
                    continue

                # Cada entry también se protege como read-only.
                index[key] = MappingProxyType(
                    {
                        "norm": product.norm,
                        "category": product.category,
                        "match_type": match_type,
                    }
                )

        return index


def normalize(text: str) -> str:
    """
    Normaliza texto para comparación en el índice:
      1. minúsculas
      2. elimina acentos y diacríticos
      3. elimina puntuación (conserva letras, dígitos y espacios)
      4. colapsa espacios múltiples
      5. trim
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r" +", " ", text).strip()
    return text
