import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag.prompts import PromptConfigurator


def test_program_prompts_use_tuition_fee_reduction_language():
    for agent in ("emba", "iemba", "embax"):
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        assert "tuition fee reduction" in prompt
        assert "Early Bird discount" not in prompt


def test_program_prompts_do_not_embed_volatile_programme_facts():
    volatile_snippets = [
        "14 September 2026",
        "24 August 2026",
        "31 August 2026",
        "31 October 2026",
        "CHF 77,500",
        "CHF 85,000",
        "CHF 99,000",
        "CHF 110,000",
        "9 core courses",
        "5 elective courses",
        "10 core courses",
        "4 elective courses",
    ]

    for agent in ("emba", "iemba", "embax"):
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")
        assert "They are NOT authoritative for volatile facts" in prompt
        assert "must come from retrieve_context()" in prompt
        for snippet in volatile_snippets:
            assert snippet not in prompt


def test_emba_and_iemba_prompts_do_not_invent_deadline_pricing():
    emba_prompt = PromptConfigurator.get_configured_agent_prompt("emba", language="en")
    iemba_prompt = PromptConfigurator.get_configured_agent_prompt("iemba", language="en")

    assert "24 November 2025" not in emba_prompt
    assert "9 February 2026" not in emba_prompt
    assert "31 March 2026" not in iemba_prompt
    assert "30 June 2026" not in iemba_prompt
    assert "do NOT invent a tuition fee reduction schedule" in emba_prompt
    assert "do NOT invent a tuition fee reduction schedule" in iemba_prompt


def test_lead_prompt_does_not_embed_specific_programme_figures():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "tuition fee reduction" in prompt
    assert "CHF 77,500 - 110,000" not in prompt
    assert "CHF 77,500" not in prompt
    assert "CHF 85,000" not in prompt
    assert "31 October 2026" not in prompt
    assert "route programme-specific questions to the relevant sub-agent" in prompt


def test_embax_prompt_uses_social_responsibility_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "Social Responsibility" in prompt
    assert "Sustainability" not in prompt
    assert "Technology, International Management, Leadership, Business Innovation, and Social Responsibility" in prompt


def test_lead_prompt_uses_updated_embax_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "call_embax_agent" in prompt
    assert "Tech / innovation / transformation focus or tech background" in prompt
    assert "route to a sub-agent based on the language heuristic" in prompt
    assert "double EMBA degree" not in prompt


def test_embax_prompt_highlights_joint_degree_and_core_usps():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "Joint Degree Programme from ETH Zurich and the University of St.Gallen" in prompt
    assert "BOTH ETH Zurich and University of St.Gallen alumni networks" in prompt
    assert "socially responsible leadership" in prompt
    assert "tailored Personal Development Programme with peer-to-peer coaching" in prompt
    assert "Technology, International Management, Leadership, Business Innovation, and Social Responsibility" in prompt
    assert "There are NO international study trips unless retrieved context explicitly says otherwise." in prompt
    assert "Tuition is payable in four instalments." not in prompt
    assert "double EMBA degree" not in prompt


def test_program_prompts_add_positive_framing_only_after_interest_is_clear():
    for agent in ("emba", "iemba", "embax"):
        prompt = PromptConfigurator.get_configured_agent_prompt(agent, language="en")

        assert "If the user has clearly expressed interest" in prompt
        assert "answer the concrete question first, then add positive value framing" in prompt
        assert "do not force promotional language unless the user's wording shows clear programme interest" in prompt
        assert 'Do not use hype-heavy claims such as "best", "world-leading", "perfect", or "guaranteed"' in prompt


def test_emba_prompt_highlights_dach_leadership_value_when_interest_is_clear():
    prompt = PromptConfigurator.get_configured_agent_prompt("emba", language="en")

    assert "A particularly attractive option for German-speaking leaders" in prompt
    assert "general-management capability" in prompt
    assert "practical leadership judgement" in prompt
    assert "executive peer network in the DACH business context" in prompt
    assert "HSG management depth" in prompt


def test_iemba_prompt_highlights_international_value_when_interest_is_clear():
    prompt = PromptConfigurator.get_configured_agent_prompt("iemba", language="en")

    assert "broaden their management perspective internationally" in prompt
    assert "global cohort" in prompt
    assert "different business environments" in prompt
    assert "international exposure" in prompt
    assert "leadership confidence beyond a single local market" in prompt


def test_embax_prompt_highlights_business_technology_value_when_interest_is_clear():
    prompt = PromptConfigurator.get_configured_agent_prompt("embax", language="en")

    assert "distinctive ETH Zurich and University of St.Gallen joint-degree positioning" in prompt
    assert "business-and-technology leadership intersection" in prompt
    assert "transformation and innovation relevance" in prompt
    assert "access to both alumni networks" in prompt


def test_lead_prompt_does_not_include_static_programme_snapshot():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Starts **14 September 2026**" not in prompt
    assert "Starts **24 August 2026**" not in prompt
    assert "January 2027 to July 2028" not in prompt
    assert "programme starts in **February 2027**" not in prompt
    assert "retrieved context" in prompt
