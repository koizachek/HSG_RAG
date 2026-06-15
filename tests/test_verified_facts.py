"""
Offline unit tests for the verified-facts layer and the local language
detection heuristics. No API key, no network, no LLM calls.

Run:  pytest tests/test_verified_facts.py -v
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import config
from src.rag.verified_facts import VerifiedFacts


@pytest.fixture(autouse=True)
def fresh_facts_cache():
    VerifiedFacts.reset_cache()
    yield
    VerifiedFacts.reset_cache()


def _facts_file() -> dict:
    path = os.path.join(config.paths.DATA, "database", "programme_facts.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------ Facts file ----------------------------------

class TestFactsFile:
    def test_facts_file_exists_and_parses(self):
        data = _facts_file()
        assert "programmes" in data and "generated_at" in data

    def test_all_three_programmes_present(self):
        programmes = _facts_file()["programmes"]
        assert set(programmes) == {"emba", "iemba", "emba_x"}

    def test_every_programme_has_volatile_core_facts(self):
        for key, prog in _facts_file()["programmes"].items():
            assert prog.get("programme_start"), f"{key}: missing programme_start"
            assert isinstance(prog.get("ects_credits"), int), f"{key}: ects_credits must be int"
            assert prog["ects_credits"] > 0, f"{key}: missing ects_credits"
            tuition = prog.get("tuition_chf", {})
            for deadline_key in ("first_deadline", "final_deadline"):
                entry = tuition.get(deadline_key, {})
                assert entry.get("deadline"), f"{key}: missing {deadline_key}.deadline"
                assert isinstance(entry.get("fee"), int), f"{key}: {deadline_key}.fee must be int"

    def test_fees_are_not_cross_contaminated(self):
        """Each programme's fees must be unique values (guards against the
        historic bug of attributing one programme's price to another)."""
        programmes = _facts_file()["programmes"]
        final_fees = {
            key: prog["tuition_chf"]["final_deadline"]["fee"]
            for key, prog in programmes.items()
        }
        assert len(set(final_fees.values())) == len(final_fees), (
            f"Duplicate final fees across programmes: {final_fees}"
        )

    def test_first_fee_lower_than_final_fee(self):
        """Deadline-based pricing: earlier deadline must be cheaper."""
        for key, prog in _facts_file()["programmes"].items():
            first = prog["tuition_chf"]["first_deadline"]["fee"]
            final = prog["tuition_chf"]["final_deadline"]["fee"]
            assert first < final, f"{key}: first fee {first} not lower than final {final}"


# ------------------------------ Prompt block --------------------------------

class TestPromptBlock:
    def test_block_renders_for_both_languages(self):
        for lang in ("de", "en"):
            block = VerifiedFacts.render_prompt_block(language=lang)
            assert "VERIFIED PROGRAMME FACTS" in block

    def test_block_contains_all_final_fees(self):
        block = VerifiedFacts.render_prompt_block(language="de")
        for prog in _facts_file()["programmes"].values():
            fee = prog["tuition_chf"]["final_deadline"]["fee"]
            assert f"CHF {fee:,}".replace(",", "'") in block

    def test_block_contains_ects_credits(self):
        block = VerifiedFacts.render_prompt_block(language="en")
        for prog in _facts_file()["programmes"].values():
            assert f"ECTS: {prog['ects_credits']}" in block

    def test_block_contains_advisors(self):
        block = VerifiedFacts.render_prompt_block(language="en")
        for prog in _facts_file()["programmes"].values():
            assert prog["advisor"]["name"] in block

    def test_german_labels_in_german_block(self):
        block = VerifiedFacts.render_prompt_block(language="de")
        assert "Studiengebühr" in block and "Bewerbungsfrist" in block

    def test_unknown_language_falls_back_to_english(self):
        block = VerifiedFacts.render_prompt_block(language="fr")
        assert "Tuition fee" in block

    def test_lead_prompt_includes_facts_block(self):
        from src.rag.prompts import PromptConfigurator
        prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="de")
        assert "VERIFIED PROGRAMME FACTS" in prompt
        assert "AUTHORITATIVE" in prompt


# --------------------------- Facts extraction -------------------------------

class TestFactExtractionFallbacks:
    def test_ects_fallback_reads_es_hsg_label_value(self):
        from src.pipeline.update_programme_facts import _extract_ects_credits

        text = "### ECTS-Punkte\n\n75\n\n### Dauer\n\n18 months"
        assert _extract_ects_credits(text) == 75

    def test_diff_ignores_descriptive_llm_paraphrases(self):
        from src.pipeline.update_programme_facts import diff_facts, preserve_non_material_changes

        old = {
            "programmes": {
                "emba": {
                    "duration": {"en": "18 months (up to 48 months)"},
                    "structure": {
                        "en": "9 core courses, 5 electives, 14 weeks on campus, capstone project, self-study"
                    },
                    "tuition_chf": {
                        "final_deadline": {"deadline": "2026-07-15", "fee": 77500}
                    },
                }
            }
        }
        new = {
            "programmes": {
                "emba": {
                    "duration": {"en": "18 months (up to max. 48 months)"},
                    "structure": {
                        "en": (
                            "9 core courses, 5 electives, 14 weeks on campus, "
                            "capstone project, self-study, flexible timing."
                        )
                    },
                    "tuition_chf": {
                        "final_deadline": {"deadline": "2026-07-15", "fee": 77500}
                    },
                }
            }
        }

        stabilized = preserve_non_material_changes(old, new)
        assert diff_facts(old, stabilized) == []
        assert stabilized["programmes"]["emba"]["duration"]["en"] == "18 months (up to 48 months)"

    def test_diff_keeps_alerting_on_material_core_fact_changes(self):
        from src.pipeline.update_programme_facts import diff_facts

        old = {
            "programmes": {
                "emba": {
                    "tuition_chf": {
                        "final_deadline": {"deadline": "2026-07-15", "fee": 77500}
                    }
                }
            }
        }
        new = {
            "programmes": {
                "emba": {
                    "tuition_chf": {
                        "final_deadline": {"deadline": "2026-07-15", "fee": 79500}
                    }
                }
            }
        }

        assert diff_facts(old, new) == [
            "emba.tuition_chf.final_deadline.fee: 77500 -> 79500"
        ]

    def test_locations_are_parsed_from_official_page_block(self):
        from src.pipeline.update_programme_facts import _extract_locations_from_programme_page

        html = """
        <div class="locations">
          <small>Orte</small>
          <ul class="items-amount-10">
            <li>Costa Rica <small class='type'>Wahlkurs</small></li>
            <li>Tokio, Japan</li>
            <li>New York City <small class='type'>Wahlkurs</small></li>
            <li>St. Gallen, Schweiz</li>
            <li>Peking, China</li>
            <li>UC Berkeley, USA</li>
            <li>UC Irvine, USA</li>
            <li>Italien <small class='type'>Wahlkurs</small></li>
            <li>Südafrika <small class='type'>Wahlkurs</small></li>
            <li>Spanien <small class='type'>Wahlkurs</small></li>
          </ul>
        </div>
        """

        locations = _extract_locations_from_programme_page(html)

        assert locations is not None
        assert "Costa Rica (Wahlkurs)" in locations.de
        assert "New York City (Wahlkurs)" in locations.de
        assert "St. Gallen, Switzerland" in locations.en
        assert "Beijing, China" in locations.en
        assert "South Africa (elective)" in locations.en

    def test_location_changes_are_not_treated_as_prose_paraphrases(self):
        from src.pipeline.update_programme_facts import diff_facts, preserve_non_material_changes

        old = {
            "programmes": {
                "iemba": {
                    "locations": {
                        "en": "Switzerland (St. Gallen), China, USA, Japan, Spain, South Africa, Italy"
                    }
                }
            }
        }
        new = {
            "programmes": {
                "iemba": {
                    "locations": {
                        "en": (
                            "Costa Rica (elective), Tokyo, Japan, New York City (elective), "
                            "St. Gallen, Switzerland, Beijing, China, UC Berkeley, USA, "
                            "UC Irvine, USA, Italy (elective), South Africa (elective), Spain (elective)"
                        )
                    }
                }
            }
        }

        stabilized = preserve_non_material_changes(old, new)
        assert stabilized["programmes"]["iemba"]["locations"]["en"] == new["programmes"]["iemba"]["locations"]["en"]
        assert diff_facts(old, stabilized) == [
            (
                "iemba.locations.en: Switzerland (St. Gallen), China, USA, Japan, Spain, South Africa, Italy"
                " -> Costa Rica (elective), Tokyo, Japan, New York City (elective), St. Gallen, "
                "Switzerland, Beijing, China, UC Berkeley, USA, UC Irvine, USA, Italy (elective), "
                "South Africa (elective), Spain (elective)"
            )
        ]

    def test_source_locations_override_incomplete_llm_extraction(self):
        from src.pipeline.update_programme_facts import (
            AllProgrammesSchema,
            BilingualText,
            DeadlineFee,
            ProgrammeFactsSchema,
            apply_deterministic_source_facts,
        )

        def programme(locations: BilingualText) -> ProgrammeFactsSchema:
            return ProgrammeFactsSchema(
                official_name="test",
                current_cohort="test",
                language=BilingualText(de="Deutsch", en="English"),
                programme_start="2026-01-01",
                duration=BilingualText(de="18 Monate", en="18 months"),
                ects_credits=75,
                structure=BilingualText(de="Struktur", en="structure"),
                locations=locations,
                first_deadline=DeadlineFee(deadline="2026-01-01", fee=1),
                final_deadline=DeadlineFee(deadline="2026-02-01", fee=2),
                advisor_name="Advisor",
                advisor_email="advisor@example.com",
                advisor_phone="+41 00 000 00 00",
            )

        extracted = AllProgrammesSchema(
            emba=programme(BilingualText(de="Schweiz", en="Switzerland")),
            iemba=programme(BilingualText(
                de="St. Gallen (Schweiz), China, USA, Japan, Spanien, Südafrika, Italien",
                en="St. Gallen (Switzerland), China, USA, Japan, Spain, South Africa, Italy",
            )),
            emba_x=programme(BilingualText(de="Zürich", en="Zurich")),
        )
        pages = {
            "emba": "",
            "iemba": """
            <div class="locations">
              <small>Orte</small>
              <ul>
                <li>Costa Rica <small class='type'>Wahlkurs</small></li>
                <li>New York City <small class='type'>Wahlkurs</small></li>
                <li>St. Gallen, Schweiz</li>
              </ul>
            </div>
            """,
        }

        result = apply_deterministic_source_facts(extracted, pages)

        assert "Costa Rica (Wahlkurs)" in result.iemba.locations.de
        assert "New York City (elective)" in result.iemba.locations.en


# --------------------------- Language detection -----------------------------

class TestLanguageHeuristics:
    """Covers ONLY the local heuristic paths — no LLM is initialized."""

    @pytest.fixture()
    def detector(self):
        from src.rag.language_detection import LanguageDetector
        return LanguageDetector()

    @pytest.mark.parametrize("query,expected", [
        ("Was kostet der EMBA und wie lange dauert das Studium?", "de"),
        ("Ich habe 10 Jahre Berufserfahrung und möchte mich weiterbilden", "de"),
        ("Können Sie mir mehr über die Studiengebühren sagen?", "de"),
        ("How much does the IEMBA cost and when does it start?", "en"),
        ("I have ten years of leadership experience in finance", "en"),
        ("What are the admission requirements for the programme?", "en"),
    ])
    def test_full_sentences_detected_locally(self, detector, query, expected):
        assert detector._heuristic_detect(query) == expected

    def test_umlauts_force_german(self, detector):
        assert detector._heuristic_detect("Zulassungsvoraussetzungen prüfen") == "de"

    def test_non_latin_script_stays_ambiguous(self, detector):
        assert detector._heuristic_detect("Сколько стоит программа MBA?") is None

    def test_ambiguous_input_returns_none(self, detector):
        # Programme names alone carry no language signal
        assert detector._heuristic_detect("EMBA IEMBA emba X") is None

    def test_model_not_initialized_by_heuristics(self, detector):
        detector._heuristic_detect("Was kostet der EMBA?")
        assert detector._model is None, "Heuristic path must not initialize the LLM"


# ------------------------------ Config flags --------------------------------

class TestConfigDefaults:
    def test_legacy_fact_router_removed(self):
        """The legacy regex fact routers were deleted entirely — neither the
        config flag nor the router methods may resurface."""
        assert not hasattr(config.chain, "ENABLE_LEGACY_FACT_ROUTER")
        from src.rag.agent_chain import ExecutiveAgentChain
        assert not hasattr(ExecutiveAgentChain, "_serve_programme_overview")
        assert not hasattr(ExecutiveAgentChain, "_extract_chf_amounts")

    def test_quality_eval_disabled(self):
        assert config.chain.EVALUATE_RESPONSE_QUALITY is False

    def test_history_cap_active(self):
        assert config.chain.MAX_HISTORY_MESSAGES > 0
