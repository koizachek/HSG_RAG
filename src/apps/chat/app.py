import gradio as gr
from src.rag.agent_chain import ExecutiveAgentChain 
from src.utils.logging import get_logger, cached_log_handler

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self, language: str = 'de') -> None:
        self._app = gr.Blocks()
     
        with self._app:
            # Initial state variables
            agent_state = gr.State(None)
            lang_state  = gr.State(language)
            
            with gr.Row():
                lang_selector = gr.Radio(
                    choices=["Deutsch", "English"],
                    value="English" if language == 'en' else 'Deutsch',
                    label="Selected Language",
                    interactive=True,
                )
                reset_button = gr.Button("Reset Conversation")
                            
            chatbot: gr.Chatbot = gr.Chatbot(
                value=[],
                type='messages'
            )
            
            gr.ChatInterface(
                chatbot=chatbot,
                fn=lambda msg, history, agent: self._chat( 
                    message=msg,
                    history=history,
                    agent=agent,
                ),
                additional_inputs=[agent_state],
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
                return agent, greeting

            def switch_language(new_language):
                new_agent, greeting = initalize_agent(new_language)
                return (
                    new_agent,
                    new_language,
                    [{"role": "assistant", "content": greeting}]
                )
            
            lang_selector.change(
                fn=clear_chat_immediate,
                outputs=[chatbot],
                queue=False,
            )

            lang_selector.change(
                fn=on_lang_change,
                inputs=[lang_selector],
                outputs=[agent_state, lang_state, chatbot],
                queue=True,
            )

            reset_button.click(
                fn=clear_chat_immediate,
                outputs=[chatbot],
                queue=False,
            )

            reset_button.click(
                fn=lambda: switch_language(lang_state.value),
                outputs=[agent_state, lang_state, chatbot],
                queue=False,
            )

            # Initialize the agent for the selected language 
            initial_agent, initial_greeting = initalize_agent(language)
            agent_state.value = initial_agent 
            chatbot.value = [{"role": "assistant", "content": initial_greeting}]
 

    def _chat(self, message: str, history: list[dict], agent: ExecutiveAgentChain):
        if agent is None:
            return "Error: Agent not initialized!"
        answers = []
        try:
            response = agent.query(query=message)
            logger.info("Recieved response from the agent, diplaying answer in the application")
            answers.append(response)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            answers.append("") 
        return answers


    def run(self):
        self._app.launch(share=False)
