import json

from model_bridge import main as main_module


def test_list_cli_noninteractive_policy_contract(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "commands": {
                "codex": {"exec": ["codex", "exec", "--skip-git-repo-check"]},
                "gemini": {"exec": ["gemini", "-p"]},
                "claude_code": {"exec": ["claude", "-p"]},
                "agy": {"exec": ["agy", "-p", "--dangerously-skip-permissions"]},
            }
        },
    )

    payload = json.loads(main_module.list_cli_noninteractive_policy())
    assert payload["status"] == "ok"
    assert payload["providers"]["codex"]["skip_flag_configured"] is True
    assert payload["providers"]["gemini"]["documented_workspace_trust_skip_flag"] is None
    assert payload["providers"]["claude_code"]["workspace_trust_prompt_skipped_in_print_mode"] is True
    assert payload["providers"]["agy"]["documented_workspace_trust_skip_flag"] == "--dangerously-skip-permissions"
    assert payload["providers"]["agy"]["skip_flag_configured"] is True
