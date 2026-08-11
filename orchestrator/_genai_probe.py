import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
)

# One hand-written declaration, same name/shape as the MCP tool.
check_user_access = types.FunctionDeclaration(
    name="check_user_access",
    description="Check if a user has access to a resource.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "user_id": types.Schema(type="STRING"),
            "resource": types.Schema(type="STRING"),
        },
        required=["user_id", "resource"],
    ),
)
tool = types.Tool(function_declarations=[check_user_access])

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Check whether user u_1001 has VPN access.",
    config=types.GenerateContentConfig(tools=[tool]),
)

cand = resp.candidates[0]
print("finish_reason:", cand.finish_reason)
for part in cand.content.parts:
    if part.function_call:
        print("FUNCTION CALL:", part.function_call.name, dict(part.function_call.args))
    elif part.text:
        print("TEXT:", part.text)