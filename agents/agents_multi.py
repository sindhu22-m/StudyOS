import sys
from pathlib import Path
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters, StdioConnectionParams
from google.adk.models.google_llm import Gemini
from google.genai import types

# Add parent directory to path to import settings
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

def create_study_os_agents() -> LlmAgent:
    """Instantiate and configure the StudyOS agent team.
    
    Returns:
        LlmAgent: The Coordinator Agent (root of the multi-agent hierarchy).
    """
    python_exe = sys.executable

    # Configure client-side retries to handle rate limits and transient errors gracefully
    retry_config = types.HttpRetryOptions(
        attempts=6,                 # Maximum retry attempts
        exp_base=2.0,               # Exponential backoff base
        initial_delay=2.0,          # Start retrying after 2 seconds
        http_status_codes=[429, 500, 503, 504]
    )
    model_name = settings.DEFAULT_MODEL or "gemini-2.5-flash"
    
    # Check if we should use LiteLLM for alternative model providers (e.g. OpenAI GPT, Anthropic Claude, Azure OpenAI)
    is_alternative_provider = any(
        prov in model_name.lower()
        for prov in ["gpt", "claude", "openai", "anthropic", "llama", "mistral", "azure"]
    )
    
    if is_alternative_provider:
        from google.adk.models.lite_llm import LiteLlm
        shared_model = LiteLlm(
            model=model_name,
            api_key=settings.GEMINI_API_KEY,
            api_base=settings.AZURE_API_BASE,
            api_version=settings.AZURE_API_VERSION
        )
    else:
        shared_model = Gemini(
            model=model_name,
            retry_options=retry_config
        )

    
    # 1. Email Agent Setup
    email_toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=python_exe,
                args=[str(settings.MCP_DIR / "mcp_email.py")]
            ),
            timeout=30.0
        )
    )
    email_agent = LlmAgent(
        name="EmailAgent",
        model=shared_model,
        instruction=(
            "You are the Email Agent for StudyOS. Your sole responsibilities are:\n"
            "1. Assignment extraction: Find assignments and extract their deadlines from emails.\n"
            "2. Deadline extraction: Find midterm/final exam dates and project deadlines from emails.\n"
            "3. Announcement summarization: Summarize other academic announcements.\n"
            "CRITICAL BEHAVIOR:\n"
            "- When activated, you must ALWAYS start by calling your `list_recent_emails` tool, then fetch specific email details if necessary.\n"
            "- Extract the exact dates, times, and summaries of deadlines/exams.\n"
            "- You must NEVER attempt to schedule calendar events, read notes, or call other agents.\n"
            "- Once you have extracted the relevant deadlines and announcements, summarize your findings clearly, and immediately transfer control back to the CoordinatorAgent. Do not perform any other routing actions."
        ),
        tools=[email_toolset],
        sub_agents=[]
    )

    # 2. Notes Agent Setup
    notes_toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=python_exe,
                args=[str(settings.MCP_DIR / "mcp_filesystem.py")]
            ),
            timeout=30.0
        )
    )
    notes_agent = LlmAgent(
        name="NotesAgent",
        model=shared_model,
        instruction=(
            "You are the Notes Agent for StudyOS. Your sole responsibilities are:\n"
            "1. Search notes: Search the workspace files for specific subject keywords or concepts.\n"
            "2. Summarize lecture material: Read and summarize key study concepts and exam syllabus details.\n"
            "3. Answer questions from notes: Answer student questions using the content of note files.\n"
            "CRITICAL BEHAVIOR:\n"
            "- When activated, you must ALWAYS start by listing files using `list_notes`, then use `search_notes` and/or `read_note` to locate and extract information.\n"
            "- You must NEVER read emails, schedule calendar events, or call other agents.\n"
            "- Once you have summarized the notes or answered the questions, compile your findings clearly, and immediately transfer control back to the CoordinatorAgent. Do not perform any other routing actions."
        ),
        tools=[notes_toolset],
        sub_agents=[]
    )

    # 3. Planner Agent Setup
    planner_toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=python_exe,
                args=[str(settings.MCP_DIR / "mcp_calendar.py")]
            ),
            timeout=30.0
        )
    )
    planner_agent = LlmAgent(
        name="PlannerAgent",
        model=shared_model,
        instruction=(
            "You are the Planner Agent for StudyOS. Your sole responsibilities are:\n"
            "1. Generate study schedules: Schedule realistic study blocks based on exam dates and study topics.\n"
            "2. Allocate available study time: Find free time slots in the calendar to place study sessions.\n"
            "3. Avoid scheduling conflicts: Ensure new study blocks do not overlap with existing events.\n"
            "CRITICAL BEHAVIOR:\n"
            "- When activated, you must check the calendar using `list_events` and find free time using `find_free_time` for the relevant date range.\n"
            "- If the request is to schedule a study session but you lack necessary details (such as the specific exam date, the topics/syllabus to cover, or the subject name), do NOT attempt to fetch them yourself. You must NEVER transfer control to `EmailAgent` or `NotesAgent` directly. Instead, return a structured report to the CoordinatorAgent detailing exactly what information is missing (e.g. 'Missing exam date', 'Missing syllabus topics') and transfer control back to CoordinatorAgent.\n"
            "- If all necessary scheduling parameters (date, time, topics) are provided in the context/request, identify a free slot, schedule a study block using `create_event` with a clear title matching the subject (e.g., 'Study OS: Scheduling' or 'Study DBMS: Joins'), and report the scheduled details back to the CoordinatorAgent."
        ),
        tools=[planner_toolset],
        sub_agents=[]
    )

    # 4. Coordinator Agent Setup
    coordinator_agent = LlmAgent(
        name="CoordinatorAgent",
        model=shared_model,
        instruction=(
            "You are the Coordinator Agent for StudyOS, serving as the central router, planner, and orchestrator.\n"
            "Your sole responsibilities are:\n"
            "1. Intent detection: Analyze user messages to identify their goals and extract the subject (e.g. DBMS, OS).\n"
            "2. Task planning: Determine what steps and what sub-agents are needed to fulfill the request. If required information (like a subject) is missing, ask the user for clarification.\n"
            "3. Agent orchestration: Transfer control to sub-agents one by one in a step-by-step sequence. Do NOT expect sub-agents to call each other. All control flows must return to you before moving to the next task step.\n"
            "   - E.g. For a complex exam preparation flow: first transfer to `EmailAgent` to extract dates/deadlines; when control returns to you, inspect the findings, then transfer to `NotesAgent` to extract syllabus topics; when control returns, inspect the findings, then transfer to `PlannerAgent` providing the dates and topics to schedule the study block; when control returns, summarize the outcome.\n"
            "4. Response synthesis: Combine and synthesize the structured findings from all active sub-agents into a single, cohesive, professional, and encouraging summary for the student.\n"
            "CRITICAL RULES:\n"
            "- Never call tools directly; always delegate tasks to your sub-agents: `EmailAgent` for emails, `NotesAgent` for notes/files, and `PlannerAgent` for calendar planning.\n"
            "- When a sub-agent transfers control back to you, check if further sub-agent actions are needed to fulfill the plan. If so, transfer control to the next sub-agent. If the plan is complete, synthesize the final response.\n"
            "- API EFFICIENCY RULES:\n"
            "  * Before invoking any sub-agent, inspect the user's message and the conversation history to see if the required details (e.g., exam dates, assignment deadlines, or syllabus topics) are already known. Do NOT invoke `EmailAgent` if dates/deadlines are already present in the history or message. Do NOT invoke `NotesAgent` if the study topics/syllabus are already present.\n"
            "  * If the student asks a question about information that was already retrieved, scheduled, or discussed in the conversation history, answer them directly using your memory of the context. Do NOT call any sub-agents to fetch it again.\n"
            "  * Only invoke the agents that are strictly required to resolve the user's current request."
        ),
        tools=[],
        sub_agents=[email_agent, notes_agent, planner_agent]
    )

    return coordinator_agent
