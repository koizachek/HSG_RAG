from time import sleep
from random import randint
from langchain_core.messages import SystemMessage
from config import TOP_K_RETRIEVAL
from src.database.weavservice import WeaviateService
from src.rag.agent_chain import ExecutiveAgentChain
from src.utils.logging import init_logging
import unittest, threading

init_logging(level="ERROR", interactive_mode=False)

SYSTEM_MESSAGE_QUERY = "Call three subagents using tools with query 'Provide information about your program' and return their responses with format AGENT_NAME=AGENT_RESPONSE"

def run_threads(func, iterable: list) -> list[threading.Thread]:
    threads = [threading.Thread(target=func, args=(item, )) for item in iterable]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


class TestWeaviateConnection(unittest.TestCase):
    
    def test_concurrent_connection_high_amount(self):
        """Tests if the service is capable of providing large amount of fast responses for banal queries for multiple threads.""" 
        def start_connection(i):
            try:
                serv = WeaviateService()
                for _ in range(4):
                    response, _ = serv.query(
                        query="HSG EMBA", 
                        lang='de', 
                        limit=1,
                    )
                doc = response.objects[0].properties.get('body', '')
                self.assertIsNotNone(doc)
            except Exception as e:
                self.fail(f"Failed to query the database from thread {i}: {e}")

        run_threads(start_connection, range(10))


    def test_concurrent_connection_stardard_workload(self):
        """Tests the standard querying workload (when one initialized chain calls the retrieve_context tool from every subagent with standard sized query)."""
        serv = WeaviateService()
        
        def start_connection(name):
            try:
                response, _ = serv.query(
                    query=f"Übersicht {name} Zielgruppe Struktur Dauer Kosten Unterrichtssprache",
                    lang='de',
                    limit=TOP_K_RETRIEVAL,
                )
                doc = response.objects[0].properties.get('body', '')
                self.assertIsNotNone(doc)
            except Exception as e:
                self.fail(f"Failed to query the database for agent {name}: {e}")

        run_threads(start_connection, ['EMBA', 'IEMBA', 'emba X'])


    def test_simulate_app_runs_with_retrieval(self):
        """Simulates the runtime of multiple app instances with large amount of database calls.""" 
        def agent_thread(tid):
            chain = ExecutiveAgentChain()

            for _ in range(3):
                response = chain._query(
                    agent=chain._agents['lead'],
                    messages=[SystemMessage(SYSTEM_MESSAGE_QUERY)]
                )
                print(f"{tid}:\n{response}")
                
                sleep(randint(3,6))

        run_threads(agent_thread, range(5))

    
if __name__ == "__main__":
    unittest.main()
