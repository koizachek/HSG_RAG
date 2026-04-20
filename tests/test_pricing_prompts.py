import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag.prompts import PromptConfigurator


def test_program_prompts_use_tuition_fee_reduction_language():
    for agent in ("emba", "iemba", "embax"):
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        assert "tuition fee reduction" in prompt
        assert "Early Bird discount" not in prompt


def test_program_prompts_use_updated_published_tuition_figures():
    expected_snippets = {
        "emba": ["14 September 2026", "CHF 77,500", "9 core courses", "5 elective courses"],
        "iemba": ["24 August 2026", "CHF 85,000", "10 core courses", "4 elective courses"],
        "embax": ["31 August 2026", "CHF 99,000", "31 October 2026", "CHF 110,000"],
    }

    for agent, snippets in expected_snippets.items():
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        for snippet in snippets:
            assert snippet in prompt


def test_emba_and_iemba_prompts_do_not_invent_deadline_pricing():
    emba_prompt = PromptConfigurator.get_configured_agent_prompt("emba", language="en")
    iemba_prompt = PromptConfigurator.get_configured_agent_prompt("iemba", language="en")

    assert "24 November 2025" not in emba_prompt
    assert "9 February 2026" not in emba_prompt
    assert "31 March 2026" not in iemba_prompt
    assert "30 June 2026" not in iemba_prompt
    assert "Do NOT mention a tuition fee reduction schedule unless retrieved context explicitly provides one." in emba_prompt
    assert "Do NOT mention a tuition fee reduction schedule unless retrieved context explicitly provides one." in iemba_prompt


def test_lead_prompt_uses_specific_programme_figures_instead_of_ranges():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "tuition fee reduction" in prompt
    assert "CHF 77,500 - 110,000" not in prompt
    assert "**EMBA HSG**: **CHF 77,500**." in prompt
    assert "**IEMBA HSG**: **CHF 85,000**." in prompt
    assert "31 October 2026" in prompt


def test_embax_prompt_uses_social_responsibility_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "Social Responsibility" in prompt
    assert "Sustainability" not in prompt
    assert "Technology, International Management, Leadership, Business Innovation, and Social Responsibility" in prompt


def test_lead_prompt_uses_updated_embax_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Technology/Innovation?" in prompt
    assert "Technology, Innovation, Social Responsibility" in prompt
    assert "strong focus on technology, leadership, business innovation, and social responsibility" in prompt
    assert "Joint Degree Programme from ETH Zurich and the University of St.Gallen" in prompt
    assert "Access to BOTH alumni networks" in prompt
    assert "Do NOT attribute international study trips to emba X." in prompt
    assert "double EMBA degree" not in prompt


def test_embax_prompt_highlights_joint_degree_and_core_usps():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "Joint Degree Programme from ETH Zurich and the University of St.Gallen" in prompt
    assert "BOTH ETH Zurich and University of St.Gallen alumni networks" in prompt
    assert "socially responsible leadership" in prompt
    assert "tailored Personal Development Programme with peer-to-peer coaching" in prompt
    assert "Technology, International Management, Leadership, Business Innovation, and Social Responsibility" in prompt
    assert "There are NO international study trips." in prompt
    assert "Tuition is payable in four instalments." in prompt
    assert "double EMBA degree" not in prompt


def test_lead_prompt_includes_updated_programme_snapshot():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Starts **14 September 2026**" in prompt
    assert "Starts **24 August 2026**" in prompt
    assert "January 2027 to July 2028" in prompt
    assert "programme starts in **February 2027**" in prompt
