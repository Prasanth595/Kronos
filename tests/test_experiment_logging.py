import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).parents[1] / "finetune" / "utils" / "experiment_logging.py"
SPEC = importlib.util.spec_from_file_location("experiment_logging", MODULE_PATH)
experiment_logging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment_logging)


class CreateCometExperimentTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "use_comet": True,
            "comet_config": {
                "api_key": "test-key",
                "project_name": "test-project",
                "workspace": "test-workspace",
            },
            "comet_tag": "test-tag",
            "comet_name": "test-name",
        }

    def test_disabled_logging_does_not_import_comet(self):
        config = {"use_comet": False}
        with patch.object(experiment_logging.importlib, "import_module") as import_module:
            self.assertIsNone(experiment_logging.create_comet_experiment(config))
        import_module.assert_not_called()

    def test_enabled_logging_explains_missing_optional_dependency(self):
        with patch.object(
            experiment_logging.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("No module named 'comet_ml'", name="comet_ml"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pip install comet_ml"):
                experiment_logging.create_comet_experiment(self.config)

    def test_enabled_logging_configures_experiment(self):
        experiment = Mock()
        comet_module = SimpleNamespace(Experiment=Mock(return_value=experiment))
        with patch.object(experiment_logging.importlib, "import_module", return_value=comet_module):
            result = experiment_logging.create_comet_experiment(self.config)

        self.assertIs(result, experiment)
        comet_module.Experiment.assert_called_once_with(
            api_key="test-key",
            project_name="test-project",
            workspace="test-workspace",
        )
        experiment.add_tag.assert_called_once_with("test-tag")
        experiment.set_name.assert_called_once_with("test-name")
        experiment.log_parameters.assert_called_once_with(self.config)


if __name__ == "__main__":
    unittest.main()
