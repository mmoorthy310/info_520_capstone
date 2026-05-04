import json
import os
import httpx
import asyncio

# configs
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8080")
DISABLE_AUTH = os.environ.get("DISABLE_AUTH", "false").lower() == "true"

async def call_mcp(tool_name, args):
    # helper to call the mcp server over sse
    payload = {
        "jsonrpc": "2.0",
        "id": f"req-{id(args)}",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args,
        },
    }

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

    if not DISABLE_AUTH:
        token = get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", f"{MCP_URL}/mcp", json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line.replace("data: ", "").strip()
                    res = json.loads(data_str)
                    if "result" in res:
                        content = res["result"].get("content", [])
                        if content:
                            return json.loads(content[0]["text"])
                        return res["result"]
                    elif "error" in res:
                        raise Exception(res["error"]["message"])

    raise Exception("No data from server")

def get_auth_token():
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token as id_token
        req = google.auth.transport.requests.Request()
        return id_token.fetch_id_token(req, MCP_URL)
    except:
        return None

async def handle_discover_jobs(filters):
    res = await call_mcp("fetch_jobs", filters)
    jobs = res.get("jobs", [])
    
    if len(jobs) == 0:
        return "I couldn't find any jobs matching those filters. Maybe try different keywords?"

    out = f"Found {len(jobs)} jobs:\n\n"
    for i, j in enumerate(jobs, 1):
        rem = " (Remote)" if j.get("remote") else ""
        out += f"{i}. {j['company']} - {j['title']}{rem}\n"
        out += f"   Location: {j['location']} | Deadline: {j.get('deadline', 'TBD')}\n"
        out += f"   Link: {j.get('url', '')}\n\n"
        
    out += "Do you want to save any of these to your pipeline?"
    return out

async def handle_update_pipeline(action):
    res = await call_mcp("sync_pipeline", action)
    if not res.get("success"):
        return f"Failed to update pipeline: {res.get('error')}"

    op = res.get("operation")
    if op == "create":
        return f"Saved {res.get('entry', {}).get('company')} to your pipeline!"
    elif op == "status_change":
        return f"Updated status to {res['new_status']}!"
    elif op == "delete":
        return "Removed from pipeline."
    
    return "Pipeline updated."

async def handle_view_pipeline(status_filter=None):
    params = {"operation": "list"}
    if status_filter:
        params["status"] = status_filter

    res = await call_mcp("sync_pipeline", params)
    entries = res.get("entries", [])
    
    if not entries:
        return "Your pipeline is empty right now."

    out = f"Your Pipeline ({len(entries)} items):\n\n"
    for e in entries:
        out += f"- {e.get('company')} ({e.get('title')}) [{e.get('status').upper()}]\n"
        
    return out

async def main_handler(intent, payload):
    # route the intent from the orchestrator
    if intent == "discover_jobs":
        return await handle_discover_jobs(payload.get("filters", {}))
    elif intent == "update_pipeline":
        return await handle_update_pipeline(payload.get("action", {}))
    elif intent == "view_pipeline":
        return await handle_view_pipeline(payload.get("status_filter"))
    else:
        return "I don't know how to handle that intent."

# vertex ai config
SPECIALIST_PROMPT = """
You are the Career Specialist Agent. You only talk to the Lead Orchestrator, not the user.

Your job is to call the right MCP tool based on the intent.
- discover_jobs -> call fetch_jobs
- update_pipeline -> call sync_pipeline (create or status_change)
- view_pipeline -> call sync_pipeline (list)

Format the results clearly and return them. Never ask follow up questions.
"""

def get_specialist_config():
    return {
        "display_name": "ACC Career Specialist",
        "description": "Calls MCP tools",
        "default_language_code": "en",
        "agent_type": "DIALOGFLOW_CX",
        "generative_settings": {
            "llm": "gemini-1.5-pro",
            "system_prompt": SPECIALIST_PROMPT,
            "temperature": 0.1,
        },
        "tools": [
            {
                "name": "fetch_jobs",
                "description": "Fetch and filter jobs from MCP",
                "mcp_server_url": MCP_URL,
                "mcp_tool_name": "fetch_jobs",
            },
            {
                "name": "sync_pipeline",
                "description": "CRUD operations on pipeline in Firestore",
                "mcp_server_url": MCP_URL,
                "mcp_tool_name": "sync_pipeline",
            },
        ],
    }

if __name__ == "__main__":
    # quick local test
    async def test():
        print("Testing fetch_jobs...")
        r = await main_handler("discover_jobs", {"filters": {"keyword": "python"}})
        print(r)
    asyncio.run(test())
