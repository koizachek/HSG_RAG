"""
Tests for TranscriptLogger (src/utils/logging.py) and its chain integration.

Contract under test:
- transcripts are OFF by default and write nothing (no dir, no file) —
  they may only be enabled after DSB sign-off (config.usage.STORE_TRANSCRIPTS)
- when enabled, the transcript carries user + assistant text with metadata
- wipe_session_data deletes profile, usage-event AND transcript files
"""
import json
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import config
from src.rag import agent_chain as agent_chain_module
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.logging import TranscriptLogger


class DummyWeaviateService:
    pass


def make_chain(monkeypatch, session_id="transcript-test-session"):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(
        agent_chain_module.ExecutiveAgentChain, "_init_agents", lambda self: ({}, {})
    )
    chain = agent_chain_module.ExecutiveAgentChain(language="en", session_id=session_id)
    monkeypatch.setattr(
        chain._language_detector, "detect_explicit_switch_request", lambda q: None
    )
    monkeypatch.setattr(
        chain._language_detector, "is_language_neutral_input", lambda q: True
    )
    monkeypatch.setattr(chain._scope_guardian, "check_scope", lambda q, lang: "on_topic")
    monkeypatch.setattr(
        chain,
        "_query_lead",
        lambda q, on_delta=None: LeadAgentQueryResponse(
            response="The answer.",
            language="en",
            processed_query=q,
            relevant_programs=[],
        ),
    )
    return chain


class TestTranscriptLogger:

    def test_disabled_by_default(self, tmp_path):
        logger = TranscriptLogger(base_dir=str(tmp_path / "transcripts"))
        assert logger.enabled is False
        logger.log_turn("sess-1", 1, "user text", "assistant text")
        assert not (tmp_path / "transcripts").exists()

    def test_enabled_writes_transcript(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config.usage, "STORE_TRANSCRIPTS", True)
        logger = TranscriptLogger(base_dir=str(tmp_path / "transcripts"))
        logger.log_turn("sess-2", 1, "user text", "assistant text", meta={"language": "de"})

        log_path = tmp_path / "transcripts" / "transcript_sess-2.jsonl"
        entry = json.loads(log_path.read_text(encoding="utf-8"))
        assert entry["user"] == "user text"
        assert entry["assistant"] == "assistant text"
        assert entry["turn_index"] == 1
        assert entry["meta"]["language"] == "de"

    def test_never_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config.usage, "STORE_TRANSCRIPTS", True)
        logger = TranscriptLogger(base_dir=str(tmp_path / "transcripts"))
        logger.log_turn("sess-3", 1, "text", "text", meta={"bad": object()})


class TestChainIntegration:

    def test_chain_writes_no_transcript_by_default(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        chain.query("Tell me about the EMBA")

        assert not (tmp_path / "logs" / "transcripts").exists()
        # usage event was still written
        assert (tmp_path / "logs" / "usage").exists()

    def test_chain_writes_transcript_when_enabled(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(config.usage, "STORE_TRANSCRIPTS", True)
        chain = make_chain(monkeypatch)
        chain.query("Tell me about the EMBA")

        log_path = (
            tmp_path / "logs" / "transcripts" / "transcript_transcript-test-session.jsonl"
        )
        entry = json.loads(log_path.read_text(encoding="utf-8"))
        assert entry["user"] == "Tell me about the EMBA"
        assert entry["assistant"] == "The answer."
        assert entry["meta"]["outcome"] == "answered"

    def test_wipe_session_data_deletes_all_session_files(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(config.usage, "STORE_TRANSCRIPTS", True)
        session_id = "wipe-test-session"
        chain = make_chain(monkeypatch, session_id=session_id)
        chain.query("Tell me about the EMBA")

        # simulate an existing profile snapshot as well
        profile_dir = tmp_path / "logs" / "user_profiles"
        profile_dir.mkdir(parents=True)
        profile_file = profile_dir / f"profile_{session_id}_20260710_120000.json"
        profile_file.write_text("{}", encoding="utf-8")

        usage_file = tmp_path / "logs" / "usage" / f"usage_{session_id}.jsonl"
        transcript_file = (
            tmp_path / "logs" / "transcripts" / f"transcript_{session_id}.jsonl"
        )
        assert usage_file.exists()
        assert transcript_file.exists()

        chain.wipe_session_data()

        assert not profile_file.exists()
        assert not usage_file.exists()
        assert not transcript_file.exists()
