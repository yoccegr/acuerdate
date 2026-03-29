import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from models.request import RecommendRequest
from models.response import (
    ClassificationSummary,
    EngineBlock,
    ErrorDetail,
    MapsBlock,
    ParamsUsed,
    RecommendResponse,
    RecommendationDetail,
)
from modules.classifier import classify_list
from modules.coverage_engine import evaluate
from modules.maps_client import (
    MapsAuthError,
    MapsQuotaError,
    MapsTimeoutError,
    MapsUnavailableError,
    search,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Recomienda una tienda para la lista de compras del usuario",
)
async def recommend(raw_request: Request, body: RecommendRequest) -> JSONResponse:
    state = raw_request.app.state
    index = state.index
    settings = state.settings

    classification = classify_list(body.items, index)

    profile = evaluate(classification, settings)

    engine_block = EngineBlock(
        classification_summary=ClassificationSummary(
            total_items=len(classification.items),
            unrecognized=len(classification.unrecognized),
        ),
        rule_applied=profile.rule_applied,
        params_used=ParamsUsed(
            specialist_coverage_threshold=settings.specialist_coverage_threshold,
            specialist_max_items=settings.specialist_max_items,
            optional_coverage_threshold=settings.optional_coverage_threshold,
        ),
    )

    try:
        maps_result = search(
            profile=profile,
            location=body.location,
            radius_meters=settings.radius_meters,
            api_key=settings.google_maps_api_key,
            timeout=settings.request_timeout_seconds,
        )
    except MapsAuthError as e:
        logger.error("Maps auth error: %s", e)
        return _error_response(
            500,
            "maps_auth_error",
            "Error de autenticación con Google Maps.",
        )
    except MapsQuotaError as e:
        logger.error("Maps quota error: %s", e)
        return _error_response(
            500,
            "maps_quota_exceeded",
            "Cuota de Google Maps API excedida.",
        )
    except MapsTimeoutError as e:
        logger.error("Maps timeout: %s", e)
        return _error_response(
            500,
            "maps_timeout",
            "Google Maps no respondió a tiempo. Intenta de nuevo.",
        )
    except MapsUnavailableError as e:
        logger.error("Maps unavailable: %s", e)
        return _error_response(
            500,
            "maps_api_unavailable",
            "No se pudo conectar con Google Maps. Intenta de nuevo.",
        )
    except Exception as e:
        logger.exception("Error inesperado en maps_client: %s", e)
        return _error_response(
            500,
            "internal_error",
            "Error interno. Intenta de nuevo.",
        )

    recommendation_detail = None
    if maps_result.recommendation is not None:
        recommendation_detail = RecommendationDetail(
            store=maps_result.recommendation,
            alternatives=maps_result.alternatives,
        )

    maps_block = MapsBlock(
        recommendation=recommendation_detail,
        optional=maps_result.optional,
        search_status=maps_result.search_status,
    )

    status = "ok" if maps_result.recommendation is not None else "no_results"

    response = RecommendResponse(
        status=status,
        engine=engine_block,
        maps=maps_block,
    )
    return JSONResponse(
        content=response.model_dump(),
        status_code=200,
    )


def _error_response(http_status: int, code: str, message: str) -> JSONResponse:
    body = RecommendResponse(
        status="error",
        error=ErrorDetail(code=code, message=message),
    )
    return JSONResponse(
        content=body.model_dump(),
        status_code=http_status,
    )
