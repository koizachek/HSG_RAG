from src.rag.utilclasses import LeadAgentQueryResponse
from src.cache.cache import Cache

class ExecutiveAgentChain:
    def preprocess_query(self, message: str):
        return LeadAgentQueryResponse(
            response=None,
            processed_query=message,
            language="de",
            should_cache=True,
            confidence_fallback=False,
            max_turns_reached=False,
        )

    def agent_query(self, query: str):
        return LeadAgentQueryResponse(
            response=f"Antwort auf: {query}",
            processed_query=query,
            language="de",
            should_cache=True,
            confidence_fallback=False,
            max_turns_reached=False,
        )

class ChatBotApplication:
    def __init__(self):
        self._cache = Cache.get_cache()
        self._language = "de"

    def _chat(self, message: str, agent: ExecutiveAgentChain):
        preprocess_resp = agent.preprocess_query(message)
        current_lang = preprocess_resp.language
        processed_q = preprocess_resp.processed_query

        final_response = None

        if preprocess_resp.response is not None:
            final_response = preprocess_resp

        elif Cache._settings["enabled"]:
            cached_text = self._cache.get(processed_q, language=current_lang)
            if cached_text is not None:
                final_response = LeadAgentQueryResponse(
                    response=cached_text,
                    processed_query=processed_q,
                    language=current_lang,
                    should_cache=False,
                    confidence_fallback=False,
                    max_turns_reached=False,
                )

        if final_response is None:
            final_response = agent.agent_query(processed_q)

        if final_response.should_cache and Cache._settings["enabled"]:
            self._cache.set(
                key=processed_q,
                value=final_response.response,
                language=current_lang
            )

        return final_response.response


def test_cache_hit_miss():
    Cache.configure(mode="dict", no_cache=False)
    
    app = ChatBotApplication()
    agent = ExecutiveAgentChain()

    r1 = app._chat("Was ist EMBA?", agent)
    r2 = app._chat("Was ist EMBA?", agent)

    assert r1 == "Antwort auf: Was ist EMBA?"
    assert r2 == "Antwort auf: Was ist EMBA?"

    stats = Cache._cache_metrics.cache_stats
    assert stats.misses == 1
    assert stats.hits == 1   
