import os
import gradio as gr
from config import MAX_CONVERSATION_TURNS
from src.apps.chat.constants import *
from src.rag.agent_chain import ExecutiveAgentChain
from src.utils.logging import get_logger
from utils.cache.cache import Cache

logger = get_logger("chatbot_app")

JS_LISTENER = """
function() {
    document.addEventListener('click', function(e) {
        // 1. Use .closest() to find the <a> tag even if user clicks the text/icon inside it
        const target = e.target.closest('a.appointment-btn');

        if (target) {
            // 2. Prevent the link from opening in a new tab/window
            e.preventDefault();

            // 3. Get the URL from the standard href attribute
            const url = target.getAttribute('href');
            const container = document.getElementById('consultation-iframe-container');

            if (container) {
                container.innerHTML = `
                    <div style="margin-top: 20px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
                        <div style="background: #f9fafb; padding: 10px; font-weight: bold; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between;">
                            <span>Appointment Booking</span>
                            <button onclick="document.getElementById('consultation-iframe-container').innerHTML=''" style="cursor: pointer; color: red;">✕ Close</button>
                        </div>
                        <iframe src="${url}" width="100%" height="600px" frameborder="0"></iframe>
                    </div>
                `;
                container.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
}
"""

JS_CLEAR = """
function() {
    const el = document.getElementById('consultation-iframe-container');
    if (el) {
        el.innerHTML = '';
    }
}
"""


class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks(js=JS_LISTENER)
        self._cache = Cache.get_cache_strategy()

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
            return ["I apologize, but the chatbot is not properly initialized."]

        if len(history) >= MAX_CONVERSATION_TURNS:
            response_list = [CONVERSATION_END_MESSAGE[language]]
            response_list.extend(APPOINTMENT_LINKS[language])
            return response_list

        answers = []
        try:
            logger.info(f"Processing user query: {message[:100]}...")
            
            if self._cache is not None:
                cache_key = f"{language}_response_{message}"
                cached_response = self._cache.get(cache_key)
                if cached_response:
                    logger.info("Cache hit for user query.")
                    return [cached_response]

            structured_response = agent.query(query=message)
            response = structured_response.response
            confidence_score = structured_response.confidence_score
            logger.info(f"Evaluated Confidence Score: {confidence_score}")

            if confidence_score <= 0.3:
                answers.append(FALLBACK_MESSAGE[language])
                answers.extend(APPOINTMENT_LINKS[language])
            else:
                answers.append(response)

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