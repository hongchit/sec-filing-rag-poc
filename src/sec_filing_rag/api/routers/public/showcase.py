from typing import Annotated

from fastapi import APIRouter, Depends

from ....core.config import Settings
from ....showcase import ShowcaseResponse, load_showcase
from ...dependencies import settings

router = APIRouter(prefix="/showcase", tags=["showcase"])


@router.get("", response_model=ShowcaseResponse, operation_id="getShowcase")
def showcase(config: Annotated[Settings, Depends(settings)]) -> ShowcaseResponse:
    """Read optional, deployment-managed examples for the public landing page."""
    return load_showcase(config.showcase_config_path)
