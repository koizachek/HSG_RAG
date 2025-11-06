from dataclasses import dataclass
from typing_extensions import TypedDict
from langchain.agents import AgentState
from langchain_core.messages import AnyMessage

@dataclass
class AgentContext:
    agent_name: str

class State(TypedDict):
    messages: list[AnyMessage]
    answer: str


class LeadInformationState(AgentState):
    lead_name: str
    lead_age:  int
    lead_language_knowledge: list 
    lead_work_experience: dict
    lead_motivation: list
