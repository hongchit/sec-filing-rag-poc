from fastapi import APIRouter, Depends

from ...dependencies import authorize_internal
from .corpus import router as corpus_router
from .lifecycle import router as lifecycle_router
from .providers import router as providers_router
from .scheduled_batches import router as scheduled_batches_router

router = APIRouter(prefix="/internal", dependencies=[Depends(authorize_internal)])
router.include_router(lifecycle_router)
router.include_router(providers_router)
router.include_router(corpus_router)
router.include_router(scheduled_batches_router)
