import asyncio
from agent import access_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP, USER, SESS = "acc", "u_1001", "s1"

async def main():
    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP, user_id=USER, session_id=SESS)
    runner = Runner(agent=access_agent, app_name=APP, session_service=sessions)
    msg = types.Content(role="user", parts=[types.Part(text="I can't connect to the VPN.")])

    final_text = None
    async for event in runner.run_async(user_id=USER, session_id=SESS, new_message=msg):
        # Raw visibility into every event.
        print("EVENT:", type(event).__name__,
              "| author:", getattr(event, "author", None),
              "| final:", event.is_final_response())
        if getattr(event, "error_message", None):
            print("  ERROR:", event.error_message)
        for call in (event.get_function_calls() or []):
            print(f"  -> tool call: {call.name}({call.args})")
        for resp in (event.get_function_responses() or []):
            print(f"  <- tool result: {resp.name} = {resp.response}")
        if event.content and event.content.parts:
            txt = "".join(p.text or "" for p in event.content.parts)
            if txt:
                print("  TEXT:", txt)
            if event.is_final_response():
                final_text = txt

    print("\nACCESS AGENT:", final_text)

asyncio.run(main())