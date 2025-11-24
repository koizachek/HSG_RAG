from dataclasses import dataclass, field
from typing_extensions import TypedDict
from langchain.agents import AgentState
from langchain_core.messages import AnyMessage

@dataclass
class AgentContext:
    agent_name: str

class State(TypedDict):
    messages: list[AnyMessage]
    answer: str


class ConversationState(TypedDict):
    """Tracks user profile and conversation context"""
    user_language: str | None  # Locked after first message
    user_name: str | None
    years_experience: int | None
    qualification_level: str | None  # "bachelor", "master", "MBA", etc.
    program_interest: list[str]  # ["EMBA", "IEMBA", "EMBAX"]
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
