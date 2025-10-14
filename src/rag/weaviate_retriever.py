from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from src.database.weavservice import WeaviateService
from src.utils.logging import get_logger
from typing import List 

logger = get_logger("weaviate_retriever")

class WeaviateRetriever(BaseRetriever):
    """Custom retriever for the implementation of the Weaviate serivce."""

    
    def __init__(self, language: str, top_k: int = 5):
        super().__init__()
        self._weaviate_service = WeaviateService()
        self._language = language
        self._top_k = top_k 


    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        """Retrieves the relevant documents from the Weaviate database."""

        try:
            response, elapsed = self._weaviate_service.query(
                query=query,
                lang=self._language,
                limit=self._top_k,
            )
            logger.info(f"Finished retrieving from the database in {elapsed:2.2f} seconds")

            documents = []
            if not response: return documents

            for obj in response.objects:
                doc = Document(
                    page_content=obj.properties.get("body", ""),
                    metadata={
                        "program_id": obj.properties.get("chunk_id", ""),
                        "program_name": obj.properties.get("source", ""),
                        "document_id": obj.properties.get("document_id", ""),
                        "source": obj.properties.get("source", ""),
                        "date": obj.properties.get("date", ""),
                        "programs": obj.properties.get("programs", []),
                        "distance": obj.metadata.distance if hasattr(obj, 'metadata') else None
                    }
                )
                documents.append(doc)
            
            return documents
        except Exception as e:
            logger.error(f"Error retrieving from Weaviate: {e}")
            return []
