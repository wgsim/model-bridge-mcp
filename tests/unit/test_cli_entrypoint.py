from model_bridge import main as main_module


def test_run_function_uses_mcp_run(monkeypatch):
    called = {"ok": False}

    def _fake_run():
        called["ok"] = True

    monkeypatch.setattr(main_module.mcp, "run", _fake_run)
    main_module.run()
    assert called["ok"] is True

