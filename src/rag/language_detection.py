import re
import unicodedata

from src.config import config
from src.utils.lang import detect_language_profile
from src.utils.logging import get_logger

logger = get_logger('lang_detector')

# Common short words for quick language detection (no LLM needed)
SHORT_WORDS_DE = {
    'ja', 'nein', 'danke', 'bitte', 'ok', 'gut', 'hallo', 'hi', 'hey',
    'genau', 'stimmt', 'klar', 'super', 'prima', 'toll', 'schön',
    'mehr', 'weniger', 'was', 'wie', 'wo', 'wann', 'warum', 'wer',
    'und', 'oder', 'aber', 'doch', 'noch', 'schon', 'jetzt', 'hier',
    'gerne', 'natürlich', 'sicher', 'vielleicht', 'also', 'ach', 'aha',
}
SHORT_WORDS_EN = {
    'yes', 'no', 'thanks', 'please', 'ok', 'okay', 'good', 'hello', 'hi', 'hey',
    'right', 'sure', 'great', 'nice', 'cool', 'fine', 'perfect',
    'more', 'less', 'what', 'which', 'how', 'where', 'when', 'why', 'who',
    'and', 'or', 'but', 'yet', 'now', 'here', 'there',
    'maybe', 'probably', 'definitely', 'certainly', 'alright',
}

# Stopword sets for full-text heuristic detection (latency fix: avoids the
# LLM round-trip for the vast majority of inputs). High-frequency function
# words are near-guaranteed to appear in any real sentence.
STOPWORDS_DE = SHORT_WORDS_DE | {
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem',
    'einer', 'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'mich', 'mir',
    'ist', 'sind', 'war', 'waren', 'sein', 'haben', 'habe', 'hat', 'hatte',
    'kann', 'können', 'muss', 'müssen', 'möchte', 'will', 'wollen', 'soll',
    'nicht', 'kein', 'keine', 'auch', 'nur', 'sehr', 'dann', 'wenn', 'weil',
    'dass', 'für', 'mit', 'von', 'aus', 'auf', 'bei', 'nach', 'über', 'unter',
    'zum', 'zur', 'als', 'wie', 'um', 'an', 'im', 'am', 'beim', 'durch',
    'mein', 'meine', 'dein', 'ihre', 'ihren', 'unser', 'euch', 'uns',
    'jahre', 'jahren', 'erfahrung', 'studium', 'kosten', 'dauer', 'beginn',
    'kostet', 'welche', 'welcher', 'welches', 'heute',
}
STOPWORDS_EN = SHORT_WORDS_EN | {
    'the', 'a', 'an', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'my',
    'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do',
    'does', 'did', 'can', 'could', 'would', 'should', 'will', 'shall', 'must',
    'not', 'also', 'only', 'very', 'then', 'if', 'because', 'that', 'this',
    'for', 'with', 'from', 'of', 'on', 'at', 'by', 'after', 'about', 'to',
    'in', 'as', 'your', 'our', 'their', 'us', 'them', 'want', 'like', 'need',
    'years', 'experience', 'study', 'cost', 'costs', 'duration', 'start',
}

MIXED_LANGUAGE_AMBIGUOUS_TOKENS = {
    # German "im" is also a common ASCII typo for English "I'm".
    'im',
    # Common in German questions/text but also English stopwords.
    'in',
    'was',
}

STRONG_LANGUAGE_SIGNALS_DE = {
    'wo', 'wann', 'warum', 'wer', 'wie',
    'welche', 'welcher', 'welches',
    'kostet',
}
STRONG_LANGUAGE_SIGNALS_EN = {
    'where', 'when', 'why', 'who', 'how',
    'what', 'which',
    'cost', 'costs',
}

LANGDETECT_MIN_PROBABILITY = 0.75

# Characters that only occur in German (among the two supported languages)
GERMAN_CHARS = set('äöüß')

# Scripts we cannot map to de/en heuristically (Cyrillic, Arabic, CJK, ...)
NON_LATIN_SCRIPT_RE = re.compile(
    r'[Ѐ-ӿ֐-׿؀-ۿऀ-ॿ一-鿿'
    r'぀-ヿ가-힯]'
)

# Patterns for explicit language switch requests
SWITCH_TO_EN_PATTERNS = [
    'in english', 'to english', 'switch to english', 'continue in english',
    'speak english', 'english please', 'prefer english', 'rather in english',
    'answer in english', 'respond in english', 'information in english',
]
SWITCH_TO_DE_PATTERNS = [
    'auf deutsch', 'zu deutsch', 'in deutsch', 'deutsch bitte', 'lieber deutsch',
    'bitte deutsch', 'weiter auf deutsch', 'antworten auf deutsch',
    'in german', 'to german', 'switch to german', 'continue in german',
    'speak german', 'german please', 'prefer german',
]

LANGUAGE_NEUTRAL_PROGRAM_PATTERNS = [
    r"emba",
    r"emba hsg",
    r"iemba",
    r"iemba hsg",
    r"international emba",
    r"international executive mba",
    r"emba x",
    r"embax",
]


class LanguageDetector:
    def __init__(self) -> None:
        # Kept for tests that assert local heuristics never initialize a model.
        self._model = None

    def detect_explicit_switch_request(self, query: str) -> str | None:
        """
        Detect if user explicitly requests a language switch.
        Returns 'en', 'de', or None if no explicit switch requested.
        """
        query_lower = query.lower()
        normalized = re.sub(r"[^\w\s]", " ", query_lower)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if normalized in {'english', 'englisch'}:
            logger.info("Explicit language switch request detected: -> English")
            return 'en'

        if normalized in {'deutsch', 'german'}:
            logger.info("Explicit language switch request detected: -> German")
            return 'de'

        for pattern in SWITCH_TO_EN_PATTERNS:
            if pattern in query_lower:
                logger.info(f"Explicit language switch request detected: -> English")
                return 'en'

        for pattern in SWITCH_TO_DE_PATTERNS:
            if pattern in query_lower:
                logger.info(f"Explicit language switch request detected: -> German")
                return 'de'

        return None

    def _quick_detect_short_words(self, query: str) -> str | None:
        """Quick detection for short inputs using word dictionary. Returns None if not detected."""
        words = re.findall(r"[a-z']+", query.lower())
        if len(words) > 3:
            return None

        shared_de_en = SHORT_WORDS_DE & SHORT_WORDS_EN
        de_matches = sum(
            1
            for word in words
            if (
                word in SHORT_WORDS_DE
                and word not in shared_de_en
                and word not in MIXED_LANGUAGE_AMBIGUOUS_TOKENS
            )
        )
        en_matches = sum(
            1
            for word in words
            if (
                word in SHORT_WORDS_EN
                and word not in shared_de_en
                and word not in MIXED_LANGUAGE_AMBIGUOUS_TOKENS
            )
        )

        if de_matches > en_matches:
            logger.info(f"Quick detection: '{query}' -> German (dictionary match)")
            return 'de'
        elif en_matches > de_matches:
            logger.info(f"Quick detection: '{query}' -> English (dictionary match)")
            return 'en'

        return None

    def is_language_neutral_program_reference(self, query: str) -> bool:
        """
        Return True when the query is only a programme name/reference and therefore
        should not trigger a fresh language detection.
        """
        normalized = re.sub(r"[^\w\s]", " ", query.casefold())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized in LANGUAGE_NEUTRAL_PROGRAM_PATTERNS

    def is_language_neutral_input(self, query: str) -> bool:
        """Return True when the input should keep the conversation language.

        Shared greetings such as ``hi`` and ``hey`` are valid in both English
        and German. Sending these very short inputs to the statistical language
        detector produces unreliable results (for example, ``hi`` is commonly
        classified as Swahili).
        """
        normalized = re.sub(r"[^\w\s]", " ", query.casefold())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        shared_short_words = SHORT_WORDS_DE & SHORT_WORDS_EN
        return (
            self.is_language_neutral_program_reference(query)
            or normalized in shared_short_words
        )

    @staticmethod
    def _supported_languages() -> set[str]:
        return set(config.get("AVAILABLE_LANGUAGES", ["en", "de"]))

    @staticmethod
    def _profile_detect(query: str) -> tuple[str, float] | None:
        profile = detect_language_profile(query)
        if profile:
            profile_lang, probability = profile
            logger.info(f"Profile detection: {profile_lang} ({probability:.2f})")
        return profile

    @staticmethod
    def _mixed_language_signal_counts(text: str) -> tuple[int, int]:
        words = re.findall(r"[a-z']+", text)
        shared_de_en = STOPWORDS_DE & STOPWORDS_EN
        de_hits = sum(
            1
            for word in words
            if (
                word in STOPWORDS_DE
                and word not in shared_de_en
                and word not in MIXED_LANGUAGE_AMBIGUOUS_TOKENS
            )
        )
        en_hits = sum(
            1
            for word in words
            if (
                word in STOPWORDS_EN
                and word not in shared_de_en
                and word not in MIXED_LANGUAGE_AMBIGUOUS_TOKENS
            )
        )
        if any(ch in GERMAN_CHARS for ch in text):
            de_hits += 1
        return de_hits, en_hits

    @staticmethod
    def _weighted_language_signal_counts(text: str) -> tuple[int, int]:
        """
        Count unambiguous de/en signals, weighting high-confidence question
        words so short factual queries can be resolved without langdetect.
        """
        words = re.findall(r"[a-z']+", text)
        shared_de_en = STOPWORDS_DE & STOPWORDS_EN

        def score(
            language_words: set[str],
            strong_signals: set[str],
        ) -> int:
            return sum(
                2 if word in strong_signals else 1
                for word in words
                if (
                    word in language_words
                    and word not in shared_de_en
                    and word not in MIXED_LANGUAGE_AMBIGUOUS_TOKENS
                )
            )

        return (
            score(STOPWORDS_DE, STRONG_LANGUAGE_SIGNALS_DE),
            score(STOPWORDS_EN, STRONG_LANGUAGE_SIGNALS_EN),
        )

    def _heuristic_detect(self, query: str) -> str | None:
        """
        Full-text heuristic detection for de/en. Returns None when ambiguous
        or unsupported.
        """
        text = query.lower()

        # Non-Latin script -> unsupported by the de/en-only local detector.
        if NON_LATIN_SCRIPT_RE.search(text):
            return None

        # Other Latin diacritics (e.g. Turkish, Hungarian, Latvian) should not
        # be forced into de/en by a coincidental German-looking character.
        if self._has_non_german_latin_diacritic(text):
            return None

        # Umlauts / eszett are a strong German signal
        if any(ch in GERMAN_CHARS for ch in text):
            logger.info("Heuristic detection: German characters found -> de")
            return 'de'

        words = re.findall(r"[a-z']+", text)
        if not words:
            return None

        de_hits, en_hits = self._weighted_language_signal_counts(text)
        min_hits = 1 if len(words) <= 3 else 2

        # Require a clear weighted signal and a strict majority. Ties and
        # zero-hit inputs stay ambiguous.
        if de_hits > en_hits and de_hits >= min_hits:
            logger.info(f"Heuristic detection: de ({de_hits} vs {en_hits} weighted hits)")
            return 'de'
        if en_hits > de_hits and en_hits >= min_hits:
            logger.info(f"Heuristic detection: en ({en_hits} vs {de_hits} weighted hits)")
            return 'en'

        return None

    def needs_language_clarification(self, query: str) -> bool:
        """
        Return True when a message blends language signals and answering in one
        supported language would be a guess.
        """
        text = query.lower()

        words = re.findall(r"[a-z']+", text)
        de_hits, en_hits = self._mixed_language_signal_counts(text)
        supported_hits = de_hits + en_hits
        has_unsupported_script_signal = (
            NON_LATIN_SCRIPT_RE.search(text)
            or self._has_non_german_latin_diacritic(text)
        )

        if len(words) >= 4 and de_hits > 0 and en_hits > 0:
            logger.info(
                "Mixed-language input detected "
                f"(de={de_hits}, en={en_hits})"
            )
            return True

        if supported_hits > 0 and has_unsupported_script_signal:
            logger.info("Mixed supported/unsupported language input detected.")
            return True

        if self._heuristic_detect(query):
            return False

        profile_result = self._profile_detect(query) if supported_hits > 0 else None
        if profile_result:
            profile_lang, profile_probability = profile_result
            if (
                profile_lang not in self._supported_languages()
                and profile_probability >= LANGDETECT_MIN_PROBABILITY
            ):
                logger.info(
                    "Mixed supported/unsupported language input detected "
                    f"(profile={profile_lang}, p={profile_probability:.2f})"
                )
                return True

        return False

    @staticmethod
    def _has_non_german_latin_diacritic(text: str) -> bool:
        for ch in text:
            if ord(ch) <= 127 or ch in GERMAN_CHARS:
                continue
            if 'LATIN' in unicodedata.name(ch, ''):
                return True
        return False

    def detect_language(self, query: str) -> str:
        # 1. Quick detection for short inputs
        quick_result = self._quick_detect_short_words(query)
        if quick_result:
            return quick_result

        if self.needs_language_clarification(query):
            logger.info("Local language detection found mixed supported-language signals.")
            return ""

        # 2. Full-text stopword heuristic (latency fix: resolves the vast
        #    majority of inputs locally in <1 ms instead of an LLM round-trip)
        heuristic_result = self._heuristic_detect(query)
        if heuristic_result:
            return heuristic_result

        profile_result = self._profile_detect(query)
        if profile_result:
            profile_lang, profile_probability = profile_result
            if (
                profile_lang in self._supported_languages()
                and profile_probability >= LANGDETECT_MIN_PROBABILITY
            ):
                logger.info(
                    "Profile detection accepted: "
                    f"{profile_lang} ({profile_probability:.2f})"
                )
                return profile_lang

        # 3. Ambiguous or unsupported input. Do not call an LLM here: the chain
        # handles this through the supported-language fallback.
        logger.info("Local language detection ambiguous or unsupported.")
        return ""
