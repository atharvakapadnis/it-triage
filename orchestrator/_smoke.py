import asyncio
import os
from dotenv import load_dotenv

# point ADK at vertedx
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME, USER_ID, SESSION_ID = "smoke", "u_test", "s_test"

agent = LlmAgent(
    name="smoke_agent",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant. Answer in one short sentence.",
)

async def main():
    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=sessions)
    msg = types.Content(role="user", parts=[types.Part(text="Name the capital of France.")])
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=msg):
        if event.is_final_response():
            print("AGENT:", event.content.parts[0].text)

asyncio.run(main())