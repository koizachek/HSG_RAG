"""
Command-line interface for the RAG chatbot.
"""
import os
import sys
from typing import Dict, List, Any, Optional, Tuple

import colorama
from colorama import Fore, Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from config import MAX_HISTORY
from src.rag.chain import RAGChain
from src.utils.logging import get_logger, init_logging

# Initialize colorama
colorama.init()

init_logging(interactive_mode=False)
logger = get_logger('cli')

# Initialize rich console
console = Console()


class ChatbotCLI:
    """Command-line interface for the RAG chatbot."""

    def __init__(self):
        """Initialize the chatbot CLI."""
        self.rag_chain = RAGChain()
        self.chat_history = []

    def _print_welcome_message(self) -> None:
        """Print the welcome message."""
        console.print(
            Panel(
                "[bold green]Executive MBA HSG Chatbot[/bold green]\n\n"
                "Welcome! I'm your Executive Education Advisor specializing in the Executive MBA HSG program. "
                "Ask me about the Executive MBA HSG program's curriculum, "
                "admissions, costs, or anything related to this specific program at the "
                "University of St. Gallen.\n\n"
                "Type [bold cyan]'exit'[/bold cyan], [bold cyan]'quit'[/bold cyan], [bold cyan]'bye'[/bold cyan], or [bold cyan]'goodbye'[/bold cyan] to end the conversation.",
                title="Welcome",
                border_style="green",
                width=100,
            )
        )

    def _print_sources(self, sources: List[Dict[str, Any]]) -> None:
        """
        Print the sources of information.

        Args:
            sources: List of source information dictionaries.
        """
        if not sources:
            return
        
        table = Table(title="Sources", box=None, show_header=True, header_style="bold cyan")
        table.add_column("Program", style="cyan")
        
        for source in sources:
            program_name = source.get("program_name", "Unknown Program")
            table.add_row(program_name)
        
        console.print(table)

    def _print_response(self, response: Dict[str, Any]) -> None:
        """
        Print the chatbot response.

        Args:
            response: The response dictionary.
        """
        answer = response.get("answer", "")
        sources = response.get("sources", [])
        
        # Print the answer as markdown
        console.print(Markdown(answer))
        
        # Print the sources
        if sources:
            console.print("\n[bold cyan]Sources:[/bold cyan]")
            self._print_sources(sources)

    def _get_user_input(self) -> str:
        """
        Get input from the user.

        Returns:
            The user input.
        """
        console.print("\n[bold green]You:[/bold green] ", end="")
        return input()

    def _process_query(self, query: str) -> Dict[str, Any]:
        """
        Process a user query.

        Args:
            query: The user query.

        Returns:
            The response dictionary.
        """
        try:
            # Get the response from the RAG chain
            response = self.rag_chain.query(query, self.chat_history)
            
            # Update chat history
            if len(self.chat_history) >= MAX_HISTORY:
                self.chat_history.pop(0)
            
            self.chat_history.append((query, response["answer"]))
            
            return response
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "I'm sorry, I encountered an error while processing your question. Please try again.",
                "sources": [],
            }

    def run(self) -> None:
        """Run the chatbot CLI."""
        self._print_welcome_message()
        
        while True:
            # Get user input
            query = self._get_user_input()
            
            # Check if the user wants to exit
            if query.lower() in ["exit", "quit", "bye", "goodbye"]:
                console.print("\n[bold green]Thank you for using the Executive MBA HSG Chatbot. Goodbye![/bold green]")
                break
            
            # Process the query
            console.print("\n[bold blue]Assistant:[/bold blue]")
            response = self._process_query(query)
            
            # Print the response
            self._print_response(response)
            
            # Add a separator
            console.print("\n" + "-" * 100)


if __name__ == "__main__":
    cli = ChatbotCLI()
    cli.run()
