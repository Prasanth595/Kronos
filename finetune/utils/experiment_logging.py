"""Optional experiment-tracking integrations for fine-tuning."""

import importlib
from typing import Any, Mapping, Optional


def create_comet_experiment(config: Mapping[str, Any]) -> Optional[Any]:
    """Create a Comet experiment only when Comet logging is enabled.

    Keeping the import here allows fine-tuning users who do not use Comet to
    run without installing its optional dependency.
    """
    if not config.get("use_comet", False):
        return None

    try:
        comet_ml = importlib.import_module("comet_ml")
    except ModuleNotFoundError as exc:
        if exc.name == "comet_ml":
            raise RuntimeError(
                "Comet logging is enabled, but the optional dependency is not "
                "installed. Install it with `pip install comet_ml`, or set "
                "use_comet = False` in finetune/config.py."
            ) from exc
        raise

    comet_config = config["comet_config"]
    experiment = comet_ml.Experiment(
        api_key=comet_config["api_key"],
        project_name=comet_config["project_name"],
        workspace=comet_config["workspace"],
    )
    experiment.add_tag(config["comet_tag"])
    experiment.set_name(config["comet_name"])
    experiment.log_parameters(dict(config))
    return experiment
