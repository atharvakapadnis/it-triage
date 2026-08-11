import asyncio
from agent import root_agent  # run from inside orchestrator/
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP, USER, SESS = "root", "u_1001", "s1"
# REQUEST = "My laptop, asset AST-100, keeps freezing up."  # swap to test other domains
# REQUEST = "I need a Figma license for design work."
REQUEST = "I can't connect to the VPN, and I also need a Figma license approved for design work."
# REQUEST = "My laptop, asset AST-404, is completely dead."

async def main():
    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP, user_id=USER, session_id=SESS)
    runner = Runner(agent=root_agent, app_name=APP, session_service=sessions)
    msg = types.Content(role="user", parts=[types.Part(text=REQUEST)])
    async for event in runner.run_async(user_id=USER, session_id=SESS, new_message=msg):
        for call in (event.get_function_calls() or []):
            print(f"  -> {event.author} calls: {call.name}({call.args})")
        if event.is_final_response() and event.content and event.content.parts:
            print("\nFINAL:", "".join(p.text or "" for p in event.content.parts))

asyncio.run(main())