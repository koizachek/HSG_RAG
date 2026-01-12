from langsmith import traceable
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import (
    HumanMessage, 
    AIMessage, 
    SystemMessage, 
)
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.agents.structured_output import ProviderStrategy

import uuid
import json
import os
import re
from datetime import datetime

from src.database.weavservice import WeaviateService

from src.rag.utilclasses import *
from src.rag.middleware import AgentChainMiddleware as chainmdw
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
from src.rag.quality_score_handler import QualityEvaluationResult, QualityScoreHandler

from src.utils.lang import detect_language, get_language_name
from src.utils.logging import get_logger 
from config import (
    TOP_K_RETRIEVAL,
    LOCK_LANGUAGE_AFTER_FIRST_MESSAGE,
    TRACK_USER_PROFILE,
    ENABLE_RESPONSE_CHUNKING,
    ENABLE_EVALUATE_RESPONSE_QUALITY,
)

chain_logger = get_logger('agent_chain')

class ExecutiveAgentChain:
    def __init__(self, language: str = 'en') -> None:
        self._initial_language = language
        self._language = language
        self._user_language = None  # Will be locked after first user message
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        self._conversation_history = []

        if ENABLE_EVALUATE_RESPONSE_QUALITY:
            self._quality_handler = QualityScoreHandler()
        
        # Generate unique user ID for this session
        self._user_id = str(uuid.uuid4())
        
        # Initialize conversation state with user profile tracking
        self._conversation_state: ConversationState = {
            'user_id': self._user_id,
            'user_language': None,
            'user_name': None,
            'experience_years': None,
            'leadership_years': None,
            'field': None,
            'interest': None,
            'qualification_level': None,
            'program_interest': [],
            'suggested_program': None,
            'handover_requested': None,
            'topics_discussed': [],
            'preferences_known': False
        }
        
        # Track scope violations for escalation
        self._scope_violation_count = 0
        
        chain_logger.info(f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}")


    def _retrieve_context(self, query: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language. 
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """
        lang = language or self._language
        try:
            response, _ = self._dbservice.query(
                query=query, 
                lang=lang, 
                limit=TOP_K_RETRIEVAL,
            )
            serialized = '\n\n'.join([doc.properties.get('body', '') for doc in response.objects])
            return serialized
        except Exception as e:
            raise e
   

    def _call_emba_agent(self, query: str) -> str:
        """
        Invokes the EMBA support agent to retrieve more detailed information about the EMBA program.
        
        Args:
            query: Query to the EMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['emba'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except Exception as e:
            chain_logger.error(f"EMBA Agent error: {e}")
            raise RuntimeError("Unable to retrieve EMBA information at this time.")


    def _call_iemba_agent(self, query: str) -> str:
        """
        Invokes the IEMBA support agent to retrieve more detailed information about the IEMBA program.
        
        Args:
            query: Query to the IEMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['iemba'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except Exception as e:
            chain_logger.error(f"IEMBA Agent error: {e}")
            raise RuntimeError("Unable to retrieve IEMBA information at this time.")


    def _call_embax_agent(self, query: str) -> str:
        """
        Invokes the emba X support agent to retrieve more detailed information about the emba X program.
        
        Args:
            query: Query to the emba X support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['embax'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except Exception as e:
            chain_logger.error(f"emba X Agent error: {e}")
            raise RuntimeError("Unable to retrieve emba X information at this time.")


    def _init_agents(self):
        config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        fallback_middleware = ModelFallbackMiddleware(
            *modelconf.get_fallback_models()
        )
        tool_retrieve_context = tool(
            name_or_callable='retrieve_context',
            runnable=self._retrieve_context,
            return_direct=False,
            parse_docstring=True,
        )
        tools_agent_calling = [
            tool(
                name_or_callable='call_emba_agent',
                runnable=self._call_emba_agent,
                return_direct=False,
                parse_docstring=True,
            ),
            tool(
                name_or_callable='call_iemba_agent',
                runnable=self._call_iemba_agent,
                return_direct=False,
                parse_docstring=True,
            ),
            tool(
                name_or_callable='call_embax_agent',
                runnable=self._call_embax_agent,
                return_direct=False,
                parse_docstring=True,
            ),
        ]
        agents = {
            'lead': create_agent(
                name="Lead Agent",
                model=modelconf.get_main_agent_model(),
                tools=tools_agent_calling,
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt('lead', language=self._language),
                middleware=[
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                    fallback_middleware,
                ],
                context_schema=AgentContext,
                response_format=ProviderStrategy(
                    StructuredAgentResponse
                ),
            ),            
        }
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent]=create_agent(
                name=f"{agent.upper()} Agent",
                model=modelconf.get_subagent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(agent, language=self._language),
                middleware=[
                    fallback_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                context_schema=AgentContext,
            )
        return agents, config
   
    def _extract_experience_years(self, conversation: str) -> int | None:
        """Extract years of professional experience from conversation text."""
        # Look for patterns like "10 years", "5 years experience", etc.
        patterns = [
            r'(\d+)\s*years?\s*(?:of\s*)?(?:experience|work)',
            r'(\d+)\s*years?\s*in\s*(?:the\s*)?(?:field|industry)',
            r'working\s*for\s*(\d+)\s*years?',
            r'(\d+)\s*Jahre\s*(?:Erfahrung|Berufserfahrung)',  # German
        ]
        for pattern in patterns:
            match = re.search(pattern, conversation, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _extract_leadership_years(self, conversation: str) -> int | None:
        """Extract years of leadership experience from conversation text."""
        patterns = [
            r'(\d+)\s*years?\s*(?:of\s*)?(?:leadership|management|managing)',
            r'(?:lead|led|manage|managed)\s*(?:for\s*)?(\d+)\s*years?',
            r'(\d+)\s*Jahre\s*(?:Führungserfahrung|Führung)',  # German
        ]
        for pattern in patterns:
            match = re.search(pattern, conversation, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _extract_field(self, conversation: str) -> str | None:
        """Extract professional field/industry from conversation text."""
        # Common fields mentioned in executive education
        fields = [
            'finance', 'banking', 'technology', 'tech', 'IT', 'healthcare', 
            'consulting', 'manufacturing', 'retail', 'marketing', 'sales',
            'engineering', 'pharma', 'telecommunications', 'energy',
            'Finanzwesen', 'Technologie', 'Gesundheitswesen', 'Beratung'  # German
        ]
        conversation_lower = conversation.lower()
        for field in fields:
            if field.lower() in conversation_lower:
                return field.capitalize()
        return None

    def _extract_interest(self, conversation: str) -> str | None:
        """Extract content interests from conversation text."""
        # Look for interest indicators
        interests = [
            'strategy', 'innovation', 'leadership', 'digital transformation',
            'finance', 'operations', 'marketing', 'entrepreneurship',
            'sustainability', 'technology', 'management',
            'Strategie', 'Innovation', 'Führung', 'Digitalisierung'  # German
        ]
        conversation_lower = conversation.lower()
        found_interests = [interest for interest in interests 
                          if interest.lower() in conversation_lower]
        return ', '.join(found_interests) if found_interests else None

    def _extract_name(self, conversation: str) -> str | None:
        """Extract user's name from conversation text."""
        patterns = [
            r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"(?:this is|it's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            r"(?:ich heiße|mein Name ist|ich bin)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",  # German
        ]
        for pattern in patterns:
            match = re.search(pattern, conversation, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Filter out common words that might be误ly matched
                excluded = ['interested', 'looking', 'working', 'searching', 'asking']
                if name.lower() not in excluded:
                    return name
        return None

    def _detect_handover_request(self, conversation: str) -> bool:
        """Detect if user requested appointment, callback, or contact."""
        # Keywords indicating handover request
        handover_keywords = [
            'appointment', 'call me', 'contact me', 'schedule', 'meeting',
            'callback', 'reach out', 'follow up', 'get in touch', 'speak with',
            'talk to', 'consultation', 'discuss with', 'meet with',
            'Termin', 'Rückruf', 'kontaktieren', 'Gespräch', 'anrufen',  # German
            'zurückrufen', 'Beratung', 'treffen'
        ]
        conversation_lower = conversation.lower()
        return any(keyword.lower() in conversation_lower for keyword in handover_keywords)

    def _determine_suggested_program(self) -> str | None:
        """Determine recommended program based on user profile."""
        state = self._conversation_state
        
        # If program interest was explicitly mentioned
        if state['program_interest']:
            return state['program_interest'][0]
        
        # Make recommendation based on profile
        experience = state.get('experience_years', 0) or 0
        leadership = state.get('leadership_years', 0) or 0
        
        # EMBA: 5+ years experience, 2+ years leadership
        if experience >= 5 and leadership >= 2:
            return 'EMBA'
        # IEMBA: International focus, 3+ years experience
        elif experience >= 3:
            return 'IEMBA'
        # EMBA X: Digital/Innovation focus
        elif state.get('interest') and any(kw in state.get('interest', '').lower() 
                                           for kw in ['digital', 'innovation', 'technology']):
            return 'EMBA X'
        
        return None

    def _update_conversation_state(self, user_query: str, agent_response: str) -> None:
        """Update conversation state by extracting information from the conversation."""
        if not TRACK_USER_PROFILE:
            return
        
        # Combine query and response for analysis
        conversation_text = f"{user_query} {agent_response}"
        
        # Extract profile information
        if not self._conversation_state.get('experience_years'):
            exp_years = self._extract_experience_years(conversation_text)
            if exp_years:
                self._conversation_state['experience_years'] = exp_years
                chain_logger.info(f"Extracted experience years: {exp_years}")
        
        if not self._conversation_state.get('leadership_years'):
            lead_years = self._extract_leadership_years(conversation_text)
            if lead_years:
                self._conversation_state['leadership_years'] = lead_years
                chain_logger.info(f"Extracted leadership years: {lead_years}")
        
        if not self._conversation_state.get('field'):
            field = self._extract_field(conversation_text)
            if field:
                self._conversation_state['field'] = field
                chain_logger.info(f"Extracted field: {field}")
        
        if not self._conversation_state.get('interest'):
            interest = self._extract_interest(conversation_text)
            if interest:
                self._conversation_state['interest'] = interest
                chain_logger.info(f"Extracted interest: {interest}")
        
        # Extract name
        if not self._conversation_state.get('user_name'):
            name = self._extract_name(conversation_text)
            if name:
                self._conversation_state['user_name'] = name
                chain_logger.info(f"Extracted name: {name}")
        
        # Detect handover request
        if self._detect_handover_request(conversation_text):
            self._conversation_state['handover_requested'] = True
            chain_logger.info("Handover request detected")
        
        # Check for program mentions
        programs = ['EMBA', 'IEMBA', 'EMBA X']
        for program in programs:
            if program.lower() in conversation_text.lower():
                if program not in self._conversation_state['program_interest']:
                    self._conversation_state['program_interest'].append(program)
        
        # Update suggested program
        suggested = self._determine_suggested_program()
        if suggested and not self._conversation_state.get('suggested_program'):
            self._conversation_state['suggested_program'] = suggested
            chain_logger.info(f"Suggested program: {suggested}")

    def _log_user_profile(self) -> None:
        """Log user profile to JSON file."""
        if not TRACK_USER_PROFILE:
            return
        
        try:
            # Create logs directory if it doesn't exist
            log_dir = os.path.join('logs', 'user_profiles')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create profile data
            profile_data = {
                'user_id': self._conversation_state['user_id'],
                'name': self._conversation_state.get('user_name'),
                'timestamp': datetime.now().isoformat(),
                'experience_years': self._conversation_state.get('experience_years'),
                'leadership_years': self._conversation_state.get('leadership_years'),
                'field': self._conversation_state.get('field'),
                'interest': self._conversation_state.get('interest'),
                'suggested_program': self._conversation_state.get('suggested_program'),
                'handover': self._conversation_state.get('handover_requested'),
                'user_language': self._conversation_state.get('user_language'),
                'program_interest': self._conversation_state.get('program_interest', []),
            }
            
            # Log file path with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, f'profile_{self._user_id}_{timestamp}.json')
            
            # Write to file
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            chain_logger.info(f"User profile logged to {log_file}")
            
        except Exception as e:
            chain_logger.error(f"Failed to log user profile: {e}")

    def generate_greeting(self) -> str:
        self._conversation_history.extend([
            SystemMessage("Generate a short greeting message and introduce yourself. 30 words max."),
            SystemMessage(f"Respond in {get_language_name(self._language)} language."),
        ])
        structured_response = self._query(
            agent=self._agents['lead'], 
            messages=self._conversation_history,
        )
        message = structured_response.response
        self._conversation_history.append(AIMessage(message))
        return message

    @traceable
    def query(self, query: str) -> str:
        """
        Process user query with input handling, scope checking, and response formatting.
        
        Args:
            query: User input
            
        Returns:
            Formatted response
        """
        # Step 1: Process input (handle numeric inputs, validation)
        processed_query, is_valid = InputHandler.process_input(
            query,
            [msg for msg in self._conversation_history if isinstance(msg, (HumanMessage, AIMessage))]
        )
        
        if not is_valid or not processed_query:
            chain_logger.warning(f"Invalid input received: '{query}'")
            return "I didn't quite understand that. Could you please rephrase your question?"
        
        # Log if input was interpreted
        if processed_query != query:
            chain_logger.info(f"Interpreted input '{query}' as '{processed_query}'")
        
        # Step 2: Lock language on first user message
        if LOCK_LANGUAGE_AFTER_FIRST_MESSAGE and self._user_language is None:
            self._user_language = detect_language(processed_query)
            self._conversation_state['user_language'] = self._user_language
            self._language = self._user_language
            chain_logger.info(f"Locked conversation language to '{self._user_language}'")
        
        # Use locked language or current language
        response_language = self._user_language or self._language
        
        # Step 3: Check scope before querying agent
        scope_type = ScopeGuardian.check_scope(processed_query, response_language)
        
        if scope_type != 'on_topic':
            chain_logger.info(f"Out-of-scope query detected: {scope_type}")
            self._scope_violation_count += 1
            
            # Check if should escalate
            should_escalate, escalation_type = ScopeGuardian.should_escalate(
                processed_query,
                scope_type,
                self._scope_violation_count
            )
            
            if should_escalate:
                redirect_msg = ScopeGuardian.get_escalation_message(
                    escalation_type,
                    response_language
                )
            else:
                redirect_msg = ScopeGuardian.get_redirect_message(
                    scope_type,
                    response_language
                )
            
            # Add to history
            self._conversation_history.append(HumanMessage(processed_query))
            self._conversation_history.append(AIMessage(redirect_msg))
            
            return redirect_msg
        
        # Reset violation count on valid topic
        self._scope_violation_count = 0
        
        # Step 4: Build messages with locked language
        self._conversation_history.append(HumanMessage(processed_query))
        
        # Add language instruction (use locked language)
        language_instruction = SystemMessage(
            f"Respond in {get_language_name(response_language)} language."
        )
        
        # Step 5: Query agent
        structured_response = self._query(
            agent=self._agents['lead'],
            messages=self._conversation_history + [language_instruction],
        )
        message = structured_response.response
        
        # Step 6: Format response (remove tables, chunk if needed)
        if ENABLE_RESPONSE_CHUNKING:
            formatted_response = ResponseFormatter.format_response(
                message,
                agent_type='lead',
                enable_chunking=True
            )
        else:
            formatted_response = ResponseFormatter.remove_tables(message)
        
        # Clean up response
        formatted_response = ResponseFormatter.clean_response(formatted_response)

        # Step 7: Evaluate response quality 
        if ENABLE_EVALUATE_RESPONSE_QUALITY:
            quality_evaluation: QualityEvaluationResult = self._quality_handler.evaluate_response_quality(query, formatted_response)
            chain_logger.info(f"Recieved quality score: {quality_evaluation.overall_score:1.2f}")

        # Add to history
        self._conversation_history.append(AIMessage(formatted_response))
        
        # Step 8: Update conversation state and log profile if tracking is enabled
        if TRACK_USER_PROFILE:
            self._update_conversation_state(processed_query, formatted_response)
            # Log profile every 5 messages or when program is suggested
            message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])
            if (message_count % 5 == 0 or 
                self._conversation_state.get('suggested_program')):
                self._log_user_profile()
        
        return formatted_response


    def _query(self, agent, messages: list, thread_id: str = None) -> StructuredAgentResponse:
        try:
            config = self._config.copy()
            config['configurable']['thread_id'] = thread_id or 0
                
            result: AIMessage = agent.invoke(
                {"messages": messages},
                config=config,
                context=AgentContext(agent_name=agent.name),
            )
            response = result.get(
                'structured_response',
                StructuredAgentResponse(
                    response=result['messages'][-1].text, 
                    confidence_score=0.5)
            )
            return response
        except Exception as e:
            error_msg = e.body['message'] if hasattr(e, 'body') else str(e)
            chain_logger.error(f"Failed to invoke the agent: {error_msg}")
            return StructuredAgentResponse(
                response="I'm sorry, I cannot provide a helpful response right now. Please contact tech support or try again later.",
                confidence_score=0.0
            )
