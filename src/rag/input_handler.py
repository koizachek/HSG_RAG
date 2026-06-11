"""
Input handler for processing and validating user messages.
Handles numeric inputs, validation, and interpretation.
"""
import re
from dataclasses import dataclass
from src.utils.logging import get_logger

logger = get_logger("input_handler")


@dataclass
class InputProcessingResult:
    processed_message: str
    is_valid: bool
    fallback_triggered: bool = False
    fallback_category: str | None = None


class InputHandler:
    """Handles input validation and interpretation"""

    VOWELS = set("aeiouyäöüAEIOUYÄÖÜ")
    COMMON_SHORT_REPLIES = {
        "yes", "no", "ok", "okay", "thanks", "please", "hi", "hello", "hey",
        "ja", "nein", "danke", "bitte", "hallo",
    }
    PROGRAMME_REFERENCES = {
        "emba", "iemba", "emba x", "embax", "mba", "executive mba",
        "international emba", "international executive mba",
    }
    KEYBOARD_MASH_PATTERNS = (
        "asdf", "qwer", "zxcv", "hjkl", "jkl", "dfgh", "sdfg",
    )
    SUSPICIOUS_LETTER_SEQUENCES = (
        "klw", "lwj", "wjk", "jke", "nmj", "mjk", "kjh", "lkj",
        "qwe", "zxc", "xcv", "dfg", "fgh", "ghj", "hjk",
        "ksm", "smd", "skl", "kld", "lso", "sop", "opw", "pwo",
        "kfl", "qok", "mjd", "jdk",
    )
    SUSPICIOUS_WORD_ENDINGS = (
        "lw", "jw", "qw", "qx", "jk", "kj", "hj", "fq", "wq",
    )

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
    def _normalize_for_allowlist(message: str) -> str:
        normalized = re.sub(r"[^\w\s]", " ", message.casefold())
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _has_long_consonant_run(word: str, min_run_length: int = 6) -> bool:
        run_length = 0
        for char in word:
            if char.isalpha() and char not in InputHandler.VOWELS:
                run_length += 1
                if run_length >= min_run_length:
                    return True
            else:
                run_length = 0
        return False

    @staticmethod
    def _looks_like_nonsense_word(word: str) -> bool:
        word_lower = word.casefold()
        if len(word_lower) < 8:
            return False

        score = 0
        if any(pattern in word_lower for pattern in InputHandler.KEYBOARD_MASH_PATTERNS):
            score += 2
        suspicious_sequence_count = sum(
            1
            for sequence in InputHandler.SUSPICIOUS_LETTER_SEQUENCES
            if sequence in word_lower
        )
        if suspicious_sequence_count >= 2:
            score += 2
        elif suspicious_sequence_count == 1:
            score += 1
        if InputHandler._has_long_consonant_run(word_lower, min_run_length=5):
            score += 1
        if re.search(r"([a-zäöü])\1{2,}", word_lower):
            score += 1

        vowel_count = sum(1 for char in word_lower if char in InputHandler.VOWELS)
        vowel_ratio = vowel_count / len(word_lower)
        if vowel_ratio <= 0.2:
            score += 1
        elif vowel_ratio <= 0.3 and suspicious_sequence_count:
            score += 1

        return score >= 2

    @staticmethod
    def _has_suspicious_numeric_companion(word: str) -> bool:
        word_lower = word.casefold()
        if len(word_lower) < 7:
            return False

        return (
            InputHandler._looks_like_nonsense_word(word_lower)
            or word_lower.endswith(InputHandler.SUSPICIOUS_WORD_ENDINGS)
        )

    @staticmethod
    def _has_compact_alphanumeric_noise(message: str) -> bool:
        if re.search(r"\s", message):
            return False

        compact = re.sub(r"[^A-Za-zÄÖÜäöü0-9]", "", message)
        if not compact:
            return False

        letters = re.findall(r"[A-Za-zÄÖÜäöü]", compact)
        digits = re.findall(r"\d", compact)
        if not letters or not digits:
            return False

        letter_part = "".join(letters)
        return (
            len(letter_part) >= 5
            and (
                InputHandler._looks_like_nonsense_word(letter_part)
                or any(
                    sequence in letter_part.casefold()
                    for sequence in InputHandler.SUSPICIOUS_LETTER_SEQUENCES
                )
            )
        )

    @staticmethod
    def is_probably_gibberish(message: str) -> bool:
        """
        Detect obvious non-language input before language detection/model calls.

        The checks are intentionally conservative so short valid answers,
        programme names, names, and numeric follow-ups keep their existing flow.
        """
        normalized = message.strip()

        if not normalized:
            return True

        if InputHandler.is_numeric_input(normalized):
            return False

        allowlisted = InputHandler._normalize_for_allowlist(normalized)
        if allowlisted in InputHandler.COMMON_SHORT_REPLIES:
            return False
        if allowlisted in InputHandler.PROGRAMME_REFERENCES:
            return False

        if not re.search(r"[A-Za-zÄÖÜäöü0-9]", normalized):
            return True

        non_space_chars = re.findall(r"\S", normalized)
        letters = re.findall(r"[A-Za-zÄÖÜäöü]", normalized)
        digits = re.findall(r"\d", normalized)
        punctuation = re.findall(r"[^A-Za-zÄÖÜäöü0-9\s]", normalized)

        if non_space_chars and len(letters) / len(non_space_chars) < 0.35:
            return True

        if (
            len(letters) >= 8
            and punctuation
            and digits
            and (len(punctuation) + len(digits)) / len(non_space_chars) >= 0.45
        ):
            return True
        if InputHandler._has_compact_alphanumeric_noise(normalized):
            return True

        words = re.findall(r"[A-Za-zÄÖÜäöü]+", normalized)
        if not words:
            return False

        joined_words = "".join(word.casefold() for word in words)
        if (
            len(joined_words) >= 8
            and any(pattern in joined_words for pattern in InputHandler.KEYBOARD_MASH_PATTERNS)
        ):
            return True
        if InputHandler._looks_like_nonsense_word(joined_words):
            return True
        if any(InputHandler._looks_like_nonsense_word(word) for word in words):
            return True
        if (
            digits
            and len(words) == 1
            and InputHandler._has_suspicious_numeric_companion(words[0])
        ):
            return True

        vowel_count = sum(1 for char in joined_words if char in InputHandler.VOWELS)
        if len(joined_words) >= 8 and vowel_count / len(joined_words) <= 0.18:
            return True

        for word in words:
            if len(word) >= 8 and (
                InputHandler._has_long_consonant_run(word)
                or not any(char in InputHandler.VOWELS for char in word)
            ):
                return True

        return False

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
        interpreted, _ = InputHandler.interpret_numeric_input_with_category(
            message,
            conversation_history,
        )
        return interpreted

    @staticmethod
    def interpret_numeric_input_with_category(
        message: str,
        conversation_history: list
    ) -> tuple[str, str]:
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
            return f"I have {number} years of work experience", "numeric_experience"
        
        elif any(keyword in recent_context for keyword in [
            "age", "old", "alter", "jahre alt"
        ]):
            logger.info(f"Interpreting numeric input '{number}' as age")
            return f"I am {number} years old", "numeric_age"
        
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
            return level_map.get(number, f"My qualification level is {number}"), "numeric_qualification"
        
        # Default: assume years of experience (most common)
        logger.info(f"Interpreting numeric input '{number}' as years of experience (default)")
        return f"I have {number} years of work experience", "numeric_default"

    @staticmethod
    def process_input_with_metadata(
        message: str,
        conversation_history: list
    ) -> InputProcessingResult:
        normalized = InputHandler.validate_and_normalize(message)

        if not normalized:
            return InputProcessingResult(
                processed_message="",
                is_valid=False,
                fallback_triggered=True,
                fallback_category="empty_input",
            )

        if InputHandler.is_probably_gibberish(normalized):
            logger.warning(f"Rejected probable gibberish input: '{message}'")
            return InputProcessingResult(
                processed_message=normalized,
                is_valid=False,
                fallback_triggered=True,
                fallback_category="gibberish",
            )

        if InputHandler.is_numeric_input(normalized):
            interpreted, category = InputHandler.interpret_numeric_input_with_category(
                normalized,
                conversation_history
            )
            return InputProcessingResult(
                processed_message=interpreted,
                is_valid=True,
                fallback_triggered=True,
                fallback_category=category,
            )

        return InputProcessingResult(
            processed_message=normalized,
            is_valid=True,
        )
    
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
        result = InputHandler.process_input_with_metadata(message, conversation_history)
        return result.processed_message, result.is_valid
