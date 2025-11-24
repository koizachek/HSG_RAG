"""
Response formatter for handling long responses and table formatting.
Ensures responses are mobile-friendly and appropriately sized.
"""
import re
from config import MAX_RESPONSE_WORDS_LEAD, MAX_RESPONSE_WORDS_SUBAGENT
from src.utils.logging import get_logger

logger = get_logger("response_formatter")


class ResponseFormatter:
    """Formats agent responses for optimal display"""
    
    @staticmethod
    def count_words(text: str) -> int:
        """Count words in text"""
        words = text.split()
        return len(words)
    
    @staticmethod
    def remove_tables(text: str) -> str:
        """
        Convert markdown tables to bullet point lists.
        Tables don't display well on mobile devices.
        
        Args:
            text: Response text potentially containing tables
            
        Returns:
            Text with tables converted to bullet points
        """
        # Pattern to match markdown tables
        table_pattern = r'\|[^\n]+\|\n\|[-:\s|]+\|\n(\|[^\n]+\|\n)+'
        
        def table_to_bullets(match):
            table_text = match.group(0)
            lines = [line.strip() for line in table_text.split('\n') if line.strip()]
            
            if len(lines) < 3:  # Not a valid table
                return table_text
            
            # Extract headers (first line)
            headers = [cell.strip() for cell in lines[0].split('|') if cell.strip()]
            
            # Skip separator line (second line)
            # Process data rows
            bullet_points = []
            for line in lines[2:]:
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if cells and len(cells) == len(headers):
                    # Create bullet point from row
                    row_text = ", ".join([
                        f"**{headers[i]}**: {cells[i]}" 
                        for i in range(len(cells))
                        if cells[i]
                    ])
                    bullet_points.append(f"• {row_text}")
            
            return "\n".join(bullet_points)
        
        # Replace tables with bullet points
        formatted = re.sub(table_pattern, table_to_bullets, text)
        
        if formatted != text:
            logger.info("Converted table to bullet points for mobile-friendly display")
        
        return formatted
    
    @staticmethod
    def chunk_response(
        text: str, 
        max_words: int = MAX_RESPONSE_WORDS_LEAD
    ) -> tuple[str, str | None]:
        """
        Split long response into current response and continuation.
        
        Args:
            text: Full response text
            max_words: Maximum words for current response
            
        Returns:
            Tuple of (current_response, continuation_or_none)
        """
        word_count = ResponseFormatter.count_words(text)
        
        if word_count <= max_words:
            return text, None
        
        # Need to chunk
        logger.info(f"Response has {word_count} words, chunking to {max_words} words")
        
        words = text.split()
        
        # Try to break at a natural point (period, newline) near max_words
        break_point = max_words
        
        # Look for sentence ending near break point
        for i in range(max_words - 20, min(max_words + 20, len(words))):
            if i < len(words) and words[i].endswith(('.', '!', '?')):
                break_point = i + 1
                break
        
        # Create chunks
        current = " ".join(words[:break_point])
        continuation = " ".join(words[break_point:])
        
        # Add continuation prompt
        current += "\n\n*Would you like me to continue with more details?*"
        
        return current, continuation
    
    @staticmethod
    def format_response(
        text: str,
        agent_type: str = 'lead',
        enable_chunking: bool = True
    ) -> str:
        """
        Format response: remove tables and handle length.
        
        Args:
            text: Raw response text
            agent_type: 'lead' or 'subagent' (determines max length)
            enable_chunking: Whether to chunk long responses
            
        Returns:
            Formatted response text
        """
        # Remove tables
        formatted = ResponseFormatter.remove_tables(text)
        
        # Determine max words
        max_words = (
            MAX_RESPONSE_WORDS_LEAD 
            if agent_type == 'lead' 
            else MAX_RESPONSE_WORDS_SUBAGENT
        )
        
        # Handle chunking if enabled
        if enable_chunking:
            formatted, continuation = ResponseFormatter.chunk_response(
                formatted, 
                max_words
            )
            # Note: Continuation handling would need to be implemented in agent chain
            # For now, we just truncate and add hint
        
        return formatted
    
    @staticmethod
    def clean_response(text: str) -> str:
        """
        Clean up response text (remove extra whitespace, etc.)
        
        Args:
            text: Response text
            
        Returns:
            Cleaned text
        """
        # Remove multiple consecutive newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace
        cleaned = cleaned.strip()
        
        return cleaned
