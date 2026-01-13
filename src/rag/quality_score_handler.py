from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langsmith import Client
from src.rag.models import ModelConfigurator as modconf
from src.rag.prompts import PromptConfigurator as promptconf

from src.utils.logging import get_logger

from time import perf_counter

logger = get_logger('quality_score_handler')

class QualityEvaluationResult(BaseModel):
    """Result of response quality evaluation."""

    overall_score:           float = Field(description='Overall response rating')
    format_adherence_score:  float = Field(description='Format adherence score')
    context_awareness_score: float = Field(description='Context awareness score')
    pricing_adherence_score: float = Field(description='Pricing guidelines adherence score')
    scope_compliance_score:  float = Field(description='Scope compliance score')
    general_rules_score:     float = Field(description='General rules score')
    comment:                 str   = Field(description='Brief explanation')


class QualityScoreHandler:
    def __init__(self) -> None:
        self._smith_client = Client()
        self._model = modconf.get_confidence_scoring_model()
        self._model = self._model.with_structured_output(QualityEvaluationResult)


    def evaluate_response_quality(self, query: str, response: str) -> QualityEvaluationResult:
        prompt = promptconf.get_quality_scoring_prompt(query, response)
        messages = [HumanMessage(prompt)]
        
        try:
            time_start = perf_counter()
            logger.info("Evaluating the response quality...")
            evaluation: QualityEvaluationResult = self._model.invoke(messages)
            time_elapsed = perf_counter() - time_start
            logger.info(f"Finished confidence evaluation in {time_elapsed:1.3} sec")

            evaluation.overall_score = sum([
                evaluation.format_adherence_score,
                evaluation.context_awareness_score, 
                evaluation.pricing_adherence_score,
                evaluation.scope_compliance_score,
                evaluation.general_rules_score, 
            ]) / 5.0
            
            logger.info(f"- scoring: {evaluation.overall_score:1.2f}")
            logger.info(f"- comment: {evaluation.comment}")

            return evaluation
        except Exception as e:
            logger.error(f"Failed to evaluate the response's confidence: {e}")
            return QualityEvaluationResult()
