from langsmith import traceable
from langchain_core.messages import AIMessage, HumanMessage

from src.config import config
from src.const.agent_response_constants import *
from src.rag.chain_components import ChainComponent
from src.rag.deterministic_responses import DeterministicResponsePolicy
from src.rag.deterministic_routes import DeterministicRoutes
from src.rag.input_handler import InputHandler
from src.rag.programme_fact_responses import ProgrammeFactResponses
from src.rag.scope_guardian import ScopeGuardian
from src.rag.utilclasses import LeadAgentQueryResponse
from src.utils.lang import get_language_name
from src.utils.logging import get_logger

chain_logger = get_logger('agent_chain')


class ChatbotControlFlow(ChainComponent):
    @traceable
    def query(self, query: str) -> LeadAgentQueryResponse:
        """
        Phase 1: Validation, Scope-Check and language detection.
        Does not call the agent directly.
        """
        chain = self._chain
        deterministic_routes = chain._get_component(
            "_deterministic_routes", DeterministicRoutes
        )
        programme_fact_responses = chain._get_component(
            "_programme_fact_responses", ProgrammeFactResponses
        )

        # Remember fallback language
        current_language = self._stored_language 

        deterministic_policy = getattr(
            self,
            "_deterministic_policy",
            DeterministicResponsePolicy.from_config(),
        )
        deterministic_control_enabled = deterministic_policy.control_enabled
        deterministic_programme_content_enabled = deterministic_policy.programme_content_enabled

        if deterministic_control_enabled and len(self._conversation_history) >= config.convstate.MAX_CONVERSATION_TURNS:
            return LeadAgentQueryResponse(
                response = CONVERSATION_END_MESSAGE[current_language],
                language = current_language,
                max_turns_reached = True,
                relevant_programs=[],
                processed_query = query
            ) 

        # 2. Input Processing
        processed_query, is_valid = InputHandler.process_input(
            query,
            [msg for msg in self._conversation_history if isinstance(msg, (HumanMessage, AIMessage))]
        )

        if deterministic_control_enabled and (not is_valid or not processed_query):
            chain_logger.warning(f"Invalid input received: '{query}'")
            self._fallback_counters["invalid_input"] += 1
            invalid_response = (
                get_repeated_not_valid_query_message(self._stored_language)
                if self._fallback_counters["invalid_input"] >= 2
                else NOT_VALID_QUERY_MESSAGE[self._stored_language]
            )
            return LeadAgentQueryResponse(
                response=invalid_response,
                language=current_language,
                processed_query=query
            )

        if is_valid and processed_query:
            self._fallback_counters["invalid_input"] = 0
        else:
            processed_query = query

        # Log check
        if processed_query != query:
            chain_logger.info(f"Interpreted input '{query}' as '{processed_query}'")

        # 3. Language Detection
        # First: Check for explicit language switch request (overrides lock)
        explicit_switch = self._language_detector.detect_explicit_switch_request(processed_query)
        if explicit_switch:
            self._stored_language = explicit_switch
            current_language = explicit_switch
            self._conversation_state['user_language'] = explicit_switch
        elif self._language_detector.is_language_neutral_program_reference(processed_query):
            chain_logger.info(
                f"Skipping language re-detection for language-neutral programme reference: '{processed_query}'"
            )
            current_language = self._stored_language
        else:
            # Count user messages in conversation history
            user_message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])

            # Lock language after N user messages (allows language switch early in conversation)
            lang_lock_n = config.convstate.LOCK_LANGUAGE_AFTER_N_MESSAGES
            if lang_lock_n > 0 and user_message_count >= lang_lock_n:
                chain_logger.info(f"Language locked to '{self._stored_language}' (after {user_message_count} messages)")
                current_language = self._stored_language
            else:
                detected_language = self._language_detector.detect_language(processed_query)
                self._conversation_state['user_language'] = detected_language

                # Language validation
                if detected_language in ['de', 'en']:
                    self._stored_language = detected_language
                    current_language = detected_language
                else:
                    chain_logger.info("Invalid language detected.")
                    return LeadAgentQueryResponse(
                        response=LANGUAGE_FALLBACK_MESSAGE[current_language],
                        language=current_language,
                        processed_query=processed_query
                    )

        if deterministic_programme_content_enabled:
            if (
                deterministic_routes._is_continuation_request(processed_query)
                and deterministic_routes._latest_ai_mentions_multiple_programmes()
            ):
                return deterministic_routes._serve_programme_overview(
                    processed_query=processed_query,
                    response_language=current_language,
                    detailed=True,
                    profile_context=getattr(self, "_programme_overview_profile_context", False),
                )

            if deterministic_routes._is_iemba_embax_tech_career_change_request(processed_query):
                return deterministic_routes._serve_iemba_embax_tech_career_guidance(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_iemba_eligibility_assessment_request(processed_query):
                return deterministic_routes._serve_iemba_eligibility_assessment(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_iemba_visa_request(processed_query):
                return deterministic_routes._serve_iemba_visa_response(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_iemba_apac_alumni_request(processed_query):
                return deterministic_routes._serve_iemba_apac_alumni_response(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_mixed_language_programme_overview_request(processed_query):
                return deterministic_routes._serve_mixed_language_programme_overview(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_emba_minimal_profile_guidance_request(processed_query):
                return deterministic_routes._serve_emba_minimal_profile_guidance(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if (
                deterministic_routes._latest_ai_mentions_multiple_programmes()
                and deterministic_routes._is_profile_context_update(processed_query)
                and not deterministic_routes._query_mentions_specific_programme(processed_query)
            ):
                return deterministic_routes._serve_programme_overview(
                    processed_query=processed_query,
                    response_language=current_language,
                    detailed=False,
                    profile_context=True,
                )

            preferred_programme = deterministic_routes._extract_programme_preference(processed_query)
            if preferred_programme and deterministic_routes._latest_ai_mentions_multiple_programmes():
                return programme_fact_responses._serve_programme_next_steps(
                    processed_query=processed_query,
                    response_language=current_language,
                    programme=preferred_programme,
                )

            if deterministic_routes._is_embax_comparison_request(processed_query):
                return deterministic_routes._serve_embax_comparison_response(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if deterministic_routes._is_embax_language_request(processed_query):
                return deterministic_routes._serve_embax_language_response(
                    processed_query=processed_query,
                    response_language=current_language,
                )

            if (
                deterministic_routes._previous_response_was_application_next_step()
                and deterministic_routes._is_application_process_detail_request(processed_query)
            ):
                application_programmes = deterministic_routes._resolve_known_application_programmes(processed_query)
                if application_programmes:
                    return programme_fact_responses._serve_application_process_details(
                        processed_query=processed_query,
                        response_language=current_language,
                        programmes=application_programmes,
                    )

            application_programmes = deterministic_routes._resolve_application_programmes(processed_query)
            if application_programmes:
                return programme_fact_responses._serve_application_next_steps(
                    processed_query=processed_query,
                    response_language=current_language,
                    programmes=application_programmes,
                )

            fact_programmes = programme_fact_responses._resolve_programmes_for_fact_request(processed_query)
            if fact_programmes:
                return programme_fact_responses._serve_programme_fact_request(
                    processed_query=processed_query,
                    response_language=current_language,
                    programmes=fact_programmes,
                )

            if deterministic_routes._is_price_frustration_request(processed_query):
                return deterministic_routes._serve_price_frustration_response(
                    processed_query=processed_query,
                    response_language=current_language,
                )

        if deterministic_control_enabled and self._pending_continuation and deterministic_routes._is_continuation_request(processed_query):
            return deterministic_routes._serve_pending_continuation(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._pending_continuation:
            chain_logger.info("Discarding pending continuation because the user started a new request.")
            self._pending_continuation = None

        # 4. Scope Check
        scope_type = (
            ScopeGuardian.check_scope(processed_query, current_language)
            if deterministic_control_enabled
            else "on_topic"
        )

        if scope_type != 'on_topic':
            chain_logger.info(f"Out-of-scope query detected: {scope_type}")
            if scope_type == 'aggressive':
                self._fallback_counters["aggressive"] += 1
                attempt_count = self._fallback_counters["aggressive"]
            else:
                scope_violations = self._fallback_counters["scope_violations"]
                scope_violations[scope_type] = scope_violations.get(scope_type, 0) + 1
                attempt_count = scope_violations[scope_type]

            should_escalate, escalation_type = ScopeGuardian.should_escalate(
                processed_query, scope_type, attempt_count
            )

            if should_escalate:
                redirect_msg = ScopeGuardian.get_escalation_message(escalation_type, current_language)
            else:
                redirect_msg = ScopeGuardian.get_redirect_message(scope_type, current_language)
                if scope_type == "off_topic":
                    redirect_msg = deterministic_routes._append_cost_orientation_to_redirect(
                        redirect_msg,
                        current_language,
                    )

            self._conversation_history.append(HumanMessage(processed_query))
            self._conversation_history.append(AIMessage(redirect_msg))

            return LeadAgentQueryResponse(
                response=redirect_msg,
                language=current_language,
                processed_query=processed_query,
                appointment_requested=False,
                show_booking_widget=False,
            )

        if deterministic_programme_content_enabled and deterministic_routes._is_likely_too_early_for_executive_mba(processed_query):
            return deterministic_routes._serve_too_early_for_executive_mba(
                processed_query=processed_query,
                response_language=current_language,
            )

        if deterministic_programme_content_enabled and deterministic_routes._is_general_mba_overview_request(processed_query):
            return deterministic_routes._serve_programme_overview(
                processed_query=processed_query,
                response_language=current_language,
                detailed=False,
                profile_context=False,
            )
        
        # 5. Check if cached data already exists for this session 
        if config.cache.ENABLED:
            cached_data = self._cache.get(query, current_language, self._user_id)
            if cached_data and isinstance(cached_data, dict):
                return LeadAgentQueryResponse(
                    response=cached_data["response"],
                    additional_details=cached_data.get("additional_details", ""),
                    language=current_language,
                    appointment_requested=cached_data.get("appointment_requested", False),
                    show_booking_widget=cached_data.get("show_booking_widget", False),
                    relevant_programs=cached_data.get("relevant_programs", []),
                )
            

        # 6. Preprocessing is finished - the agent has to answer the query 
        response = self._query_lead(processed_query) 
        
        if config.cache.ENABLED and response.should_cache:
            self._cache.set(
                key=query,
                value={
                    "response":              response.response,
                    "additional_details":    response.additional_details,
                    "appointment_requested": response.appointment_requested,
                    "show_booking_widget":    response.show_booking_widget,
                    "relevant_programs":     response.relevant_programs,
                },
                language   = current_language,
                session_id = self._user_id,
            )
        
        return response
