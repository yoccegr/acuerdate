from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # --- Google Maps ---
    google_maps_api_key: str = Field(..., alias="GOOGLE_MAPS_API_KEY")

    # --- Parámetros operativos del motor de cobertura ---
    # Heurísticas iniciales del MVP. Ajustables en Fase 4 sin cambiar código.
    specialist_coverage_threshold: float = Field(
        default=0.85,
        alias="SPECIALIST_COVERAGE_THRESHOLD",
    )
    specialist_max_items: int = Field(
        default=6,
        alias="SPECIALIST_MAX_ITEMS",
    )
    optional_coverage_threshold: float = Field(
        default=0.50,
        alias="OPTIONAL_COVERAGE_THRESHOLD",
    )

    # --- Parámetros operativos de búsqueda en Maps ---
    # Valor inicial: 1500m. Ajustable en Fase 4.
    radius_meters: int = Field(
        default=1500,
        alias="RADIUS_METERS",
    )

    # --- Rutas internas ---
    products_path: str = Field(
        default="data/products.json",
        alias="PRODUCTS_PATH",
    )

    # --- Timeout para llamadas externas ---
    request_timeout_seconds: int = Field(
        default=10,
        alias="REQUEST_TIMEOUT_SECONDS",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
    }


# Instancia única. El resto del proyecto importa este objeto, nunca os.environ.
settings = Settings()
