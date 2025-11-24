"""
Input handler for processing and validating user messages.
Handles numeric inputs, validation, and interpretation.
"""
import re
from src.rag.utilclasses import ConversationState
from src.utils.logging import get_logger

logger = get_logger("input_handler")


class InputHandler:
    """Handles input validation and interpretation"""
    
    @staticmethod
    def validate_and_normalize(message: str) -> str:
        """
        Normalize and validate user input.
        
        Args:
            message: Raw user input
            
        Returns:
            Normalized message
        """
        if not message:
            return ""
        
        # Strip whitespace
        normalized = message.strip()
        
        # Handle empty or very short inputs
        if len(normalized) < 1:
            return ""
        
        return normalized
    
    @staticmethod
    def is_numeric_input(message: str) -> bool:
        """
        Check if message is a standalone number.
        
        Args:
            message: User input
            
        Returns:
            True if message is just a number
        """
        normalized = message.strip()
        # Check if it's just digits (possibly with decimal)
        return bool(re.match(r'^\d+(\.\d+)?$', normalized))
    
    @staticmethod
    def interpret_numeric_input(
        message: str, 
        conversation_history: list
    ) -> str:
        """
        Interpret standalone numeric input based on conversation context.
        
        Args:
            message: Numeric input (e.g., "5")
            conversation_history: Recent conversation messages (LangChain message objects)
            
        Returns:
            Interpreted message (e.g., "I have 5 years of experience")
        """
        number = message.strip()
        
        # Look at recent messages for context
        recent_context = ""
        if len(conversation_history) > 0:
            # Get last bot message
            # Import here to avoid circular dependency
            from langchain_core.messages import AIMessage
            
            for msg in reversed(conversation_history):
                # Handle LangChain message objects
                if isinstance(msg, AIMessage):
                    recent_context = msg.content.lower() if hasattr(msg, 'content') else ""
                    break
                # Handle dictionary format (for backward compatibility)
                elif isinstance(msg, dict) and msg.get("role") == "assistant":
                    recent_context = msg.get("content", "").lower()
                    break
        
        # Interpret based on context keywords
        if any(keyword in recent_context for keyword in [
            "experience", "years", "worked", "arbeits", "erfahrung", "jahre"
        ]):
            logger.info(f"Interpreting numeric input '{number}' as years of experience")
            return f"I have {number} years of work experience"
        
        elif any(keyword in recent_context for keyword in [
            "age", "old", "alter", "jahre alt"
        ]):
            logger.info(f"Interpreting numeric input '{number}' as age")
            return f"I am {number} years old"
        
        elif any(keyword in recent_context for keyword in [
            "qualification", "degree", "bachelor", "master", "qualifikation"
        ]):
            logger.info(f"Interpreting numeric input '{number}' as qualification level")
            # Interpret as degree type
            level_map = {
                "1": "I have a Bachelor's degree",
                "2": "I have a Master's degree",
                "3": "I have an MBA",
                "4": "I have a doctorate/PhD"
            }
            return level_map.get(number, f"My qualification level is {number}")
        
        # Default: assume years of experience (most common)
        logger.info(f"Interpreting numeric input '{number}' as years of experience (default)")
        return f"I have {number} years of work experience"
    
    @staticmethod
    def process_input(
        message: str,
        conversation_history: list
    ) -> tuple[str, bool]:
        """
        Process user input with validation and interpretation.
        
        Args:
            message: Raw user input
            conversation_history: Recent messages for context
            
        Returns:
            Tuple of (processed_message, is_valid)
        """
        # Normalize
        normalized = InputHandler.validate_and_normalize(message)
        
        if not normalized:
            return "", False
        
        # Check if numeric
        if InputHandler.is_numeric_input(normalized):
            interpreted = InputHandler.interpret_numeric_input(
                normalized, 
                conversation_history
            )
            return interpreted, True
        
        return normalized, True
