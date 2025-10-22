import gradio as gr
from src.rag.chain import RAGChain 
from src.utils.logging import get_logger
from src.utils.lang import detect_language

logger = get_logger("chatbot_app")

class ChatbotApplication:
    def __init__(self) -> None:
        self._rag_chain: RAGChain = None
        self._language: str = 'en'
        self._interface = gr.ChatInterface(
            fn=self._chat,
            title="Executive Education Adviser",
            type='messages'
        )


    def _chat(self, message: str, history: list[dict]):
        answers = []
        if not self._rag_chain:
            self._language = detect_language(message)
            logger.info(f"Setting up the RAGChain for language '{self._language}'")
            self._rag_chain = RAGChain(language=self._language)
            answers.append(f"[Language detected: {self._language}]")

        logger.info("Sending query and history to the RAG chain...")
        try:
            response = self._rag_chain.query(message, history)
            logger.info("Recieved response from RAG chain, diplaying answer in the application")
            answers.append(response['answer'])
            return answers
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            answers.append("I'm sorry, I encountered an error while processing your question. Please try again.")
            return answers


    def run(self):
        self._interface.launch()
