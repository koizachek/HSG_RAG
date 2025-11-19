import gradio as gr
from src.rag.agent_chain import ExecutiveAgentChain 
from src.utils.logging import get_logger, cached_log_handler

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self, language: str = 'en') -> None:
        self._language: str = language
        self._agent_chain: ExecutiveAgentChain = ExecutiveAgentChain(language=self._language)
        self._app = gr.Blocks()

        chatbot: gr.Chatbot = gr.Chatbot(
            value=[
                gr.ChatMessage(
                    role='assistant', 
                    content=self._agent_chain.generate_greeting(),
                )
            ],
            type='messages'
        )
        
        with self._app:
            with gr.Row():
                with gr.Row(scale=3):
                    gr.ChatInterface(
                        chatbot=chatbot,
                        fn=self._chat,
                        title="Executive Education Adviser",
                        type='messages',
                    )
                with gr.Row(scale=1):
                    log_window = gr.Code(
                        label='Console Log',
                        lines=30,
                        max_lines=30, 
                        show_line_numbers=False,
                    )

                    log_timer = gr.Timer(value=0.5, active=True)
                    log_timer.tick(fn=lambda: cached_log_handler.get_logs(), outputs=log_window)
        

    def _chat(self, message: str, history: list[dict]):
        answers = []
        try:
            response = self._agent_chain.query(query=message)
            logger.info("Recieved response from the agent, diplaying answer in the application")
            answers.append(response)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            answers.append("") 
        return answers


    def run(self):
        self._app.launch(share=True)
