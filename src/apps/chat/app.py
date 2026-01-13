import os
import gradio as gr
from gradio import ChatMessage
from src.rag.agent_chain import ExecutiveAgentChain
from src.utils.logging import get_logger

logger = get_logger("chatbot_app")

FALLBACK_RESPONSE = {
    "en": [
        (
            "I'm sorry, but I couldn't find any information in my records that matches your request, "
            "so I can't answer it with confidence. Could you please rephrase your question?\n\n"
            "Alternatively, you can book an appointment with a student services advisor using the links below."
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
            metadata={
                "title": "Cyra von Müller, Head of Recruitment & Admissions – EMBA HSG Program"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
            metadata={
                "title": "Kristin Fuchs, Head of Recruitment & Admissions – International EMBA HSG Program"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/teyuna-giger-unisg",
            metadata={
                "title": "Teyuna Giger, Head of Recruitment & Admissions – EMBA ETH HSG (emba X) Program"
            },
        ),
    ],
    "de": [
        (
            "Es tut mir leid, aber ich konnte in meinen Unterlagen keine Informationen finden, "
            "die zu Ihrer Anfrage passen, sodass ich sie nicht mit ausreichender Sicherheit beantworten kann. "
            "Könnten Sie Ihre Frage bitte umformulieren?\n\n"
            "Alternativ können Sie über die untenstehenden Links einen Termin bei der Studienberatung buchen."
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
            metadata={
                "title": "Cyra von Müller, Leitung Rekrutierung & Zulassung – EMBA HSG Programm"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
            metadata={
                "title": "Kristin Fuchs, Leitung Rekrutierung & Zulassung – Internationales EMBA HSG Programm"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/teyuna-giger-unisg",
            metadata={
                "title": "Teyuna Giger, Leitung Rekrutierung & Zulassung – EMBA ETH HSG (emba X) Programm"
            },
        ),
    ],
}


class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks()

        with self._app:
            # Initial state variables
            agent_state = gr.State(None)
            lang_state = gr.State(language)

            with gr.Row():
                lang_selector = gr.Radio(
                    choices=["Deutsch", "English"],
                    value="English" if language == 'en' else 'Deutsch',
                    label="Selected Language",
                    interactive=True,
                )
                reset_button = gr.Button("Reset Conversation")

            chat = gr.ChatInterface(
                fn=lambda msg, history, agent, lang: self._chat(
                    message=msg,
                    history=history,
                    agent=agent,
                    language=lang,
                ),
                additional_inputs=[agent_state, lang_state],
                title="Executive Education Adviser",
                type='messages',
            )

            def clear_chat_immediate():
                return []

            def on_lang_change(language):
                lang_code = 'en' if language == 'English' else 'de'
                return switch_language(lang_code)

            def initalize_agent(language):
                agent = ExecutiveAgentChain(language=language)
                greeting = agent.generate_greeting()
                return agent, [{"role": "assistant", "content": greeting}]

            def switch_language(new_language):
                new_agent, greeting = initalize_agent(new_language)
                return (
                    new_agent,
                    new_language,
                    greeting,
                )

            lang_selector.change(
                fn=clear_chat_immediate,
                outputs=[chat.chatbot_value],
                queue=True,
            )

            lang_selector.change(
                fn=on_lang_change,
                inputs=[lang_selector],
                outputs=[agent_state, lang_state, chat.chatbot_value],
                queue=True,
            )

            reset_button.click(
                fn=clear_chat_immediate,
                outputs=[chat.chatbot_value],
                queue=True,
            )

            reset_button.click(
                fn=switch_language,
                inputs=[lang_state],
                outputs=[agent_state, lang_state, chat.chatbot_value],
                queue=True,
            )

            # Initialize the agent chain on the app startup
            self._app.load(
                fn=lambda: initalize_agent(language),
                outputs=[agent_state, chat.chatbot_value],
            )

    @property
    def app(self) -> gr.Blocks:
        """Expose underlying Gradio Blocks for external runners (e.g., HF Spaces)."""
        return self._app

    def _chat(self, message: str, history: list[dict], agent: ExecutiveAgentChain, language: str):
        if agent is None:
            logger.error("Agent not initialized")
            return [
                "I apologize, but the chatbot is not properly initialized. Please refresh the page or contact support."]

        answers = []
        try:
            # Log user input
            logger.info(f"Processing user query: {message[:100]}...")

            # Query agent (now includes input handling, scope checking, and formatting)
            structured_response = agent.query(query=message)
            response = structured_response.response
            confidence_score = structured_response.confidence_score
            logger.info(f"Evaluated Confidence Score: {confidence_score}")

            logger.info(f"Received and formatted response from agent ({len(response)} chars)")

            if confidence_score <= 0.3:
                answers.extend(FALLBACK_RESPONSE[language])
            else:
                answers.append(response)

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)

            # Provide helpful error message instead of empty string
            error_message = (
                "I apologize, but I encountered an error processing your request. "
                "Please try rephrasing your question or contact our admissions team for assistance."
            )
            answers.append(error_message)

        return answers

    def run(self):
        self._app.launch(
            share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
            server_name=os.getenv("SERVER_NAME", "0.0.0.0"),
            server_port=int(os.getenv("PORT", 7860)),
        )
