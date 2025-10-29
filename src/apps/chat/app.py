import gradio as gr
from src.rag.agent_chain import ExecutiveAgentChain 
from src.utils.logging import get_logger

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self, language: str = 'en') -> None:
        self._language: str = language
        self._agent_chain: ExecutiveAgentChain = ExecutiveAgentChain(language=self._language)
        
        chatbot: gr.Chatbot = gr.Chatbot(
            value=[
                gr.ChatMessage(
                    role='assistant', 
                    content=self._agent_chain.generate_greeting()
                )
            ],
            type='messages'
        )

        self._interface = gr.ChatInterface(
            chatbot=chatbot,
            fn=self._chat,
            title="Executive Education Adviser",
            type='messages'
        )
    


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
        self._interface.launch()
