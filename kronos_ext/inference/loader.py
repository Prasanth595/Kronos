"""Model loading boundary for future Kronos inference.

No model downloads or external network calls are performed here. The real
implementation should accept explicit local paths or pre-loaded model objects.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRefs:
    """Local model/tokenizer reference paths for future loading."""

    model_path: str
    tokenizer_path: str


def load_local_model_refs(model_path: str, tokenizer_path: str) -> ModelRefs:
    """Return local model references without loading model weights.

    TODO: Replace this placeholder with explicit local-only loading once the
    runtime layout and model cache policy are defined.
    """

    return ModelRefs(model_path=model_path, tokenizer_path=tokenizer_path)
