# Lead Orchestrator Agent for INFO 520 Capstone
# Runs on Vertex AI Agent Builder

ORCHESTRATOR_PROMPT = """
You are the Lead Orchestrator for the Agentic Career Coach (ACC).
You help university students find internships and manage their applications.

Your main job is to figure out what the student wants to do and route them to the Career Specialist agent.

Routing rules:
1. If they want to search for jobs/internships:
   Transfer to career_specialist with intent="discover_jobs" and pass any filters they gave (like role, location, remote, keywords).
   
2. If they want to update their application pipeline (like saying they applied or got an interview):
   Transfer to career_specialist with intent="update_pipeline" and pass the details.

3. If they want to see their saved jobs or current pipeline status:
   Transfer to career_specialist with intent="view_pipeline".

4. If they just want general career advice (like resume tips):
   Just answer them directly. No need to transfer.

When the specialist agent returns data, you should format it nicely for the user. 
Always be encouraging and professional.
"""

def get_orchestrator_config():
    # config dict for vertex ai
    return {
        "display_name": "ACC Lead Orchestrator",
        "description": "Main entry point that routes users to the specialist",
        "default_language_code": "en",
        "time_zone": "America/New_York",
        "agent_type": "DIALOGFLOW_CX",
        "generative_settings": {
            "llm": "gemini-1.5-pro",
            "system_prompt": ORCHESTRATOR_PROMPT,
            "temperature": 0.3,
        },
        "connected_agents": [
            {
                "agent_id": "career_specialist",
                "display_name": "ACC Career Specialist",
                "transfer_triggers": ["discover_jobs", "update_pipeline", "view_pipeline"],
            }
        ],
        "logging": {
            "enable_stackdriver_logging": True,
            "enable_interaction_logging": True,
        },
    }
