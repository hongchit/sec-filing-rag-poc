from fastapi import APIRouter, Depends

from ...dependencies import current_user
from .admin import router as admin_router
from .authentication import router as authentication_router
from .companies import router as companies_router
from .corpus import router as corpus_router
from .evaluation_overview import router as evaluation_overview_router
from .evaluations import router as evaluations_router
from .feedback import router as feedback_router
from .filing_batches import router as filing_batches_router
from .generation_evaluations import router as generation_evaluations_router
from .research import router as research_router
from .showcase import router as showcase_router
from .system import router as system_router

router = APIRouter(prefix="/api")
router.include_router(system_router)
router.include_router(authentication_router)
router.include_router(evaluation_overview_router)
router.include_router(showcase_router)
router.include_router(evaluations_router)
router.include_router(generation_evaluations_router)
protected = APIRouter(dependencies=[Depends(current_user)])
protected.include_router(companies_router)
protected.include_router(corpus_router)
protected.include_router(filing_batches_router)
protected.include_router(feedback_router)
protected.include_router(research_router)
protected.include_router(admin_router)
router.include_router(protected)
