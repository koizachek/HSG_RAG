import os
import gradio as gr
from src.rag.agent_chain import ExecutiveAgentChain 
from src.utils.logging import get_logger, cached_log_handler

logger = get_logger("chatbot_app")

CSS_PATH = "frontend/style.css"

class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks()       
        
        with self._app:
            # Initial state variables
            agent_state = gr.State(None)
            
            lang_storage = gr.BrowserState(language)
            chat_storage = gr.BrowserState(None)
             
            reset_button = gr.Button("Reset Conversation")
            
            # Chat interface
            with gr.Column():
                chatbot = gr.Chatbot(show_label=False)
                chat_interface = gr.ChatInterface(
                    fn=lambda msg, history, agent: self._chat( 
                        message=msg,
                        history=history,
                        agent=agent,
                    ),
                    chatbot=chatbot,
                    additional_inputs=[agent_state],
                    title="Executive Education Adviser",
                    #type='messages',
                )
                
                lang_selector = gr.Radio(
                    choices=["DE", "EN"],
                    value=language.upper(),
                    interactive=True,
                    show_label=False,
                    container=False,
                    elem_id="lang-toggle",
                )

            
            def clear_chat_immediate():
                return [], None
            
            def on_lang_change(language):
                lang_code = language.lower()
                return switch_language(lang_code)
            
            def initalize_agent(language):
                agent = ExecutiveAgentChain(language=language)
                greeting = agent.generate_greeting()
                return agent, [text_msg("assistant", greeting)]
            
            def init_session(saved_lang, saved_chat):
                lang = (saved_lang or language).lower()
                agent = ExecutiveAgentChain(language=lang)

                if saved_chat:
                    history = saved_chat
                else:
                    greeting = agent.generate_greeting()
                    history = [text_msg("assistant", greeting)]

                return agent, lang.upper(), history, history

            def switch_language(new_language):
                new_agent, greeting = initalize_agent(new_language)
                return (
                    new_agent,
                    new_language,
                    greeting,
                )
            
            def text_msg(role: str, text: str):
                return {"role": role, "content": [{"type": "text", "text": text}]}
            
            lang_selector.input(
                fn=clear_chat_immediate,
                outputs=[chatbot, chat_storage],
                queue=True,
            )

            lang_selector.input(
                fn=on_lang_change,
                inputs=[lang_selector],
                outputs=[agent_state, lang_storage, chatbot],
                queue=True,
            )

            reset_button.click(
                fn=clear_chat_immediate,
                outputs=[chatbot, chat_storage],
                queue=True,
            )

            reset_button.click(
                fn=switch_language,
                inputs=[lang_storage],
                outputs=[agent_state, lang_storage, chatbot],
                queue=True,
            )
            
            @gr.on([lang_selector.input], inputs=[lang_selector], outputs=[lang_storage])
            def save_to_local_storage(selected_lang):
                return selected_lang

            @gr.on([chatbot.change], inputs=[chatbot], outputs=[chat_storage])
            def save_chat_to_chat_storage(curr_chat):
                return curr_chat

            self._app.load(
                fn=init_session,
                inputs=[lang_storage, chat_storage],
                outputs=[agent_state, lang_selector, chatbot, chat_interface.chatbot_value],
            )

    @property
    def app(self) -> gr.Blocks:
        """Expose underlying Gradio Blocks for external runners (e.g., HF Spaces)."""
        return self._app

    def _chat(self, message: str, history, agent: ExecutiveAgentChain):
        if agent is None:
            logger.error("Agent not initialized")
            return "I apologize, but the chatbot is not properly initialized. Please refresh the page or contact support."
    
        try:
            # Log user input
            logger.info(f"Processing user query: {message[:100]}...")
            
            # Query agent (now includes input handling, scope checking, and formatting)
            response = agent.query(query=message)
            
            logger.info(f"Received and formatted response from agent ({len(response)} chars)")
            return response
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return (
                "I apologize, but I encountered an error processing your request. "
                "Please try rephrasing your question or contact our admissions team for assistance."
            )


    def run(self):
        self._app.launch(
            share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
            server_name=os.getenv("SERVER_NAME", "0.0.0.0"),
            server_port=int(os.getenv("PORT", 7860)),
            css_paths=[CSS_PATH] if os.path.exists(CSS_PATH) else None,
        )
