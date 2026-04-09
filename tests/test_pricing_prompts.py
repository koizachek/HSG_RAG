import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag.prompts import PromptConfigurator


def test_program_prompts_use_tuition_fee_reduction_language():
    for agent in ("emba", "iemba", "embax"):
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        assert "tuition fee reduction" in prompt
        assert "Early Bird discount" not in prompt


def test_program_prompts_include_deadline_based_pricing():
    expected_snippets = {
        "emba": ["24 November 2025", "CHF 70,000", "9 February 2026", "CHF 75,000"],
        "iemba": ["31 March 2026", "CHF 80,000", "30 June 2026", "CHF 85,000"],
        "embax": ["31 August 2026", "CHF 99,000", "31 October 2026", "CHF 110,000"],
    }

    for agent, snippets in expected_snippets.items():
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        for snippet in snippets:
            assert snippet in prompt


def test_lead_prompt_uses_specific_deadline_figures_instead_of_ranges():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "tuition fee reduction" in prompt
    assert "CHF 75,000 - 110,000" not in prompt
    assert "24 November 2025" in prompt
    assert "30 June 2026" in prompt
    assert "31 October 2026" in prompt


def test_embax_prompt_highlights_joint_degree_and_core_usps():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "Joint Degree Programme from ETH Zurich and the University of St.Gallen" in prompt
    assert "BOTH ETH Zurich and University of St.Gallen alumni networks" in prompt
    assert "Individual Development Journey" in prompt
    assert "Leadership Skills Labs" in prompt
    assert "Peak Performance Insights" in prompt
    assert "Technology and Leadership" in prompt
    assert "There are NO international study trips." in prompt
    assert "double EMBA degree" not in prompt


def test_lead_prompt_uses_embax_joint_degree_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Joint Degree Programme from ETH Zurich and the University of St.Gallen" in prompt
    assert "Access to BOTH alumni networks" in prompt
    assert "Do NOT attribute international study trips to emba X." in prompt
    assert "double EMBA degree" not in prompt
