from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ....repositories.corpus_reader import CorpusReaderRepository
from ....schemas.corpus_reader import (
    CorpusChunkLocation,
    CorpusItem,
    CorpusItemDocument,
    CorpusVersion,
)
from ...dependencies import corpus_reader_repository

router = APIRouter(prefix="/corpus", tags=["corpus"])
Repository = Annotated[CorpusReaderRepository, Depends(corpus_reader_repository)]
ChunkId = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]
ChunkQuery = Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")]


@router.get(
    "/versions/{corpus_version_id}",
    response_model=CorpusVersion,
    operation_id="getCorpusVersion",
)
def version(corpus_version_id: uuid.UUID, repository: Repository) -> CorpusVersion:
    value = repository.version(corpus_version_id)
    if value is None:
        raise HTTPException(status_code=404, detail="ready corpus version not found")
    return CorpusVersion.model_validate(value)


@router.get(
    "/versions/{corpus_version_id}/items/{item}",
    response_model=CorpusItemDocument,
    operation_id="getCorpusItem",
)
def item_document(
    corpus_version_id: uuid.UUID,
    item: CorpusItem,
    repository: Repository,
    chunk_id: ChunkQuery = None,
) -> CorpusItemDocument:
    value = repository.item(corpus_version_id, item, chunk_id)
    if value is None:
        raise HTTPException(status_code=404, detail="ready corpus Item or chunk not found")
    return CorpusItemDocument.model_validate(value)


@router.get(
    "/chunks/{chunk_id}/location",
    response_model=CorpusChunkLocation,
    operation_id="getCorpusChunkLocation",
)
def chunk_location(chunk_id: ChunkId, repository: Repository) -> CorpusChunkLocation:
    value = repository.location(chunk_id)
    if value is None:
        raise HTTPException(status_code=404, detail="ready corpus chunk not found")
    return CorpusChunkLocation.model_validate(value)
