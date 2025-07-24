"""
RAG chain implementation using LangChain.
"""
import logging
from typing import Dict, List, Any, Optional, Tuple

from langchain.chains import ConversationalRetrievalChain
from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from config import (
    VECTORDB_PATH,
    CHAT_MODEL,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    TOP_K_RETRIEVAL,
)
from src.rag.prompts import (
    RAG_PROMPT,
    STANDALONE_PROMPT,
    CONDENSE_QUESTION_PROMPT,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RAGChain:
    """RAG chain implementation using LangChain."""

    def __init__(
        self,
        vectordb_path: str = VECTORDB_PATH,
        collection_name: str = "programs",
        model_name: str = CHAT_MODEL,
        openai_api_key: str = OPENAI_API_KEY,
        embedding_model: str = EMBEDDING_MODEL,
        top_k: int = TOP_K_RETRIEVAL,
    ):
        """
        Initialize the RAG chain.

        Args:
            vectordb_path: Path to the vector database.
            collection_name: Name of the collection to use.
            model_name: Name of the chat model to use.
            openai_api_key: OpenAI API key.
            embedding_model: Name of the embedding model to use.
            top_k: Number of documents to retrieve for each query.
        """
        self.vectordb_path = vectordb_path
        self.collection_name = collection_name
        self.model_name = model_name
        self.openai_api_key = openai_api_key
        self.embedding_model = embedding_model
        self.top_k = top_k
        
        # Initialize components
        self.embeddings = self._init_embeddings()
        self.vectorstore = self._init_vectorstore()
        self.llm = self._init_llm()
        self.memory = self._init_memory()
        self.retriever = self._init_retriever()
        self.chain = self._init_chain()

    def _init_embeddings(self) -> OpenAIEmbeddings:
        """Initialize the embeddings model."""
        return OpenAIEmbeddings(
            model=self.embedding_model,
            openai_api_key=self.openai_api_key,
        )

    def _init_vectorstore(self) -> Chroma:
        """Initialize the vector store."""
        return Chroma(
            persist_directory=self.vectordb_path,
            embedding_function=self.embeddings,
            collection_name=self.collection_name,
        )

    def _init_llm(self) -> BaseChatModel:
        """Initialize the language model."""
        return ChatOpenAI(
            model=self.model_name,
            openai_api_key=self.openai_api_key,
            temperature=0.2,
        )

    def _init_memory(self) -> ConversationBufferMemory:
        """Initialize the conversation memory."""
        return ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer",
        )

    def _init_retriever(self) -> Any:
        """Initialize the retriever with contextual compression."""
        return self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": self.top_k},
        )

    def _format_chat_history(self, chat_history: List[Tuple[str, str]]) -> str:
        """
        Format chat history for the condense question prompt.

        Args:
            chat_history: List of (human, ai) message tuples.

        Returns:
            Formatted chat history string.
        """
        formatted_history = ""
        for i, (human, ai) in enumerate(chat_history):
            formatted_history += f"Human: {human}\nAI: {ai}\n"
        return formatted_history.strip()

    def _get_source_documents(self, docs: List[Document]) -> List[Dict[str, Any]]:
        """
        Extract source information from retrieved documents.

        Args:
            docs: List of retrieved documents.

        Returns:
            List of source information dictionaries.
        """
        sources = []
        seen_programs = set()
        
        for doc in docs:
            if not hasattr(doc, "metadata"):
                continue
            
            program_id = doc.metadata.get("program_id")
            program_name = doc.metadata.get("program_name")
            
            if program_id and program_name and program_id not in seen_programs:
                sources.append({
                    "program_id": program_id,
                    "program_name": program_name,
                })
                seen_programs.add(program_id)
        
        return sources

    def _init_chain(self) -> BaseConversationalRetrievalChain:
        """Initialize the conversational retrieval chain."""
        # Create a chain for condensing the question based on chat history
        condense_question_chain = (
            ChatPromptTemplate.from_template(CONDENSE_QUESTION_PROMPT.template)
            | self.llm
            | StrOutputParser()
        )
        
        # Create a chain for answering the question based on retrieved documents
        qa_chain = (
            {
                "context": lambda x: x["context"],
                "question": lambda x: x["question"],
            }
            | ChatPromptTemplate.from_template(RAG_PROMPT.template)
            | self.llm
            | StrOutputParser()
        )
        
        # Create a chain for answering when no relevant documents are found
        standalone_chain = (
            {
                "question": lambda x: x["question"],
            }
            | ChatPromptTemplate.from_template(STANDALONE_PROMPT.template)
            | self.llm
            | StrOutputParser()
        )
        
        # Define a function to determine whether to use retrieved documents or standalone
        def route_based_on_docs(inputs):
            if not inputs.get("context") or len(inputs["context"]) == 0:
                return standalone_chain
            return qa_chain
        
        # Create the final conversational retrieval chain
        chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=self.retriever,
            memory=self.memory,
            condense_question_prompt=CONDENSE_QUESTION_PROMPT,
            combine_docs_chain_kwargs={"prompt": RAG_PROMPT},
            return_source_documents=True,
            output_key="answer",
        )
        
        return chain

    def query(
        self,
        query: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Query the RAG chain.

        Args:
            query: The query text.
            chat_history: Optional chat history as a list of (human, ai) message tuples.

        Returns:
            A dictionary containing the response and source documents.
        """
        if chat_history is None:
            chat_history = []
        
        try:
            # Run the chain
            result = self.chain.invoke(
                {"question": query, "chat_history": chat_history}
            )
            
            # Extract source documents
            source_docs = result.get("source_documents", [])
            sources = self._get_source_documents(source_docs)
            
            return {
                "answer": result["answer"],
                "sources": sources,
                "source_documents": source_docs,
            }
        except Exception as e:
            logger.error(f"Error querying RAG chain: {e}")
            return {
                "answer": "I'm sorry, I encountered an error while processing your question. Please try again.",
                "sources": [],
                "source_documents": [],
            }

    def add_message_to_memory(self, human_message: str, ai_message: str) -> None:
        """
        Add a message pair to the conversation memory.

        Args:
            human_message: The human message.
            ai_message: The AI message.
        """
        self.memory.chat_memory.add_user_message(human_message)
        self.memory.chat_memory.add_ai_message(ai_message)

    def get_chat_history(self) -> List[Tuple[str, str]]:
        """
        Get the chat history from memory.

        Returns:
            A list of (human, ai) message tuples.
        """
        messages = self.memory.chat_memory.messages
        history = []
        
        for i in range(0, len(messages), 2):
            if i + 1 < len(messages):
                if isinstance(messages[i], HumanMessage) and isinstance(messages[i+1], AIMessage):
                    history.append((messages[i].content, messages[i+1].content))
        
        return history

    def clear_memory(self) -> None:
        """Clear the conversation memory."""
        self.memory.clear()
