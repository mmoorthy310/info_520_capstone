import json
import os
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import google.auth.transport.requests
from google.oauth2 import id_token as google_id_token
from google.cloud import firestore
from google.oauth2 import service_account

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# setup firestore connection
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "capstonedb")
PIPELINE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "internship")

def get_db():
    # checking for local key vs cloud run secret
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        import json as _json
        info = _json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return firestore.Client(database=FIRESTORE_DATABASE, credentials=creds)
    
    return firestore.Client(database=FIRESTORE_DATABASE)

db = get_db()

# mock jobs for the fetch tool
MOCK_JOBS = [
    {
        "id": "job-001",
        "company": "Google",
        "title": "Software Engineering Intern",
        "location": "Mountain View, CA",
        "remote": False,
        "keywords": ["python", "distributed systems", "machine learning"],
        "deadline": "2026-02-15",
        "url": "https://careers.google.com/jobs/results/job-001",
        "description": "Work on core infrastructure and ML pipelines.",
    },
    {
        "id": "job-002",
        "company": "Meta",
        "title": "Data Science Intern",
        "location": "Menlo Park, CA",
        "remote": False,
        "keywords": ["sql", "python", "statistics", "data science"],
        "deadline": "2026-02-20",
        "url": "https://www.metacareers.com/jobs/job-002",
        "description": "Build and analyze large-scale data pipelines.",
    },
    {
        "id": "job-003",
        "company": "Amazon",
        "title": "Cloud Support Engineering Intern",
        "location": "Seattle, WA",
        "remote": True,
        "keywords": ["cloud", "aws", "networking", "linux"],
        "deadline": "2026-03-01",
        "url": "https://amazon.jobs/job-003",
        "description": "Support AWS customers and build internal tooling.",
    },
    {
        "id": "job-004",
        "company": "Salesforce",
        "title": "Product Management Intern",
        "location": "San Francisco, CA",
        "remote": False,
        "keywords": ["product management", "agile", "saas", "crm"],
        "deadline": "2026-02-28",
        "url": "https://salesforce.com/careers/job-004",
        "description": "Define product requirements and work with engineering.",
    },
    {
        "id": "job-005",
        "company": "Palantir",
        "title": "Forward Deployed Software Engineer Intern",
        "location": "New York, NY",
        "remote": False,
        "keywords": ["python", "data engineering", "analytics", "java"],
        "deadline": "2026-03-10",
        "url": "https://palantir.com/careers/job-005",
        "description": "Deploy Palantir software to government and enterprise clients.",
    },
    {
        "id": "job-006",
        "company": "Stripe",
        "title": "Backend Engineering Intern",
        "location": "Remote",
        "remote": True,
        "keywords": ["python", "ruby", "api", "payments", "distributed systems"],
        "deadline": "2026-03-15",
        "url": "https://stripe.com/jobs/job-006",
        "description": "Build payment infrastructure used by millions of businesses.",
    },
    {
        "id": "job-007",
        "company": "Notion",
        "title": "Full-Stack Engineering Intern",
        "location": "San Francisco, CA",
        "remote": True,
        "keywords": ["python", "react", "typescript", "node", "databases"],
        "deadline": "2026-02-25",
        "url": "https://notion.so/careers/job-007",
        "description": "Build features for the all-in-one workspace tool.",
    },
    {
        "id": "job-008",
        "company": "Capital One",
        "title": "Technology Intern — Data Engineering",
        "location": "McLean, VA",
        "remote": False,
        "keywords": ["python", "spark", "sql", "data engineering", "finance"],
        "deadline": "2026-02-10",
        "url": "https://capitalone.com/careers/job-008",
        "description": "Build and optimize data pipelines for financial services.",
    },
]

# mcp formatting helpers
def format_mcp_res(req_id, res):
    return {"jsonrpc": "2.0", "id": req_id, "result": res}

def format_mcp_err(req_id, code, msg):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}

# no longer using stream_sse since Vertex AI expects standard JSON


# security check for cloud run
EXPECTED_AUDIENCE = os.environ.get("MCP_SERVICE_AUDIENCE", "")

async def check_auth(authorization: str = Header(default="")):
    if os.environ.get("DISABLE_AUTH", "false").lower() == "true":
        return 
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
        
    token = authorization.split(" ")[1]
    try:
        req = google.auth.transport.requests.Request()
        return google_id_token.verify_oauth2_token(token, req, EXPECTED_AUDIENCE)
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))

# tool 1: get jobs based on filters
def fetch_jobs_tool(args):
    r = args.get("role", "").lower()
    l = args.get("location", "").lower()
    k = args.get("keyword", "").lower()
    rem = args.get("remote")
    
    matches = []
    for j in MOCK_JOBS:
        if r and r not in j["title"].lower(): continue
        if l and l not in j["location"].lower(): continue
        if k and not any(k in kw for kw in j["keywords"]): continue
        if rem is not None and j["remote"] != bool(rem): continue
        matches.append(j)
        
    return {
        "jobs": matches,
        "total": len(matches),
        "filters_applied": args
    }

# tool 2: save/update firestore db
def sync_pipeline_tool(args):
    op = args.get("operation", "list")
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if op == "create":
        eid = str(uuid.uuid4())
        doc = {
            "entry_id": eid,
            "job_id": args.get("job_id"),
            "company": args.get("company"),
            "title": args.get("title"),
            "location": args.get("location"),
            "url": args.get("url"),
            "status": args.get("status", "saved"),
            "deadline": args.get("deadline"),
            "notes": args.get("notes", ""),
            "created_at": timestamp,
            "updated_at": timestamp,
            "status_history": [{"status": args.get("status", "saved"), "timestamp": timestamp}],
        }
        db.collection(PIPELINE_COLLECTION).document(eid).set(doc)
        return {"entry_id": eid, "entry": doc, "operation": "create", "success": True}
        
    elif op == "update":
        eid = args.get("entry_id")
        if not eid: return {"error": "need entry_id", "success": False}
        
        updates = {k: v for k, v in args.items() if k not in ["operation", "entry_id"] and v is not None}
        updates["updated_at"] = timestamp
        db.collection(PIPELINE_COLLECTION).document(eid).update(updates)
        updated_doc = db.collection(PIPELINE_COLLECTION).document(eid).get()
        return {"entry_id": eid, "entry": updated_doc.to_dict(), "operation": "update", "success": True}
        
    elif op == "status_change":
        eid = args.get("entry_id")
        new_stat = args.get("new_status")
        if not eid or not new_stat: return {"error": "missing info", "success": False}
        
        ref = db.collection(PIPELINE_COLLECTION).document(eid)
        current = ref.get()
        if not current.exists: return {"error": "not found", "success": False}
        
        data = current.to_dict()
        hist = data.get("status_history", [])
        hist.append({"status": new_stat, "timestamp": timestamp})
        
        ref.update({"status": new_stat, "updated_at": timestamp, "status_history": hist})
        return {"entry_id": eid, "old_status": data.get("status"), "new_status": new_stat, "operation": "status_change", "success": True}
        
    elif op == "list":
        stat = args.get("status")
        q = db.collection(PIPELINE_COLLECTION)
        if stat:
            q = q.where("status", "==", stat)
        
        results = [d.to_dict() for d in q.stream()]
        return {"entries": results, "total": len(results), "operation": "list", "success": True}
        
    elif op == "delete":
        eid = args.get("entry_id")
        if not eid: return {"error": "need entry_id", "success": False}
        db.collection(PIPELINE_COLLECTION).document(eid).delete()
        return {"entry_id": eid, "operation": "delete", "success": True}

# register available tools
TOOLS = {
    "fetch_jobs": {
        "description": "Fetch and filter internship/job opportunities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "location": {"type": "string"},
                "keyword": {"type": "string"},
                "remote": {"type": "boolean"},
            },
        },
    },
    "sync_pipeline": {
        "description": "CRUD operations on the internship search pipeline stored in Firestore.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["create", "update", "list", "delete", "status_change"]},
                "entry_id": {"type": "string"},
                "job_id": {"type": "string"},
                "company": {"type": "string"},
                "title": {"type": "string"},
                "location": {"type": "string"},
                "url": {"type": "string"},
                "status": {"type": "string"},
                "new_status": {"type": "string"},
                "deadline": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["operation"],
        },
    },
}

# main endpoint
@app.post("/mcp", dependencies=[Depends(check_auth)])
async def handle_mcp(req: Request):
    try:
        body = await req.json()
    except:
        raise HTTPException(status_code=400, detail="bad json")
        
    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id", str(uuid.uuid4()))
    
    if method == "initialize":
        res = format_mcp_res(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "acc-mcp-server", "version": "1.0.0"},
        })
        return res
        
    if method == "tools/list":
        tool_list = [{"name": n, **info} for n, info in TOOLS.items()]
        res = format_mcp_res(req_id, {"tools": tool_list})
        return res
        
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        
        if name == "fetch_jobs":
            data = fetch_jobs_tool(args)
        elif name == "sync_pipeline":
            data = sync_pipeline_tool(args)
        else:
            err = format_mcp_err(req_id, -32601, f"tool not found: {name}")
            return err
            
        res = format_mcp_res(req_id, {
            "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
            "isError": False,
        })
        return res

    err = format_mcp_err(req_id, -32601, "method not found")
    return err

@app.get("/health")
async def health_check():
    return {"status": "ok"}
