"""
Vector database for storing and retrieving program embeddings.
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional

import chromadb
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from config import (
    PROCESSED_DATA_PATH,
    VECTORDB_PATH,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VectorDatabase:
    """Vector database for storing and retrieving program embeddings."""

    def __init__(
        self,
        input_path: str = PROCESSED_DATA_PATH,
        db_path: str = VECTORDB_PATH,
        collection_name: str = "programs",
    ):
        """
        Initialize the vector database.

        Args:
            input_path: Path to the processed data file.
            db_path: Path to the vector database.
            collection_name: Name of the collection to store embeddings.
        """
        self.input_path = input_path
        self.db_path = db_path
        self.collection_name = collection_name
        
        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=OPENAI_API_KEY,
        )
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"Using existing collection: {collection_name}")
        except ValueError:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "The EMBA HSG is an advanced General Management programme"}
            )
            logger.info(f"Created new collection: {collection_name}")

    def load_data(self) -> List[Dict[str, Any]]:
        """
        Load processed data from the input file and filter to only include Executive MBA HSG.

        Returns:
            A list of dictionaries containing program data for Executive MBA HSG only.
        """
        try:
            with open(self.input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Filter to only include Executive MBA HSG
            filtered_data = [program for program in data if program.get("name") == "Executive MBA HSG"]
            
            logger.info(f"Loaded and filtered to {len(filtered_data)} programs (Executive MBA HSG only) from {self.input_path}")
            return filtered_data
        except Exception as e:
            logger.error(f"Error loading data from {self.input_path}: {e}")
            return []

    def prepare_documents(self, programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare documents for embedding.

        Args:
            programs: List of program data.

        Returns:
            A list of documents ready for embedding.
        """
        documents = []
        
        for program in programs:
            # Create a comprehensive text representation of the program
            program_text = self._create_program_text(program)
            
            # Split the text into chunks
            chunks = self.text_splitter.split_text(program_text)
            
            # Create a document for each chunk
            for i, chunk in enumerate(chunks):
                doc_id = f"{program['program_id']}_{i:03d}"
                
                document = {
                    "id": doc_id,
                    "text": chunk,
                    "program_id": program["program_id"],
                    "program_name": program["name"],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                
                documents.append(document)
        
        logger.info(f"Prepared {len(documents)} documents from {len(programs)} programs")
        return documents

    def _create_program_text(self, program: Dict[str, Any]) -> str:
        """
        Create a comprehensive text representation of a program.

        Args:
            program: Program data.

        Returns:
            A text representation of the program.
        """
        sections = []
        
        # Program name and description
        sections.append(f"Program: {program['name']}")
        if program.get("description"):
            sections.append(f"Description: {program['description']}")
        
        # Duration
        duration = program.get("duration", {})
        if duration.get("original_text") and duration["original_text"] != "Not specified":
            sections.append(f"Duration: {duration['original_text']}")
        
        # Costs
        costs = program.get("costs", {})
        if costs.get("original_text") and costs["original_text"] != "Not specified":
            sections.append(f"Costs: {costs['original_text']}")
        
        # Curriculum
        curriculum = program.get("curriculum", [])
        if curriculum:
            sections.append("Curriculum:")
            for item in curriculum:
                sections.append(f"- {item}")
        
        # Admission requirements
        requirements = program.get("admission_requirements", [])
        if requirements:
            sections.append("Admission Requirements:")
            for item in requirements:
                sections.append(f"- {item}")
        
        # Schedules
        if program.get("schedules") and program["schedules"] != "Not specified":
            sections.append(f"Schedules: {program['schedules']}")
        
        # Faculty
        faculty = program.get("faculty", [])
        if faculty:
            sections.append("Faculty:")
            for member in faculty:
                name = member.get("name", "")
                title = member.get("title", "")
                if name and title:
                    sections.append(f"- {name}, {title}")
                elif name:
                    sections.append(f"- {name}")
        
        # Deadlines
        if program.get("deadlines") and program["deadlines"] != "Not specified":
            sections.append(f"Application Deadlines: {program['deadlines']}")
        
        # Language
        if program.get("language") and program["language"] != "Not specified":
            sections.append(f"Language: {program['language']}")
        
        # Location
        if program.get("location") and program["location"] != "Not specified":
            sections.append(f"Location: {program['location']}")
        
        # URL
        if program.get("url"):
            sections.append(f"More Information: {program['url']}")
        
        # Join all sections with double newlines
        return "\n\n".join(sections)

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """
        Add documents to the vector database.

        Args:
            documents: List of documents to add.
        """
        # Prepare data for ChromaDB
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [{k: v for k, v in doc.items() if k != "text"} for doc in documents]
        
        # Generate embeddings using OpenAI
        try:
            embeddings = self.embeddings.embed_documents(texts)
            
            # Add documents in batches to avoid memory issues
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                batch_end = min(i + batch_size, len(documents))
                batch_ids = ids[i:batch_end]
                batch_texts = texts[i:batch_end]
                batch_metadatas = metadatas[i:batch_end]
                batch_embeddings = embeddings[i:batch_end]
                
                try:
                    self.collection.add(
                        ids=batch_ids,
                        documents=batch_texts,
                        metadatas=batch_metadatas,
                        embeddings=batch_embeddings,
                    )
                    logger.info(f"Added batch of {len(batch_ids)} documents to the vector database")
                except Exception as e:
                    logger.error(f"Error adding documents to vector database: {e}")
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query the vector database.

        Args:
            query_text: The query text.
            n_results: Number of results to return.
            where: Filter to apply to the query.

        Returns:
            A list of matching documents.
        """
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where,
            )
            
            # Format results
            formatted_results = []
            for i in range(len(results["ids"][0])):
                formatted_results.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None,
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error querying vector database: {e}")
            return []

    def reset(self) -> None:
        """Reset the vector database by deleting and recreating the collection."""
        try:
            self.client.delete_collection(name=self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "University of St. Gallen Executive Education Programs"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error resetting vector database: {e}")

    def run(self) -> None:
        """Run the vector database setup."""
        logger.info("Starting vector database setup...")
        
        # Ensure the directory exists
        os.makedirs(self.db_path, exist_ok=True)
        
        # Reset the database
        self.reset()
        
        # Load data
        programs = self.load_data()
        if not programs:
            logger.error("No programs to add to the vector database")
            return
        
        # Prepare documents
        documents = self.prepare_documents(programs)
        
        # Add documents to the vector database
        self.add_documents(documents)
        
        logger.info("Vector database setup completed")


if __name__ == "__main__":
    vector_db = VectorDatabase()
    vector_db.run()
