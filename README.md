# Agentic Career Coach Capstone

This is our INFO 520 Capstone project for VCU.
It's a multi-agent system that helps students find internships and manage applications.

## How it works
There are two AI agents built with Vertex AI Agent Builder:
1. **Lead Orchestrator**: Talks to the user and figures out what they want to do.
2. **Career Specialist**: Handles the actual tool calling.

The specialist connects to our custom MCP server (Model Context Protocol) running on Cloud Run.

## MCP Server
The server is in the `mcp_server` folder. It has two tools:
- `fetch_jobs`: searches through our job listings
- `sync_pipeline`: saves and updates applications in our Firestore database

### Running it locally
1. Install requirements
```
cd mcp_server
pip install -r requirements.txt
```

2. Add your service account key
Rename `.env.example` to `.env` and put the path to your GCP json key.

3. Run it
```
uvicorn main:app --port 8080
```

### Deploying to GCP
To put the server on Cloud Run:
```
gcloud run deploy acc-mcp-server --source . --project capstone-494822 --allow-unauthenticated
```
