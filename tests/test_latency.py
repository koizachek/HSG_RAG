"""
Local latency benchmark — runs without Gradio UI.
Tests key query types and reports response times.
"""
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag.agent_chain import ExecutiveAgentChain

TEST_QUERIES = [
    ("en", "What is special about the IEMBA HSG?"),
    ("en", "What is the tuition fee for emba X?"),
    ("en", "Am I eligible with 8 years experience and 3 years in leadership?"),
    ("en", "Why should I choose HSG over other business schools?"),
    ("en", "What are the application deadlines for EMBA HSG?"),
    ("de", "Was kostet das EMBA HSG Programm?"),
    ("de", "Wie bewerbe ich mich für den IEMBA HSG?"),
]

def run_latency_test():
    print("\n" + "="*60)
    print("LATENCY BENCHMARK — SINGLE AGENT MODE")
    print("="*60)

    results = []

    for lang, query in TEST_QUERIES:
        print(f"\nQuery [{lang}]: {query[:60]}...")
        agent = ExecutiveAgentChain(language=lang)

        start = time.perf_counter()
        response = agent.query(query)
        elapsed = time.perf_counter() - start

        results.append({
            "query": query[:50],
            "lang": lang,
            "time": elapsed,
            "words": len(response.response.split()),
            "rag_used": "retrieve_context" in str(response),
        })

        print(f"  Time:     {elapsed:.2f}s")
        print(f"  Words:    {len(response.response.split())}")
        print(f"  Response: {response.response[:120]}...")

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    times = [r["time"] for r in results]
    print(f"  Fastest:  {min(times):.2f}s")
    print(f"  Slowest:  {max(times):.2f}s")
    print(f"  Average:  {sum(times)/len(times):.2f}s")
    print(f"  Over 10s: {sum(1 for t in times if t > 10)} queries")
    print(f"  Over 15s: {sum(1 for t in times if t > 15)} queries")
    print("="*60)

    return results

if __name__ == "__main__":
    run_latency_test()