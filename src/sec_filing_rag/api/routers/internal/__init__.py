from fastapi import APIRouter, Depends

from ...dependencies import authorize_internal
from .corpus import router as corpus_router
from .lifecycle import router as lifecycle_router
from .providers import router as providers_router

router = APIRouter(prefix="/internal", dependencies=[Depends(authorize_internal)])
router.include_router(lifecycle_router)
router.include_router(providers_router)
router.include_router(corpus_router)
