import builtins
import runpy
import subprocess
import types
from pathlib import Path

import webui.run as webui_run


def test_check_dependencies_returns_true_when_imports_succeed(monkeypatch, capsys):
    real_import = builtins.__import__
    dependency_names = {"flask", "flask_cors", "pandas", "numpy", "plotly"}

    def fake_import(name, *args, **kwargs):
        if name in dependency_names:
            return types.SimpleNamespace()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert webui_run.check_dependencies() is True
    assert "All dependencies installed" in capsys.readouterr().out


def test_check_dependencies_reports_missing_dependency(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "flask":
            raise ImportError("No module named 'flask'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert webui_run.check_dependencies() is False
    output = capsys.readouterr().out
    assert "Missing dependency: No module named 'flask'" in output
    assert "pip install -r requirements.txt" in output


def test_install_dependencies_invokes_pip_with_current_interpreter(monkeypatch, capsys):
    calls = []

    def fake_check_call(command):
        calls.append(command)

    monkeypatch.setattr(webui_run.subprocess, "check_call", fake_check_call)

    assert webui_run.install_dependencies() is True
    assert calls == [[webui_run.sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]]
    assert "Dependencies installation completed" in capsys.readouterr().out


def test_install_dependencies_returns_false_on_pip_failure(monkeypatch, capsys):
    def fake_check_call(command):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(webui_run.subprocess, "check_call", fake_check_call)

    assert webui_run.install_dependencies() is False
    assert "Dependencies installation failed" in capsys.readouterr().out


def test_main_exits_when_dependencies_missing_and_user_declines(monkeypatch, capsys):
    monkeypatch.setattr(webui_run, "check_dependencies", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda: "n")

    webui_run.main()

    output = capsys.readouterr().out
    assert "Auto-install dependencies?" in output
    assert "Please manually install dependencies and retry" in output


def test_main_exits_when_auto_install_fails(monkeypatch, capsys):
    monkeypatch.setattr(webui_run, "check_dependencies", lambda: False)
    monkeypatch.setattr(webui_run, "install_dependencies", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda: "y")

    webui_run.main()

    assert "Auto-install dependencies?" in capsys.readouterr().out


def test_main_starts_app_with_model_import_fallback(monkeypatch, capsys):
    run_calls = []
    opened_urls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "model":
            raise ImportError("torch missing")
        if name == "app":
            return types.SimpleNamespace(app=FakeApp())
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(webui_run, "check_dependencies", lambda: True)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(webui_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(webui_run.webbrowser, "open", lambda url: opened_urls.append(url))

    webui_run.main()

    assert webui_run.os.environ["FLASK_APP"] == "app.py"
    assert webui_run.os.environ["FLASK_ENV"] == "development"
    assert opened_urls == ["http://localhost:7070"]
    assert run_calls == [{"debug": True, "host": "0.0.0.0", "port": 7070}]
    output = capsys.readouterr().out
    assert "Kronos model library not available" in output
    assert "Web server started successfully" in output


def test_main_starts_app_when_model_import_succeeds(monkeypatch, capsys):
    run_calls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "model":
            return types.SimpleNamespace(
                Kronos=object,
                KronosTokenizer=object,
                KronosPredictor=object,
            )
        if name == "app":
            return types.SimpleNamespace(app=FakeApp())
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(webui_run, "check_dependencies", lambda: True)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(webui_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(webui_run.webbrowser, "open", lambda url: None)

    webui_run.main()

    assert run_calls == [{"debug": True, "host": "0.0.0.0", "port": 7070}]
    output = capsys.readouterr().out
    assert "Kronos model library available" in output


def test_main_reports_startup_failure(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "model":
            return types.SimpleNamespace(
                Kronos=object,
                KronosTokenizer=object,
                KronosPredictor=object,
            )
        if name == "app":
            raise RuntimeError("port busy")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(webui_run, "check_dependencies", lambda: True)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    webui_run.main()

    output = capsys.readouterr().out
    assert "Startup failed: port busy" in output
    assert "Please check if port 7070 is occupied" in output


def test_script_guard_invokes_main(monkeypatch):
    dependency_names = {"flask", "flask_cors", "pandas", "numpy", "plotly"}
    run_calls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in dependency_names:
            return types.SimpleNamespace()
        if name == "model":
            return types.SimpleNamespace(
                Kronos=object,
                KronosTokenizer=object,
                KronosPredictor=object,
            )
        if name == "app":
            return types.SimpleNamespace(app=FakeApp())
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(webui_run.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(webui_run.webbrowser, "open", lambda url: None)

    runpy.run_path(str(Path(webui_run.__file__)), run_name="__main__")

    assert run_calls == [{"debug": True, "host": "0.0.0.0", "port": 7070}]
