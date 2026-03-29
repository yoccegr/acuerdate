import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.routes import router
from config.settings import Settings
from models.response import ErrorDetail, RecommendResponse
from modules.classifier_index import ClassifierIndex
from modules.dictionary_loader import load_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Acuérdate! backend...")

    try:
        settings = Settings()
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar la configuración: {e}") from e

    try:
        products = load_products(settings.products_path)
    except (FileNotFoundError, ValueError) as e:
        raise RuntimeError(f"No se pudo cargar el diccionario: {e}") from e

    try:
        index = ClassifierIndex(products)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo construir el índice del clasificador: {e}"
        ) from e

    app.state.settings = settings
    app.state.products = products
    app.state.index = index

    logger.info(
        "Servicio listo — %d productos indexados, %d claves en índice",
        len(products),
        len(index),
    )

    yield

    logger.info("Servicio detenido.")


app = FastAPI(
    title="Acuérdate! API",
    version="0.1.0",
    description="Backend MVP — recomienda tiendas para una lista de compras.",
    lifespan=lifespan,
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = exc.errors()
    code = _validation_error_code(errors)

    logger.warning("Request inválido (%s): %s", code, errors)

    body = RecommendResponse(
        status="error",
        error=ErrorDetail(
            code=code,
            message="El request contiene datos inválidos.",
        ),
    )
    return JSONResponse(content=body.model_dump(), status_code=400)


def _validation_error_code(errors: list[dict]) -> str:
    if not errors:
        return "invalid_request"

    first = errors[0]
    loc = first.get("loc", ())

    if len(loc) >= 2:
        field = loc[1]
        if field == "items":
            return "missing_items"
        if field == "location":
            sub_field = loc[2] if len(loc) >= 3 else None
            if sub_field in ("lat", "lng"):
                return "invalid_coordinates"
            return "missing_location"

    return "invalid_request"


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("Excepción no manejada: %s", exc)
    body = RecommendResponse(
        status="error",
        error=ErrorDetail(
            code="internal_error",
            message="Error interno. Intenta de nuevo.",
        ),
    )
    return JSONResponse(content=body.model_dump(), status_code=500)
