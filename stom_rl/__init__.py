"""STOM tick/back-data reinforcement-learning utilities.

The package is intentionally independent from Kronos model code.  It may reuse
existing STOM data artifacts as inputs, but it does not depend on Kronos
tokenizers, predictors, or checkpoints.

Import concrete utilities from submodules, for example
``stom_rl.episode_manifest`` or ``stom_rl.trading_env``.  Keeping the package
initializer side-effect-free also avoids double-import warnings when running
``python -m`` submodules.
"""
