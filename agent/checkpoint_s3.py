"""
S3 checkpointer — STUB (not yet implemented).

Swap SqliteSaver for this once you have a bucket.
Implement BaseCheckpointSaver from langgraph.checkpoint.base with:

  - put(config, checkpoint, metadata, new_versions) → RunnableConfig
  - get_tuple(config) → CheckpointTuple | None
  - list(config, *, filter, before, limit) → Iterator[CheckpointTuple]

S3 layout:
  s3://<bucket>/<prefix>/threads/<thread_id>/checkpoints/<checkpoint_id>.json
  s3://<bucket>/<prefix>/threads/<thread_id>/files/<filename>
  s3://<bucket>/<prefix>/threads/<thread_id>/artefacts/<filename>

See: https://langchain-ai.github.io/langgraph/reference/checkpoints/
"""
from __future__ import annotations


class S3Saver:
    """Placeholder — raise on instantiation until implemented."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "S3Saver is not yet implemented. "
            "Use SqliteSaver (the default) until you have an S3 bucket configured."
        )
