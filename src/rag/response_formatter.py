"""
Response formatter for handling long responses and table formatting.
Ensures responses are mobile-friendly and appropriately sized.
"""
import re
from config import MAX_RESPONSE_WORDS_LEAD, MAX_RESPONSE_WORDS_SUBAGENT
from src.utils.logging import get_logger

logger = get_logger("response_formatter")


CONTINUATION_PROMPT = {
    'en': "*Would you like me to continue with more details?*",
    'de': "*Möchten Sie, dass ich mit weiteren Details fortfahre?*"
}


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
        max_words: int = MAX_RESPONSE_WORDS_LEAD,
        language: str = 'en'
    ) -> tuple[str, str | None]:
        """
        Split long response into current response and continuation.

        Args:
            text: Full response text
            max_words: Maximum words for current response
            language: Language code ('en' or 'de') for continuation prompt

        Returns:
            Tuple of (current_response, continuation_or_none)
        """
        word_count = ResponseFormatter.count_words(text)

        if word_count <= max_words:
            return text, None

        # Need to chunk — preserve line structure (markdown formatting)
        logger.info(f"Response has {word_count} words, chunking to {max_words} words")

        lines = text.split('\n')
        current_lines = []
        current_word_count = 0

        for line in lines:
            line_words = len(line.split()) if line.strip() else 0
            if current_word_count + line_words > max_words and current_lines:
                break
            current_lines.append(line)
            current_word_count += line_words

        current = '\n'.join(current_lines)
        continuation = '\n'.join(lines[len(current_lines):])

        # Add continuation prompt in the correct language
        continuation_msg = CONTINUATION_PROMPT.get(language, CONTINUATION_PROMPT['en'])
        current += f"\n\n{continuation_msg}"

        return current, continuation
    
    @staticmethod
    def format_response(
        text: str,
        agent_type: str = 'lead',
        enable_chunking: bool = True,
        language: str = 'en'
    ) -> str:
        """
        Format response: remove tables and handle length.

        Args:
            text: Raw response text
            agent_type: 'lead' or 'subagent' (determines max length)
            enable_chunking: Whether to chunk long responses
            language: Language code ('en' or 'de') for any generated text

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
            formatted, _continuation = ResponseFormatter.chunk_response(
                formatted,
                max_words,
                language
            )

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
    
    @staticmethod
    def format_name_of_university(formatted_response, language):
        if language == "en":
            pattern = r"Universität St\.Gallen"
            replace = "University of St.Gallen"
            formatted_response = re.sub(pattern, replace, formatted_response)
        
        return formatted_response            
