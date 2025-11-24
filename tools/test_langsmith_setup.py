import os
from langsmith import Client

print("Tracing:", os.getenv("LANGSMITH_TRACING"))
print("Project:", os.getenv("LANGSMITH_PROJECT"))
print("OpenAI-key present:", os.getenv("OPENAI_API_KEY") is not None)

# Verbindung
try:
    client = Client()
    _ = list(client.list_projects())
    print("LangSmith connection: OK")
except Exception as e:
    print("LangSmith connection: ERROR")
    print(e)
    exit(1)

# Tracing-Test
try:
    run = client.create_run(
        name="langsmith_tracing_smoketest",
        run_type="chain",
        inputs={"test": True},
        outputs={"ok": True},
        project_name=os.getenv("LANGSMITH_PROJECT"),
    )
    print("Tracing: OK (run created)")
except Exception as e:
    print("Tracing: ERROR (run failed)")
    print(e)
    exit(1)