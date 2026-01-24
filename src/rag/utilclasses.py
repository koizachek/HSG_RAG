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
    processed_query: str = None
    confidence_fallback: bool = False
    max_turns_reached: bool = False
    should_cache: bool = False
    appointment_requested: bool = False

class StructuredAgentResponse(BaseModel):
    response:         str   = Field(description="Main response to the query.")
    appointment_requested: bool = Field(
        default=False,
        description="Set to True ONLY if the user explicitly wants to book, asks for help booking, or if a proactive trigger (pricing/eligibility/handover) occurred in THIS specific turn. Otherwise, set to False."
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
    lead_age:  int
    lead_language_knowledge: list 
    lead_work_experience: dict
    lead_motivation: list
    # Enhanced state tracking
    conversation_state: ConversationState
