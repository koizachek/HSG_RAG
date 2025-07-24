"""
Test script for the Executive Education Chatbot.
"""
import sys
from src.rag.chain import RAGChain

def test_chatbot():
    """Test the chatbot with a predefined message."""
    print("Testing chatbot...")
    
    # Initialize the RAG chain
    rag_chain = RAGChain()
    
    # Test queries
    test_queries = [
        "I am interested in executive education",
        "Tell me about the MBA programs",
        "What is the cost of the Executive MBA HSG?",
        "What are the admission requirements for the International Executive MBA?",
        "Where is the Executive MBA in Digital Leadership located?",
    ]
    
    # Run the queries
    for query in test_queries:
        print(f"\n\nQuery: {query}")
        try:
            result = rag_chain.query(query)
            print(f"Answer: {result['answer']}")
            
            if result['sources']:
                print("\nSources:")
                for source in result['sources']:
                    print(f"- {source['program_name']}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_chatbot()
