from pydantic import BaseModel, Field


class RetrieveContextInput(BaseModel):
    query: str = Field(
        description=(
            "Search query for current programme context. Use the same language as "
            "in the parameter 'language'."
        )
    )
    program: str = Field(
        description=(
            "Programme identifier to retrieve context for. Expected values are "
            "'emba', 'iemba', or 'emba x'."
        )
    )
    language: str | None = Field(
        default=None,
        description="Must be set to 'en' for programs IEMBA and emba x. Must be set to 'de' for program EMBA HSG.",
    )


class ProgrammeAgentInput(BaseModel):
    query: str = Field(
        description=(
            "Question or user context to pass to the programme-specific support "
            "agent. Include relevant profile details when available."
        )
    )
