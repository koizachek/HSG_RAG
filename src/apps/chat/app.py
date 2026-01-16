import os
import gradio as gr
from src.apps.chat.js import JS_LISTENER, JS_CLEAR
from src.const.agent_response_constants import *
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.logging import get_logger

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks(js=JS_LISTENER)
        self._language = language

        with self._app:
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
                fn=lambda msg, history, agent: self._chat(
                    message=msg,
                    history=history,
                    agent=agent,
                ),
                additional_inputs=[agent_state],
                title="Executive Education Adviser",
                type='messages',
            )

            iframe_container = gr.HTML(
                value="",
                elem_id="consultation-iframe-container",
                visible=True
            )

            def clear_chat_immediate():
                return [], ""

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
                    ""
                )

            lang_selector.change(
                fn=clear_chat_immediate,
                outputs=[chat.chatbot_value, iframe_container],
                queue=True,
                js=JS_CLEAR
            )

            lang_selector.change(
                fn=on_lang_change,
                inputs=[lang_selector],
                outputs=[agent_state, lang_state, chat.chatbot_value, iframe_container],
                queue=True,
            )

            reset_button.click(
                fn=clear_chat_immediate,
                outputs=[chat.chatbot_value, iframe_container],
                queue=True,
                js=JS_CLEAR
            )

            reset_button.click(
                fn=switch_language,
                inputs=[lang_state],
                outputs=[agent_state, lang_state, chat.chatbot_value, iframe_container],
                queue=True,
            )

            # Initialize the agent chain on the app startup
            self._app.load(
                fn=lambda: initalize_agent(self._language),
                outputs=[agent_state, chat.chatbot_value],
            )

    @property
    def app(self) -> gr.Blocks:
        """Expose underlying Gradio Blocks for external runners (e.g., HF Spaces)."""
        return self._app

    def _chat(self, message: str, history: list[dict], agent: ExecutiveAgentChain):
        if agent is None:
            logger.error("Agent not initialized")
            return ["I apologize, but the chatbot is not properly initialized."]

        answers = []
        try:
            logger.info(f"Processing user query: {message[:100]}...")

            lead_resp: LeadAgentQueryResponse = agent.query(query=message)
            answers.append(lead_resp.response)
            self._language = lead_resp.language

            if lead_resp.confidence_fallback or lead_resp.max_turns_reached:
                answers.extend(APPOINTMENT_LINKS[self._language])

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
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
