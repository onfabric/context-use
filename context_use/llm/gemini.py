"""Gemini implementation of BatchLLMClient.

Wraps the Google GenAI batch-generate API.  When ported to aertex this
can delegate to the existing ``app.core.ai.gemini.Gemini`` class; here
we keep a thin standalone wrapper.

NOTE: This is a structural stub.  The actual ``google-genai`` calls
are left as TODO placeholders because the specifics depend on the
SDK version and auth setup you wire in.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel

from context_use.llm.base import BatchLLMClient, BatchResults, PromptItem

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiBatchClient(BatchLLMClient):
    """Gemini batch-generate client.

    Parameters
    ----------
    genai_client:
        An authenticated ``google.genai.Client`` instance.
    model:
        Model name, e.g. ``"gemini-2.0-flash"``.
    """

    def __init__(self, genai_client: object, model: str = "gemini-2.0-flash") -> None:
        self._client = genai_client
        self._model = model

    def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Submit prompts as a Gemini batch prediction job.

        Returns the job name (resource path) as the ``job_key``.
        """
        # TODO: implement using google.genai batch API
        # 1. Build JSONL request from prompts
        # 2. Upload to GCS or inline
        # 3. Call client.batches.create(...)
        # 4. Return job.name as the job_key
        raise NotImplementedError(
            "GeminiBatchClient.batch_submit is a stub — "
            "wire in the google-genai batch API"
        )

    def batch_get_results(
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        """Poll a Gemini batch job for results.

        Returns ``None`` while the job is still running, or a dict of
        ``{item_id: parsed_schema}`` once complete.
        """
        # TODO: implement using google.genai batch API
        # 1. Call client.batches.get(name=job_key)
        # 2. If not completed, return None
        # 3. If completed, download results from GCS
        # 4. Parse each row: json.loads(line) → schema.model_validate(data)
        # 5. Return {item_id: parsed_model}
        raise NotImplementedError(
            "GeminiBatchClient.batch_get_results is a stub — "
            "wire in the google-genai batch API"
        )
