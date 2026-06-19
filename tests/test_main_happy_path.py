from src.apps.chat.app import ChatbotApplication
from src.rag.utilclasses import LeadAgentQueryResponse


class UserFacingFakeAgent:
    def __init__(self):
        self.received_messages = []
        self.reset_called = False

    def query(self, message, on_delta=None):
        self.received_messages.append(message)

        if on_delta:
            on_delta("The IEMBA HSG ")
            on_delta("tuition fee is CHF 85'000.")

        return LeadAgentQueryResponse(
            response="The IEMBA HSG tuition fee is CHF 85'000.",
            additional_details="The next application deadline is 31 May 2026.",
            language="en",
            processed_query=message,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["iemba"],
        )

    def reset_conversation_state(self):
        self.reset_called = True


def test_user_can_ask_programme_price_and_receive_streamed_chat_answer():
    app = ChatbotApplication(language="en")
    agent = UserFacingFakeAgent()

    outputs = list(app._chat(
        message="How much does the IEMBA cost?",
        history=[{"role": "assistant", "content": "Hello and welcome."}],
        agent=agent,
    ))

    streamed_text = [value for value, returned_agent in outputs[:-1]]
    final_answer, returned_agent = outputs[-1]

    assert streamed_text == [
        "The IEMBA HSG ",
        "The IEMBA HSG tuition fee is CHF 85'000.",
    ]
    assert final_answer[0] == "The IEMBA HSG tuition fee is CHF 85'000."
    assert "More information" in final_answer[1].value
    assert "31 May 2026" in final_answer[1].value
    assert returned_agent is agent
    assert agent.received_messages == ["How much does the IEMBA cost?"]
    assert agent.reset_called is False
    assert app._language == "en"
