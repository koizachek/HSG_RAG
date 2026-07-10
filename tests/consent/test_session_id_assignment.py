"""
Tests for per-session session id assignment (app.py)

Regression guard: gr.State defaults are evaluated once at Blocks construction
and copied into every browser session. A uuid4() default therefore meant ALL
visitors between two container restarts shared one session_id — colliding
consent logs, user-profile snapshots and any per-session analytics. The id is
now assigned per browser session by the assign_session_id load handler, with a
fallback inside on_accept/on_decline.
"""
import sys
import os
import uuid

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import gradio as gr

from src.apps.chat.app import ChatbotApplication


def _uuid_like(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _find_handler(blocks: gr.Blocks, name: str):
    for dep in blocks.fns.values():
        fn = getattr(dep, "fn", None)
        if fn is not None and getattr(fn, "__name__", "") == name:
            return fn
    raise AssertionError(f"No event handler named {name!r} found in Blocks")


class TestSessionIdAssignment:
    """Session ids must be unique per browser session, never shared"""

    def test_no_state_default_is_a_shared_uuid(self):
        """No gr.State default may hold a construction-time uuid (shared by all sessions)"""
        app = ChatbotApplication(language="de")
        states = [b for b in app._gradio_app.blocks.values() if isinstance(b, gr.State)]
        assert states, "expected gr.State components in the app"
        shared_uuids = [s.value for s in states if _uuid_like(s.value)]
        assert not shared_uuids, (
            f"gr.State default(s) {shared_uuids} are construction-time uuids "
            "shared across all sessions"
        )

    def test_assign_session_id_generates_fresh_ids(self):
        """The load handler must hand out a distinct uuid per session"""
        app = ChatbotApplication(language="de")
        assign = _find_handler(app._gradio_app, "assign_session_id")
        first, second = assign(None), assign(None)
        assert _uuid_like(first)
        assert _uuid_like(second)
        assert first != second

    def test_assign_session_id_keeps_existing_id(self):
        """An already-assigned session id must not be replaced"""
        app = ChatbotApplication(language="de")
        assign = _find_handler(app._gradio_app, "assign_session_id")
        assert assign("existing-id") == "existing-id"

    def test_on_accept_falls_back_to_fresh_id(self, monkeypatch):
        """If the load event never fired (session_id None), on_accept must
        generate an id, use it consistently (consent log + agent) and persist
        it back into session_id_state (last output)."""

        class FakeChain:
            def __init__(self, language, session_id):
                self.session_id = session_id

            def generate_greeting(self):
                return "greeting"

        monkeypatch.setattr("src.apps.chat.app.ExecutiveAgentChain", FakeChain)
        app = ChatbotApplication(language="de")

        logged = {}
        monkeypatch.setattr(
            app._consentLogger,
            "log",
            lambda session_id, decision, policy_version="1.0": logged.update(
                session_id=session_id, decision=decision
            ),
        )

        on_accept = _find_handler(app._gradio_app, "on_accept")
        result = on_accept("de", None)

        returned_session_id = result[-1]
        assert _uuid_like(returned_session_id)
        assert logged["session_id"] == returned_session_id
        assert logged["decision"] == "accepted"
        agent = result[3]
        assert agent.session_id == returned_session_id

    def test_on_decline_falls_back_to_fresh_id(self, monkeypatch):
        """Same fallback contract for decline (consent log + state write-back)"""
        app = ChatbotApplication(language="de")

        logged = {}
        monkeypatch.setattr(
            app._consentLogger,
            "log",
            lambda session_id, decision, policy_version="1.0": logged.update(
                session_id=session_id, decision=decision
            ),
        )

        on_decline = _find_handler(app._gradio_app, "on_decline")
        result = on_decline("de", None)

        returned_session_id = result[-1]
        assert _uuid_like(returned_session_id)
        assert logged["session_id"] == returned_session_id
        assert logged["decision"] == "declined"
