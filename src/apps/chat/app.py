import os
import uuid
import gradio as gr

from src.const.agent_response_constants import *
from src.const.data_consent_constants import *
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.logging import get_logger
from src.cache.cache import Cache

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self, language: str = "de") -> None:
        self._app = gr.Blocks()
        self._language = language
        self._cache = Cache.get_cache()

        with self._app:
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
                reset_button = gr.Button("Reset Conversation", visible)

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
                        message=msg, history=history, agent=agent
                    ),
                    additional_inputs=[agent_state],
                    title="Executive Education Adviser",
                    type="messages",
                )


            def initialize_agent(lang: str):
                agent = ExecutiveAgentChain(language=lang)
                greeting = agent.generate_greeting()
                return agent, [{"role": "assistant", "content": greeting}]

            def label_to_lang_code(label: str) -> str:
                return "en" if label == "English" else "de"

            # Language change: before consent => only update consent UI text.
            # After consent: keep chat running (or optionally re-init agent on language change).
            def on_language_change(language_label: str, consent_given: bool, agent):
                lang_code = label_to_lang_code(language_label)

                # Vor Consent: nur Consent-UI updaten
                if not consent_given:
                    return (
                        lang_code,
                        gr.update(value=PRIVACY_NOTICE[lang_code]),
                        gr.update(value=DECLINE[lang_code]),
                        gr.update(value=ACCEPT[lang_code]),
                        gr.update(visible=False, value=""),
                        None,   # agent_state bleibt None
                        None,   # chat bleibt wie es ist
                    )

                # After consent
                new_agent, greeting = initialize_agent(lang_code)
                return (
                    lang_code,
                    None,
                    None,
                    None,
                    None,
                    new_agent,
                    greeting,  # das ist der “reset” (nur Greeting)
                )


            def on_accept(lang: str):
                agent, greeting = initialize_agent(lang)
                self._language = lang
                return (
                    gr.update(visible=False),  # consent_screen hide
                    gr.update(visible=True),   # chat_screen show
                    True,                      # consent_state
                    agent,                     # agent_state
                    greeting,                  # chat initial history
                    gr.update(visible=False, value=""),  
                )

            def on_decline(lang: str):
                self._language = lang
                return (
                    gr.update(visible=True),   # consent_screen stays
                    gr.update(visible=False),  # chat_screen stays hidden
                    False,                     # consent_state
                    None,                      # agent_state
                    [],                        # chat history empty
                    gr.update(visible=True, value=DECLINE_MESSAGE[lang]),
                )

            def on_reset(lang: str):
                self._language = lang
                return (
                    gr.update(visible=True),   # consent_screen
                    gr.update(visible=False),  # chat_screen
                    False,                     # consent_state
                    None,                      # agent_state
                    [],                        # chat history
                    gr.update(value=PRIVACY_NOTICE[lang]),
                    gr.update(value=DECLINE[lang]),
                    gr.update(value=ACCEPT[lang]),
                    gr.update(visible=False, value=""),
                    str(uuid.uuid4()),         # new session id
                )

            # Language switch updates consent UI if consent not given
            lang_selector.change(
                fn=on_language_change,
                inputs=[lang_selector, consent_state, agent_state],
                outputs=[lang_state, data_policy, decline_btn, accept_btn, decline_info, agent_state, chat.chatbot_value],
                queue=True,
            )
            
            # Accept/Decline data consent
            accept_btn.click(
                fn=on_accept,
                inputs=[lang_state],
                outputs=[consent_screen, chat_screen, consent_state, agent_state, chat.chatbot_value, decline_info],
                queue=True,
            )

            decline_btn.click(
                fn=on_decline,
                inputs=[lang_state],
                outputs=[consent_screen, chat_screen, consent_state, agent_state, chat.chatbot_value, decline_info],
                queue=True,
            )

            # Reset
            reset_button.click(
                fn=on_reset,
                inputs=[lang_state],
                outputs=[
                    consent_screen,
                    chat_screen,
                    consent_state,
                    agent_state,
                    chat.chatbot_value,
                    data_policy,
                    decline_btn,
                    accept_btn,
                    decline_info,
                    session_id_state,
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

            preprocess_resp = agent.preprocess_query(message)
            final_response: LeadAgentQueryResponse = None

            current_lang = preprocess_resp.language
            processed_q = preprocess_resp.processed_query

            if preprocess_resp.response:
                # Response comes from preprocessing step
                final_response = preprocess_resp

            elif Cache._settings["enabled"]:
                cached_data = self._cache.get(processed_q, language=current_lang)

                if cached_data:
                    # Cache Hit — restore response with metadata
                    if isinstance(cached_data, dict):
                        final_response = LeadAgentQueryResponse(
                            response=cached_data["response"],
                            language=current_lang,
                            appointment_requested=cached_data.get("appointment_requested", False),
                            relevant_programs=cached_data.get("relevant_programs", []),
                        )
                    else:
                        # Legacy: plain string cache entry
                        final_response = LeadAgentQueryResponse(
                            response=cached_data,
                            language=current_lang,
                        )

            if not final_response:
                # Response needs to be generated by the agent
                final_response = agent.agent_query(processed_q)

            answers.append(final_response.response)
            self._language = final_response.language

            if final_response.confidence_fallback or final_response.max_turns_reached or final_response.appointment_requested:
                html_code = get_booking_widget(language=self._language, programs=final_response.relevant_programs)
                answers.append(gr.HTML(value=html_code))

            if final_response.should_cache and Cache._settings["enabled"]:
                # Caching response with metadata
                self._cache.set(
                    key=processed_q,
                    value={
                        "response": final_response.response,
                        "appointment_requested": final_response.appointment_requested,
                        "relevant_programs": final_response.relevant_programs,
                    },
                    language=current_lang
                )

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
