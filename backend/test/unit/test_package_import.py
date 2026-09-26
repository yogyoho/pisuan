import sys


def test_import_pisuan_does_not_eagerly_import_knowledge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delitem(sys.modules, "pisuan", raising=False)
    monkeypatch.delitem(sys.modules, "pisuan.knowledge", raising=False)

    import pisuan

    assert pisuan.get_version() == pisuan.__version__
    assert "pisuan.knowledge" not in sys.modules
