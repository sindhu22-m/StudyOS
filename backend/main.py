import sys
import json
import logging
import asyncio
import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.genai import types
from google.genai import Client

# Add project root to sys.path so we can import config and agents
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from agents.agents_multi import create_study_os_agents
from google.adk.runners import InMemoryRunner

# Set up logging to stderr so it doesn't disrupt tool outputs
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("StudyOSBackend")

app = FastAPI(title="StudyOS FastAPI Backend", version="1.0.0")

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Models -----------------
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_student"
    session_id: str = "default_session"

class CalendarEventRequest(BaseModel):
    title: str
    start: str
    end: str
    description: Optional[str] = ""

# ----------------- Helper Functions -----------------
def load_json_file(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return []

def save_json_file(path: Path, data: list) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")
        return False

# ----------------- API Endpoints -----------------

@app.get("/api/calendar")
def get_calendar():
    """Retrieve simulated calendar events."""
    return load_json_file(settings.CALENDAR_DATA_PATH)

@app.post("/api/calendar")
def add_calendar_event(event: CalendarEventRequest):
    """Add a new calendar event."""
    events = load_json_file(settings.CALENDAR_DATA_PATH)
    new_event = {
        "id": f"cal-{len(events) + 1}",
        "title": event.title,
        "start": event.start,
        "end": event.end,
        "description": event.description
    }
    events.append(new_event)
    save_json_file(settings.CALENDAR_DATA_PATH, events)
    return new_event

@app.get("/api/emails")
def get_emails():
    """Retrieve simulated academic inbox emails."""
    return load_json_file(settings.EMAIL_DATA_PATH)

@app.get("/api/notes")
def get_notes():
    """List notes in the student workspace with file sizes and type."""
    workspace = settings.WORKSPACE_DIR
    if not workspace.exists():
        return []
    
    notes = []
    for entry in workspace.iterdir():
        if entry.is_file():
            stat = entry.stat()
            notes.append({
                "name": entry.name,
                "size": stat.st_size,
                "type": "pdf" if entry.name.lower().endswith(".pdf") else "text"
            })
    return notes

@app.get("/api/notes/content/{filename}")
def get_note_content(filename: str):
    """Retrieve content of a text note or file."""
    workspace = settings.WORKSPACE_DIR
    filepath = workspace / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        if filename.lower().endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            text = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text.append(extracted)
            return {"name": filename, "content": "\n".join(text), "type": "pdf"}
        
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return {"name": filename, "content": f.read(), "type": "text"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.post("/api/notes/upload")
async def upload_note(file: UploadFile = File(...)):
    """Upload a text or PDF study notes file to the student workspace."""
    workspace = settings.WORKSPACE_DIR
    workspace.mkdir(parents=True, exist_ok=True)
    
    filename = file.filename
    # Security check: sanitizing filename
    safe_filename = Path(filename).name
    filepath = workspace / safe_filename
    
    try:
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
        return {"filename": safe_filename, "status": "success", "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving uploaded file: {str(e)}")

# ----------------- Chat SSE Endpoint -----------------

# Global cache to persist InMemoryRunner instances across requests per session
runners_cache = {}

async def adk_event_stream(message: str, user_id: str, session_id: str):
    """Asynchronously executes the ADK Runner and yields formatted SSE events."""
    logger.info(f"Starting StudyOS Agent stream for message: '{message}'")
    
    # Verify Gemini API key is configured
    if not settings.GEMINI_API_KEY:
        yield f"data: {json.dumps({'type': 'error', 'message': 'API Key missing. Please set GEMINI_API_KEY or GOOGLE_API_KEY in the environment.'})}\n\n"
        return

    try:
        # Retrieve or create a cached runner for this user + session
        cache_key = (user_id, session_id)
        if cache_key not in runners_cache:
            coordinator = create_study_os_agents()
            runner = InMemoryRunner(agent=coordinator, app_name="StudyOS")
            
            # Initialize the session inside the new runner
            await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id=user_id,
                session_id=session_id
            )
            runners_cache[cache_key] = runner
            logger.info(f"Created new runner and session for key: {cache_key}")
        else:
            runner = runners_cache[cache_key]
            logger.info(f"Reusing existing runner for key: {cache_key}")

        # Construct structured message
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=message)]
        )
        
        active_agent = "CoordinatorAgent"
        
        # Stream the ADK runner execution
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message
        ):
            # 1. Update the active agent state if the event author is different
            if event.author and event.author != active_agent:
                active_agent = event.author
                yield f"data: {json.dumps({'type': 'agent_start', 'agent': active_agent})}\n\n"
                
            # 2. Check for content and parts
            if event.content and event.content.parts:
                for part in event.content.parts:
                    # Case A: Model outputs text
                    if part.text:
                        yield f"data: {json.dumps({'type': 'text', 'agent': active_agent, 'text': part.text})}\n\n"
                    
                    # Case B: Model calls a tool
                    elif part.function_call:
                        call = part.function_call
                        if call.name == "transfer_to_agent":
                            target_agent = call.args.get("agent_name")
                            yield f"data: {json.dumps({'type': 'transfer', 'from': active_agent, 'to': target_agent})}\n\n"
                        else:
                            yield f"data: {json.dumps({
                                'type': 'tool_call', 
                                'agent': active_agent, 
                                'tool': call.name, 
                                'args': call.args
                            })}\n\n"
                    
                    # Case C: Model receives a tool response
                    elif part.function_response:
                        resp = part.function_response
                        yield f"data: {json.dumps({
                            'type': 'tool_response', 
                            'agent': active_agent, 
                            'tool': resp.name, 
                            'response': resp.response
                        })}\n\n"
            
            # 3. Check for transfer events in event.actions
            if event.actions and event.actions.transfer_to_agent:
                target = event.actions.transfer_to_agent
                yield f"data: {json.dumps({'type': 'transfer', 'from': active_agent, 'to': target})}\n\n"

        # Signal completion
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        logger.exception("Error in ADK Event Stream")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Endpoint executing the StudyOS multi-agent coordinator and streaming progress."""
    return StreamingResponse(
        adk_event_stream(req.message, req.user_id, req.session_id),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
