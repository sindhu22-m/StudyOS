import sys
import datetime
import importlib.util
from pathlib import Path
from typing import AsyncGenerator, Optional

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.events.event import Event
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.google_llm import Gemini
from google.genai import types

# Add project root to sys.path so we can import config
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

# Load local MCP modules dynamically to prevent naming collisions with the installed 'mcp' package
def load_local_mcp_module(module_name: str, filename: str):
    mcp_dir = Path(__file__).resolve().parent.parent / "mcp"
    file_path = mcp_dir / filename
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    module = importlib.util.module_from_spec(spec)
    # Ensure sys.path contains project root during execution so the imported module can import config
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module

local_email = load_local_mcp_module("local_mcp_email", "mcp_email.py")
list_recent_emails = local_email.list_recent_emails
get_email_details = local_email.get_email_details

local_filesystem = load_local_mcp_module("local_mcp_filesystem", "mcp_filesystem.py")
list_notes = local_filesystem.list_notes
read_note = local_filesystem.read_note
search_notes = local_filesystem.search_notes

local_calendar = load_local_mcp_module("local_mcp_calendar", "mcp_calendar.py")
list_events = local_calendar.list_events
find_free_time = local_calendar.find_free_time
create_event = local_calendar.create_event

def extract_subject(query: str) -> str:
    """Extract academic subject keyword from the user's query."""
    query_lower = query.lower() if query else ""
    if "os" in query_lower or "operating system" in query_lower:
        return "OS"
    if "dbms" in query_lower or "database" in query_lower:
        return "DBMS"
    # No fallback, return empty string for general search
    return ""


class GmailAgent(BaseAgent):
    name: str = "GmailAgent"
    description: str = "Retrieves simulated academic emails programmatically."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract user query
        user_query = ""
        for ev in ctx._get_events():
            if ev.author == "user" and ev.content and ev.content.parts:
                user_query = " ".join([p.text for p in ev.content.parts if p.text])
                break

        subject = extract_subject(user_query)

        # Call MCP email functions directly (no LLM call)
        emails = list_recent_emails()
        relevant_emails = []
        for mail in emails:
            if subject.lower() in mail["subject"].lower() or subject.lower() in mail["snippet"].lower():
                details = get_email_details(mail["id"])
                relevant_emails.append(details)

        if not relevant_emails and emails:
            relevant_emails.append(get_email_details(emails[0]["id"]))

        summary_lines = [f"Gmail Agent Report for subject '{subject}':"]
        for mail in relevant_emails:
            summary_lines.append(f"- From: {mail.get('sender')}")
            summary_lines.append(f"  Subject: {mail.get('subject')}")
            summary_lines.append(f"  Date: {mail.get('date')}")
            summary_lines.append(f"  Body: {mail.get('body')}")

        yield Event(author=self.name, message="\n".join(summary_lines))

class FilesystemAgent(BaseAgent):
    name: str = "FilesystemAgent"
    description: str = "Retrieves relevant study notes from the workspace programmatically."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract user query
        user_query = ""
        for ev in ctx._get_events():
            if ev.author == "user" and ev.content and ev.content.parts:
                user_query = " ".join([p.text for p in ev.content.parts if p.text])
                break

        subject = extract_subject(user_query)

        # Call MCP filesystem functions directly (no LLM call)
        notes = list_notes()
        relevant_notes = []
        for note in notes:
            if subject.lower() in note.lower() or "note" in note.lower():
                content = read_note(note)
                relevant_notes.append((note, content))

        if not relevant_notes and notes:
            relevant_notes.append((notes[0], read_note(notes[0])))

        summary_lines = [f"Filesystem Agent Report for subject '{subject}':"]
        for note_name, content in relevant_notes:
            summary_lines.append(f"File: {note_name}")
            summary_lines.append("Content:")
            summary_lines.append(content)

        yield Event(author=self.name, message="\n".join(summary_lines))

class CalendarAgent(BaseAgent):
    name: str = "CalendarAgent"
    description: str = "Manages study calendar events programmatically."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract user query to check subject
        user_query = ""
        for ev in ctx._get_events():
            if ev.author == "user" and ev.content and ev.content.parts:
                user_query = " ".join([p.text for p in ev.content.parts if p.text])
                break
        subject = extract_subject(user_query)
        if not subject:
            yield Event(author=self.name, message="Calendar Agent Report:\n- No subject was specified in the request. Unable to schedule a study session.")
            return


        # Check for existing study session in the calendar to avoid duplicates
        existing_events = list_events()
        already_scheduled = None
        for ev in existing_events:
            if f"Study {subject}" in ev["title"] or "Study session for" in ev.get("description", ""):
                already_scheduled = ev
                break

        if already_scheduled:
            summary_text = (
                f"Calendar Agent Report:\n"
                f"- Found existing study session: '{already_scheduled['title']}'\n"
                f"- Scheduled: {already_scheduled['start']} to {already_scheduled['end']}\n"
                f"- Description: {already_scheduled.get('description', '')}"
            )
            yield Event(author=self.name, message=summary_text)
            return

        # Otherwise, search for a free 2-hour slot starting from 2026-06-29
        scheduled_ev = None
        start_date = datetime.date(2026, 6, 29)

        for offset in range(8):  # Check the next 8 days
            check_date = start_date + datetime.timedelta(days=offset)
            date_str = check_date.strftime("%Y-%m-%d")
            free_slots = find_free_time(date_str)
            slot = self._find_two_hour_slot(free_slots)
            if slot:
                start_time_str, end_time_str = slot
                start_iso = f"{date_str}T{start_time_str}:00"
                end_iso = f"{date_str}T{end_time_str}:00"

                scheduled_ev = create_event(
                    title=f"Study {subject}: Exam Prep",
                    start_time=start_iso,
                    end_time=end_iso,
                    description=f"Automatically scheduled study session for {subject} exam preparation."
                )
                break

        if scheduled_ev:
            summary_text = (
                f"Calendar Agent Report:\n"
                f"- Successfully scheduled a new study session: '{scheduled_ev['title']}'\n"
                f"- Time: {scheduled_ev['start']} to {scheduled_ev['end']}\n"
                f"- Description: {scheduled_ev.get('description', '')}"
            )
        else:
            summary_text = "Calendar Agent Report:\n- Unable to find a free 2-hour slot to schedule the study session."

        yield Event(author=self.name, message=summary_text)

    def _find_two_hour_slot(self, free_slots: list[str]) -> Optional[tuple[str, str]]:
        """Finds a 2-hour slot within the free slots list."""
        for slot in free_slots:
            try:
                start_str, end_str = slot.split(" - ")
                sh, sm = map(int, start_str.split(":"))
                eh, em = map(int, end_str.split(":"))
                start_mins = sh * 60 + sm
                end_mins = eh * 60 + em
                if end_mins - start_mins >= 120:
                    sh_end = sh + 2
                    end_slot_str = f"{sh_end:02d}:{sm:02d}"
                    return start_str, end_slot_str
            except Exception:
                continue
        return None

def create_study_os_agents() -> SequentialAgent:
    """Instantiate and configure the StudyOS agent team.
    
    Returns:
        SequentialAgent: The pipeline runner containing Gmail, Filesystem, Calendar, and Coordinator agents.
    """
    # Configure client-side retries to handle rate limits and transient errors gracefully
    retry_config = types.HttpRetryOptions(
        attempts=6,                 # Maximum retry attempts
        exp_base=2.0,               # Exponential backoff base
        initial_delay=2.0,          # Start retrying after 2 seconds
        http_status_codes=[429, 500, 503, 504]
    )
    shared_model = Gemini(
        model=settings.DEFAULT_MODEL,
        retry_options=retry_config
    )

    gmail_agent = GmailAgent()
    fs_agent = FilesystemAgent()
    cal_agent = CalendarAgent()

    coordinator_agent = LlmAgent(
        name="CoordinatorAgent",
        model=shared_model,
        instruction=(
            "You are the Coordinator Agent for StudyOS, a student's personal academic operating system.\n"
            "Your task is to synthesize the information collected by the specialized agents (GmailAgent, FilesystemAgent, and CalendarAgent) "
            "into a single, cohesive, production-quality response for the student.\n\n"
            "The conversation history contains:\n"
            "1. The student's request.\n"
            "2. GmailAgent's report containing exam date and details.\n"
            "3. FilesystemAgent's report containing the relevant syllabus and study concepts.\n"
            "4. CalendarAgent's report containing the details of the study session that has been scheduled.\n\n"
            "Synthesize all of this information. State clearly:\n"
            "- The exam details (date, time, location, coverage) found in the emails.\n"
            "- The key study concepts/syllabus found in the notes.\n"
            "- The details of the study session that has been automatically scheduled for them (date, time, description).\n\n"
            "Be precise, professional, encouraging, and thorough. Do not attempt to call any tools or perform any new actions."
        ),
        tools=[],
        sub_agents=[]
    )

    # Wrap them in a SequentialAgent pipeline
    pipeline = SequentialAgent(
        name="StudyOS_Pipeline",
        sub_agents=[gmail_agent, fs_agent, cal_agent, coordinator_agent]
    )

    return pipeline
