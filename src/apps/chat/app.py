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
            lang_state  = gr.State(language)
             
            reset_button = gr.Button("Reset Conversation")
            
            # Chat interface
            with gr.Column():
                chatbot = gr.Chatbot(show_label=False)
                chat = gr.ChatInterface(
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
                    value="EN" if language == 'en' else 'DE',
                    interactive=True,
                    show_label=False,
                    container=False,
                    elem_id="lang-toggle",
                )

            
            def clear_chat_immediate():
                return []
            
            def on_lang_change(language):
                lang_code = 'en' if language == 'EN' else 'de'
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

    def _chat(self, message: str, history: list[dict], agent: ExecutiveAgentChain):
        if agent is None:
            logger.error("Agent not initialized")
            return ["I apologize, but the chatbot is not properly initialized. Please refresh the page or contact support."]
        
        answers = []
        try:
            # Log user input
            logger.info(f"Processing user query: {message[:100]}...")
            
            # Query agent (now includes input handling, scope checking, and formatting)
            response = agent.query(query=message)
            
            logger.info(f"Received and formatted response from agent ({len(response)} chars)")
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
            css_paths=[CSS_PATH] if os.path.exists(CSS_PATH) else None,
        )
