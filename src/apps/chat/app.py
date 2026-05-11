import uuid
import gradio as gr
from fastapi import FastAPI
from datetime import datetime

from src.const.agent_response_constants import *
from src.const.data_consent_constants import *
from src.rag.agent_chain import ExecutiveAgentChain
from src.utils.logging import get_logger, ConsentLogger

logger = get_logger("chatbot_app")


def init_fastapi_app(language):
    fastapi_app = FastAPI()

    @fastapi_app.get('/health')
    def healthcheck():
        from src.database.weavservice import WeaviateService
        from fastapi.responses import JSONResponse

        status = 200
        message = {'timestamp': datetime.now().isoformat()}

        try:
            message |= {
                'status': 'ok',
                'weaviate': True,
            }

            response = WeaviateService().ping(language)

            if response['status'] != 'OK':
                status = 503
                message |= {
                    'status': 'degraded',
                    'weaviate': False,
                    'error': str(response['error']),
                }

        except Exception as e:
            status = 503
            message |= {
                'status': 'down',
                'weaviate': False,
                'error': str(e),
            }

        return JSONResponse(
            status_code=status,
            content=message,
        )

    return fastapi_app


class ChatbotApplication:
    def __init__(self, language: str = "de") -> None:
        self._fastapi_app = init_fastapi_app(language)
        self._gradio_app = gr.Blocks()
        self._app = gr.mount_gradio_app(self._fastapi_app, self._gradio_app, path='/')
        self._language = language
        self._consentLogger = ConsentLogger()

        with self._gradio_app:
            agent_state = gr.State(None)
            lang_state = gr.State(language)
            consent_state = gr.State(False)
            session_id_state = gr.State(str(uuid.uuid4()))  # for consent logging later

            with gr.Row():
                lang_selector = gr.Radio(
                    choices=["Deutsch", "English"],
                    value="English" if language == "en" else "Deutsch",
                    label="Selected Language",
                    interactive=True,
                )
                reset_button = gr.Button("Reset Conversation", visible=False)

            # ---- Consent Screen (Page 1) ----
            with gr.Column(visible=True) as consent_screen:
                data_policy = gr.Markdown(PRIVACY_NOTICE[language])
                with gr.Row():
                    decline_btn = gr.Button(DECLINE[language])
                    accept_btn = gr.Button(ACCEPT[language])

                decline_info = gr.Markdown("", visible=False)

            # ---- Chat Screen (Page 2) ----
            with gr.Column(visible=False) as chat_screen:
                chat = gr.ChatInterface(
                    fn=lambda msg, history, agent: self._chat(
                        message=msg,
                        history=history,
                        agent=agent,
                    ),
                    additional_inputs=[agent_state],
                    title="Executive Education Adviser",
                    type="messages",
                )

            booking_widget = gr.HTML(
                value=BOOKING_WIDGET_HTML[language],
                visible=False,
            )

            def create_session_id() -> str:
                return str(uuid.uuid4())

            def initialize_agent(lang: str, session_id: str):
                agent = ExecutiveAgentChain(language=lang, session_id=session_id)
                greeting = agent.generate_greeting()

                disclaimer_html = get_disclaimer_widget(lang)

                return agent, [
                    {
                        "role": "assistant",
                        "content": disclaimer_html
                    },
                    {
                        "role": "assistant",
                        "content": greeting
                    }
                ]

            def label_to_lang_code(label: str) -> str:
                return "en" if label == "English" else "de"

            # Language change: before consent => only update consent UI text.
            # After consent: keep chat running (or optionally re-init agent on language change).
            def on_language_change(
                    language_label: str,
                    consent_given: bool,
                    agent,
                    session_id: str,
            ):
                lang_code = label_to_lang_code(language_label)

                # Before consent: update consent screen text to selected language
                if not consent_given:
                    return (
                        lang_code,
                        gr.update(value=PRIVACY_NOTICE[lang_code]),
                        gr.update(value=DECLINE[lang_code]),
                        gr.update(value=ACCEPT[lang_code]),
                        gr.update(visible=False, value=""),
                        None,  # agent_state stays None
                        [],  # chat stays empty
                        gr.update(value=BOOKING_WIDGET_HTML[lang_code], visible=False)
                    )

                # After consent
                new_agent, greeting = initialize_agent(lang_code, session_id=session_id)

                return (
                    lang_code,
                    gr.update(value=PRIVACY_NOTICE[lang_code]),
                    gr.update(value=DECLINE[lang_code]),
                    gr.update(value=ACCEPT[lang_code]),
                    gr.update(visible=False, value=""),
                    new_agent,
                    greeting,
                    gr.update(value=BOOKING_WIDGET_HTML[lang_code], visible=True)
                )

            def on_accept(lang: str, session_id: str):
                agent, greeting = initialize_agent(lang, session_id=session_id)
                self._consentLogger.log(session_id, "accepted", policy_version="1.0")
                self._language = lang

                return (
                    gr.update(visible=False),  # consent_screen hide
                    gr.update(visible=True),  # chat_screen show
                    True,  # consent_state
                    agent,  # agent_state
                    greeting,  # chat initial history
                    gr.update(visible=False, value=""),  # decline_info hide
                    gr.update(visible=True),  # show reset_button
                    gr.update(value=BOOKING_WIDGET_HTML[lang], visible=True)
                )

            def on_decline(lang: str, session_id: str):
                self._language = lang
                self._consentLogger.log(session_id, "declined", policy_version="1.0")

                return (
                    gr.update(visible=True),  # consent_screen stays
                    gr.update(visible=False),  # chat_screen stays hidden
                    False,  # consent_state
                    None,  # agent_state
                    [],  # chat history empty
                    gr.update(visible=True, value=DECLINE_MESSAGE[lang]),
                    gr.update(visible=False),  # hide reset_button
                    gr.update(
                        choices=[BOOK_TEXT[lang]],
                        value=BOOK_TEXT[lang],
                        visible=False,
                    ),
                    gr.update(
                        value=BOOKING_WIDGET_HTML[lang],
                        visible=False,
                    ),
                )

            def on_reset_chat(lang: str, session_id: str):
                agent, greeting = initialize_agent(lang, session_id=session_id)
                self._language = lang

                return (
                    agent,
                    greeting,
                    gr.update(
                        choices=[BOOK_TEXT[lang]],
                        value=BOOK_TEXT[lang],
                        visible=True,
                    ),
                    gr.update(
                        value=BOOKING_WIDGET_HTML[lang],
                        visible=True,
                    ),
                )

            # Language switch updates consent UI if consent not given
            lang_selector.change(
                fn=on_language_change,
                inputs=[lang_selector, consent_state, agent_state, session_id_state],
                outputs=[
                    lang_state,
                    data_policy,
                    decline_btn,
                    accept_btn,
                    decline_info,
                    agent_state,
                    chat.chatbot_value,
                    booking_widget,
                ],
                queue=True,
            )

            # Accept/Decline data consent
            accept_btn.click(
                fn=on_accept,
                inputs=[lang_state, session_id_state],
                outputs=[
                    consent_screen,
                    chat_screen,
                    consent_state,
                    agent_state,
                    chat.chatbot_value,
                    decline_info,
                    reset_button,
                    booking_widget,
                ],
                queue=True,
            )

            decline_btn.click(
                fn=on_decline,
                inputs=[lang_state, session_id_state],
                outputs=[
                    consent_screen,
                    chat_screen,
                    consent_state,
                    agent_state,
                    chat.chatbot_value,
                    decline_info,
                    reset_button,
                    booking_widget,
                ],
                queue=True,
            )

            # Reset
            reset_button.click(
                fn=on_reset_chat,
                inputs=[lang_state, session_id_state],
                outputs=[
                    agent_state,
                    chat.chatbot_value,
                    booking_widget,
                ],
                queue=True,
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
            response = agent.query(message)
            self._language = response.language

            answers.append(response.response)

            if response.additional_details:
                details_label = (
                    "Weitere Informationen"
                    if response.language == "de"
                    else "More information"
                )

                # Remove leading/trailing whitespace/newlines from LLM output
                clean_details = response.additional_details.strip()

                # Convert line breaks into HTML breaks
                formatted_details = clean_details.replace("\n", "<br>")

                details_html = f"""
                <details style="
                    margin-top:10px;
                    padding:12px;
                    border:1px solid #374151;
                    border-radius:8px;
                    background:#1f2937;
                    color:#f9fafb;
                ">
                    <summary style="
                        cursor:pointer;
                        font-weight:600;
                        color:#93c5fd;
                        list-style:none;
                    ">
                        {details_label}
                    </summary>

                    <div style="
                        margin-top:8px;
                        color:#e5e7eb;
                        line-height:1.6;
                    ">
                        {formatted_details}
                    </div>
                </details>
                """

                answers.append(gr.HTML(value=details_html))

            return answers

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)

            return [
                "I apologize, but I encountered an error processing your request. "
                "Please try rephrasing your question or contact our admissions team for assistance."
            ]

    def run(self):
        import uvicorn

        uvicorn.run(
            self._app,
            host='0.0.0.0',
            port=7860,
            log_config=None,
        )
