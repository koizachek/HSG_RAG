"""
Scope guardian for handling out-of-scope queries and providing appropriate redirections.
Ensures the chatbot stays within its defined boundaries.
"""
import re
from src.utils.logging import get_logger

logger = get_logger("scope_guardian")


class ScopeGuardian:
    """Guards conversation scope and provides appropriate redirections"""
    
    # Keywords indicating off-topic queries
    OFF_TOPIC_KEYWORDS = {
        'en': [
            'weather', 'sports', 'politics', 'vacation', 'travel',
            'restaurant', 'movie', 'entertainment', 'news', 'dating',
            'health', 'medical', 'recipe', 'cooking'
        ],
        'de': [
            'wetter', 'sport', 'politik', 'urlaub', 'reise',
            'restaurant', 'film', 'unterhaltung', 'nachrichten',
            'gesundheit', 'medizin', 'rezept', 'kochen'
        ]
    }
    
    # Keywords indicating financial planning requests (out of scope)
    FINANCIAL_KEYWORDS = {
        'en': [
            'loan', 'payment plan', 'installment', 'financing options',
            'budget', 'savings plan', 'personal finance', 'credit',
            'bank loan', 'mortgage', 'scholarship application',
            'detailed funding'
        ],
        'de': [
            'kredit', 'ratenzahlung', 'finanzierung', 'zahlungsplan',
            'budget', 'sparplan', 'persönliche finanzen', 'darlehen',
            'bankkredit', 'stipendium antrag', 'detaillierte finanzierung'
        ]
    }
    
    # Keywords indicating aggressive or inappropriate behavior
    AGGRESSIVE_KEYWORDS = [
        'stupid', 'idiot', 'useless', 'terrible', 'worst', 'hate',
        'dumb', 'incompetent', 'pathetic', 'worthless',
        'dumm', 'idiot', 'nutzlos', 'schrecklich', 'hasse'
    ]
    
    @staticmethod
    def check_scope(message: str, language: str = 'en') -> str:
        """
        Check if message is within scope.
        
        Args:
            message: User message
            language: 'en' or 'de'
            
        Returns:
            'on_topic' | 'off_topic' | 'financial_planning' | 'aggressive'
        """
        message_lower = message.lower()
        words_list = message_lower.split()
        
        # Check for aggressive behavior
        if any(keyword in words_list for keyword in ScopeGuardian.AGGRESSIVE_KEYWORDS):
            logger.warning(f"Detected aggressive language in message")
            return 'aggressive'
        
        # Check for off-topic
        off_topic_keywords = (
            ScopeGuardian.OFF_TOPIC_KEYWORDS.get('en', []) +
            ScopeGuardian.OFF_TOPIC_KEYWORDS.get('de', [])
        )
        if any(keyword in words_list for keyword in off_topic_keywords):
            logger.info(f"Detected off-topic query")
            return 'off_topic'
        
        # Check for financial planning
        financial_keywords = (
            ScopeGuardian.FINANCIAL_KEYWORDS.get('en', []) +
            ScopeGuardian.FINANCIAL_KEYWORDS.get('de', [])
        )
        if any(keyword in words_list for keyword in financial_keywords):
            logger.info(f"Detected financial planning query")
            return 'financial_planning'
        
        return 'on_topic'
    
    @staticmethod
    def get_redirect_message(scope_type: str, language: str = 'en') -> str:
        """
        Get appropriate redirect message based on scope violation.
        
        Args:
            scope_type: Type of scope violation
            language: 'en' or 'de'
            
        Returns:
            Redirect message
        """
        messages = {
            'off_topic': {
                'en': "I'm here to help with questions about HSG Executive MBA programs (EMBA, IEMBA, and emba X). I'd be happy to discuss program details, admissions requirements, or help you find the right program for your goals. What would you like to know about our programs?",
                'de': "Ich bin hier, um Fragen zu den HSG Executive MBA-Programmen (EMBA, IEMBA und emba X) zu beantworten. Gerne helfe ich Ihnen bei Programmdetails, Zulassungsvoraussetzungen oder dabei, das richtige Programm für Ihre Ziele zu finden. Was möchten Sie über unsere Programme wissen?"
            },
            'financial_planning': {
                'en': "For detailed financial planning, payment options, or scholarship applications, I recommend contacting our admissions team directly. They can provide personalized guidance on financing options and available support.\n\nWould you like me to provide general information about program costs and what's included?",
                'de': "Für detaillierte Finanzplanung, Zahlungsoptionen oder Stipendienanträge empfehle ich, direkt mit unserem Zulassungsteam Kontakt aufzunehmen. Sie können Ihnen persönliche Beratung zu Finanzierungsmöglichkeiten und verfügbarer Unterstützung geben.\n\nMöchten Sie allgemeine Informationen über Programmkosten und Leistungen erhalten?"
            },
            'aggressive': {
                'en': "I'm here to help with questions about HSG Executive MBA programs, but please keep the conversation respectful. If the aggressive language continues, I may need to end the chat and refer you to our admissions team. How can I help you with information about our programs?",
                'de': "Ich helfe Ihnen gerne bei Fragen zu den HSG Executive MBA-Programmen, aber bitte bleiben Sie respektvoll. Wenn die aggressive Sprache anhält, muss ich das Gespräch ggf. beenden und Sie an unser Zulassungsteam verweisen. Wie kann ich Ihnen bei Informationen über unsere Programme helfen?"
            }
        }
        
        return messages.get(scope_type, {}).get(language, messages['off_topic']['en'])
    
    @staticmethod
    def should_escalate(
        message: str,
        scope_type: str,
        attempt_count: int = 1
    ) -> tuple[bool, str]:
        """
        Determine if query should be escalated to human advisor.
        
        Args:
            message: User message
            scope_type: Type of scope issue
            attempt_count: Number of clarification attempts
            
        Returns:
            Tuple of (should_escalate, escalation_message)
        """
        # Aggressive behavior -> warn first, then escalate if it continues
        if scope_type == 'aggressive':
            if attempt_count >= 2:
                return True, "escalate_aggressive"
            return False, ""
        
        # Off-topic after 2 redirects -> suggest human contact
        if scope_type == 'off_topic' and attempt_count >= 2:
            return True, "escalate_off_topic"
        
        # Complex financial queries -> escalate
        if scope_type == 'financial_planning':
            return True, "escalate_financial"
        
        return False, ""
    
    @staticmethod
    def get_escalation_message(escalation_type: str, language: str = 'en') -> str:
        """
        Get escalation message for connecting user with admissions team.
        
        Args:
            escalation_type: Type of escalation
            language: 'en' or 'de'
            
        Returns:
            Escalation message
        """
        messages = {
            'escalate_aggressive': {
                'en': "I can’t continue this chat while the language is aggressive. If you still need help, please book an appointment with our admissions team using the links below.",
                'de': "Ich kann dieses Gespräch nicht fortsetzen, solange die Sprache aggressiv ist. Wenn Sie weiterhin Unterstützung benötigen, buchen Sie bitte über die untenstehenden Links einen Termin mit unserem Zulassungsteam."
            },
            'escalate_off_topic': {
                'en': "For questions outside program information, our admissions team would be the best resource. You can reach them at [admissions contact info].\n\nIs there anything specific about the EMBA, IEMBA, or emba X programs I can help you with?",
                'de': "Für Fragen außerhalb der Programminformationen ist unser Zulassungsteam die beste Anlaufstelle. Sie erreichen diese unter [Zulassungskontaktinfo].\n\nGibt es etwas Spezifisches über die EMBA-, IEMBA- oder emba X-Programme, bei dem ich Ihnen helfen kann?"
            },
            'escalate_financial': {
                'en': "Our admissions team can provide detailed guidance on financing options, payment plans, and scholarships. Please contact them directly for personalized financial planning support.",
                'de': "Unser Zulassungsteam kann Ihnen detaillierte Beratung zu Finanzierungsoptionen, Zahlungsplänen und Stipendien geben. Bitte kontaktieren Sie diese direkt für persönliche Unterstützung bei der Finanzplanung."
            }
        }
        
        return messages.get(escalation_type, {}).get(language, messages['escalate_off_topic']['en'])
