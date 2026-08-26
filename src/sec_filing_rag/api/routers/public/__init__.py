from fastapi import APIRouter

from .companies import router as companies_router
from .evaluations import router as evaluations_router
from .feedback import router as feedback_router
from .filing_batches import router as filing_batches_router
from .research import router as research_router
from .system import router as system_router

router = APIRouter(prefix="/api")
router.include_router(system_router)
router.include_router(companies_router)
router.include_router(filing_batches_router)
router.include_router(feedback_router)
router.include_router(evaluations_router)
router.include_router(research_router)
