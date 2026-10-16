"""Step 0: is the AI phone line working? Run:  python check_llm.py
Prints one reply from the model, or the reason it failed."""
from app.config import LLM_API_KEY, LLM_MODEL
from app.llm import LLMClient, LLMUnavailable

if not LLM_API_KEY:
    raise SystemExit("LLM_API_KEY is empty. Copy .env.example to .env and paste your Groq key.")

try:
    msg = LLMClient().chat(
        [{"role": "system", "content": "You are a calm hospital front-desk assistant. Reply in one sentence."},
         {"role": "user", "content": "what time does cardiology OPD open?"}],
        tools=[],
    )
    print(f"Model {LLM_MODEL} replied:\n  {msg.content}")
    print("\nNotice: we never told it our hospital's timings. That answer is made up. "
          "This is exactly why the real bot only answers from knowledge/hospital_info.md.")
except LLMUnavailable as e:
    print(f"LLM call failed: {e}  (check the key, the model id in .env, and your internet)")
