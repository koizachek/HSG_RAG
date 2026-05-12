from dataclasses import dataclass

from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain.agents import AgentState
from langchain_core.messages import AnyMessage


@dataclass
class AgentContext:
    agent_name: str


@dataclass
class LeadAgentQueryResponse:
    response: str
    language: str
    additional_details: str | None = None
    processed_query: str = None
    confidence_fallback: bool = False
    max_turns_reached: bool = False
    should_cache: bool = False


class StructuredAgentResponse(BaseModel):
    response: str = Field(
        description="Main response shown directly to the user."
    )

    additional_details: str = Field(
        default="",
        description=(
            "Optional secondary details shown in an expandable UI section. "
            "Use this only when answering a single programme question where the full answer "
            "would otherwise become too long. "
            "Do NOT use this for multi-programme comparisons—those must appear fully in `response`. "
            "Do NOT move critical facts such as tuition, duration, deadlines, eligibility requirements, "
            "or direct answers to the user's question into this field."
        )
    )

    is_context_dependent: bool = Field(
        default=True,
        description=(
            "Set to False only if the question can be answered without using any user-specific "
            "information (e.g. name, age, preferences, extracted profile data) and without relying "
            "on prior conversation turns or conversation history. "
            "Must be True for responses involving eligibility, recommendations, comparisons after prior turns, "
            "or any answer influenced by user profile data or conversation context."
        )
    )


class State(TypedDict):
    messages: list[AnyMessage]
    answer: str


class ConversationState(TypedDict):
    """Tracks user profile and conversation context"""
    user_id: str  # Unique session identifier
    user_language: str | None  # Locked after first message
    user_name: str | None  # User's name extracted from conversation
    experience_years: int | None  # Years of professional experience
    leadership_years: int | None  # Years of leadership experience
    field: str | None  # Professional field/industry
    interest: str | None  # Content interests
    qualification_level: str | None  # "bachelor", "master", "MBA", etc.
    program_interest: list[str]  # ["EMBA", "IEMBA", "EMBAX"]
    suggested_program: str | None  # Recommended program based on conversation
    handover_requested: bool | None  # True if appointment requested, False if declined, None if session active
    topics_discussed: list[str]  # Track what's been covered
    preferences_known: bool  # Whether we have enough context


class LeadInformationState(AgentState):
    lead_name: str
    lead_age: int
    lead_language_knowledge: list
    lead_work_experience: dict
    lead_motivation: list
    # Enhanced state tracking
    conversation_state: ConversationState
