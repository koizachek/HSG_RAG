import os
import uuid
import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from src.rag.agent_chain import ExecutiveAgentChain as RealExecutiveAgentChain
from src.utils.lang import get_language_name
from src.config import config


def test_real_agent_context_dependency_and_cacheability():
    old_eval_quality = config.chain.EVALUATE_RESPONSE_QUALITY
    old_track_profile = config.convstate.TRACK_USER_PROFILE

    config.chain.EVALUATE_RESPONSE_QUALITY = False
    config.convstate.TRACK_USER_PROFILE = False

    try:
        examples = [
            {
                "name": "static FAQ should be context-independent and cacheable",
                "query": "Was ist das EMBA HSG?",
                "expected_context_dependent": False,
                "expected_should_cache": True,
            },
            {
                "name": "programme fact should be context-independent and cacheable",
                "query": "Wann startet das IEMBA?",
                "expected_context_dependent": False,
                "expected_should_cache": True,
            },
            {
                "name": "eligibility question should be context-dependent and not cacheable",
                "query": "Bin ich mit 6 Jahren Berufserfahrung und 3 Jahren Führungserfahrung für das EMBA HSG geeignet?",
                "expected_context_dependent": True,
                "expected_should_cache": False,
            },
            {
                "name": "recommendation question should be context-dependent and not cacheable",
                "query": "Ich arbeite im Tech-Bereich. Welches Programm passt besser zu mir, IEMBA oder emba X?",
                "expected_context_dependent": True,
                "expected_should_cache": False,
            },
        ]

        for example in examples:
            # Agent instance for checking raw structured output
            raw_agent = RealExecutiveAgentChain(
                language="de",
                session_id=f"raw-{uuid.uuid4()}",
            )

            raw_messages = [
                HumanMessage(example["query"]),
                SystemMessage(f"Respond in {get_language_name('de')} language."),
            ]

            structured = raw_agent._query(
                agent=raw_agent._agents["lead"],
                messages=raw_messages,
                thread_id=f"test-{uuid.uuid4()}",
            )

            assert structured.is_context_dependent == example["expected_context_dependent"], (
                f"{example['name']}: expected is_context_dependent="
                f"{example['expected_context_dependent']}, got {structured.is_context_dependent}. "
                f"Response was: {structured.response}"
            )

            # Fresh agent instance for checking final should_cache behaviour
            final_agent = RealExecutiveAgentChain(
                language="de",
                session_id=f"final-{uuid.uuid4()}",
            )

            pre = final_agent.preprocess_query(example["query"])
            final = final_agent.agent_query(pre.processed_query)

            assert final.should_cache == example["expected_should_cache"], (
                f"{example['name']}: expected should_cache="
                f"{example['expected_should_cache']}, got {final.should_cache}. "
                f"Response was: {final.response}"
            )

        # Extra real history-based example:
        # follow-up after prior turns must be context-dependent / not cacheable
        history_agent = RealExecutiveAgentChain(
            language="de",
            session_id=f"history-{uuid.uuid4()}",
        )

        first_pre = history_agent.preprocess_query(
            "Ich habe 8 Jahre Berufserfahrung, 4 Jahre Führungserfahrung und arbeite in der Softwarebranche."
        )
        history_agent.agent_query(first_pre.processed_query)

        followup_query = "Welches Programm passt zu mir?"
        followup_pre = history_agent.preprocess_query(followup_query)
        followup_final = history_agent.agent_query(followup_pre.processed_query)

        assert followup_final.should_cache is False, (
            "Follow-up recommendation based on prior turns must not be cacheable. "
            f"Response was: {followup_final.response}"
        )

    finally:
        config.chain.EVALUATE_RESPONSE_QUALITY = old_eval_quality
        config.convstate.TRACK_USER_PROFILE = old_track_profile