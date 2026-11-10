import pytest

from sessionbeat.wire import session_log_path


def test_session_log_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSIONBEAT_HOME", str(tmp_path))
    with pytest.raises(ValueError, match=r"\.\./x"):
        session_log_path("../x")
