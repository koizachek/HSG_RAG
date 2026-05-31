import pytest

from src.pipeline.utils.strategies_processor import (
    StrategiesProcessor,
    StrategyArguments,
)


@pytest.fixture
def strategies_processor():
    return StrategiesProcessor()


def classify_programmes(strategies_processor, file_name, file_content, chunk):
    return strategies_processor.apply_strategy(
        "programs",
        StrategyArguments(file_name, file_content, chunk),
    )


def test_shared_admissions_requirements_are_tagged_for_emba_and_iemba(strategies_processor):
    chunk = """
    Application Requirements
    In order to apply to the Executive MBA HSG programmes, candidates must fulfil the following requirements:
    - Hold a recognised undergraduate degree
    - Have a minimum 5 years of working experience*
    - Have a minimum 3 years of managerial / leadership experience
    - Fluency on the language of the programme (German or English)
    For emba X programme application requirements click
    Programme of Interest *
    Executive MBA HSG (german-speaking programme)
    International EMBA HSG (english-speaking programme)
    EMBA ETH Zurich + University of St.Gallen
    """

    programmes = classify_programmes(
        strategies_processor,
        "https://emba.unisg.ch/en/admissions/process",
        chunk,
        chunk,
    )

    assert programmes == ["emba", "iemba"]


def test_shared_emba_host_does_not_boost_emba_hsg(strategies_processor):
    programmes = classify_programmes(
        strategies_processor,
        "https://emba.unisg.ch/en/admissions/process",
        "",
        "International EMBA HSG Programme",
    )

    assert programmes == ["iemba"]


def test_program_specific_address_boosts_embax(strategies_processor):
    programmes = classify_programmes(
        strategies_processor,
        "https://embax.ch/admissions/student-profile",
        "",
        "",
    )

    assert programmes == ["emba_x"]
