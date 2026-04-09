import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.rag import agent_chain as agent_chain_module


class DummyWeaviateService:
    pass


def test_agent_chain_generates_session_id_when_missing(monkeypatch):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module.ExecutiveAgentChain, "_init_agents", lambda self: ({}, {}))

    agent = agent_chain_module.ExecutiveAgentChain(language="en")

    assert agent._user_id
    assert agent._conversation_state["session_id"] == agent._user_id
    assert agent._conversation_state["user_id"] == agent._user_id


def test_log_user_profile_uses_valid_session_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module.ExecutiveAgentChain, "_init_agents", lambda self: ({}, {}))
    monkeypatch.setattr(agent_chain_module.config.convstate, "TRACK_USER_PROFILE", True)

    agent = agent_chain_module.ExecutiveAgentChain(language="en", session_id="session-123")
    agent._log_user_profile()

    log_dir = tmp_path / "logs" / "user_profiles"
    created_files = list(log_dir.glob("profile_session-123_*.json"))

    assert len(created_files) == 1
