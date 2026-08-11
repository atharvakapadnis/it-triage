import os
import json
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent

logging.basicConfig(level=logging.INFO)
APP_NAME = "it-triage"

app = FastAPI(title="IT Support Triage Orchestrator")

# One shared session service for the process. With a single Cloud Run instance
# (max-instances=1) this persists conversation state across turns.
_sessions = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_sessions)


class ChatRequest(BaseModel):
    user_id: str = "u_1001"
    session_id: str = "s_default"
    message: str

class ChatResponse(BaseModel):
    reply: str
    agents_called: list[str]
    tools_called: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


async def _ensure_session(user_id: str, session_id: str):
    existing = await _sessions.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await _sessions.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    await _ensure_session(req.user_id, req.session_id)
    msg = types.Content(role="user", parts=[types.Part(text=req.message)])

    reply, agents_called, tools_called = "", [], []
    async for event in _runner.run_async(
        user_id=req.user_id, session_id=req.session_id, new_message=msg
    ):
        for call in (event.get_function_calls() or []):
            bucket = agents_called if event.author == root_agent.name else tools_called
            bucket.append(call.name)
            logging.info(json.dumps(
                {"event": "call", "author": event.author, "name": call.name}
            ))
        if event.is_final_response() and event.content and event.content.parts:
            reply = "".join(p.text or "" for p in event.content.parts)

    return ChatResponse(reply=reply, agents_called=agents_called, tools_called=tools_called)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))