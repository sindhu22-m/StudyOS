import sys
import json
import datetime
from pathlib import Path
from fastmcp import FastMCP

# Add project root to sys.path so we can import config
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

# Initialize FastMCP
mcp = FastMCP("StudyOS Calendar MCP")

def load_calendar_data() -> list[dict]:
    path = settings.CALENDAR_DATA_PATH
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error loading calendar data: {e}\n")
        return []

def save_calendar_data(data: list[dict]) -> bool:
    path = settings.CALENDAR_DATA_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        sys.stderr.write(f"Error saving calendar data: {e}\n")
        return False

@mcp.tool
def list_events(start_date: str = None, end_date: str = None) -> list[dict]:
    """List calendar events, optionally filtered between start_date and end_date (formatted as YYYY-MM-DD)."""
    sys.stderr.write(f"Calendar MCP: Listing events from {start_date} to {end_date}\n")
    events = load_calendar_data()
    
    if not start_date and not end_date:
        return events
        
    filtered = []
    for ev in events:
        ev_start_date = ev["start"][:10]  # Get YYYY-MM-DD
        if start_date and ev_start_date < start_date:
            continue
        if end_date and ev_start_date > end_date:
            continue
        filtered.append(ev)
    return filtered

@mcp.tool
def create_event(title: str, start_time: str, end_time: str, description: str = "") -> dict:
    """Create a new calendar event (e.g. a study block). Time parameters must be in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)."""
    sys.stderr.write(f"Calendar MCP: Creating event '{title}' at {start_time}\n")
    events = load_calendar_data()
    
    # Generate unique ID
    new_id = f"cal-{int(datetime.datetime.now().timestamp())}"
    new_event = {
        "id": new_id,
        "title": title,
        "start": start_time,
        "end": end_time,
        "description": description
    }
    
    events.append(new_event)
    save_calendar_data(events)
    return new_event

@mcp.tool
def find_free_time(date_str: str) -> list[str]:
    """Find free slots for a given date (formatted as YYYY-MM-DD) between standard study hours (08:00 to 22:00)."""
    sys.stderr.write(f"Calendar MCP: Finding free time on {date_str}\n")
    events = load_calendar_data()
    
    # Day limits (08:00 to 22:00)
    day_start = datetime.datetime.strptime(f"{date_str}T08:00:00", "%Y-%m-%dT%H:%M:%S")
    day_end = datetime.datetime.strptime(f"{date_str}T22:00:00", "%Y-%m-%dT%H:%M:%S")
    
    # Find busy intervals on this day
    busy_intervals = []
    for ev in events:
        # Parse event start/end times
        ev_start = datetime.datetime.strptime(ev["start"][:19], "%Y-%m-%dT%H:%M:%S")
        ev_end = datetime.datetime.strptime(ev["end"][:19], "%Y-%m-%dT%H:%M:%S")
        
        # Check overlap with date_str
        if ev_start.date() == day_start.date():
            # Bound within 08:00 to 22:00
            start = max(ev_start, day_start)
            end = min(ev_end, day_end)
            if start < end:
                busy_intervals.append((start, end))
                
    # Sort busy intervals by start time
    busy_intervals.sort(key=lambda x: x[0])
    
    # Merge overlapping busy intervals
    merged_busy = []
    for start, end in busy_intervals:
        if not merged_busy:
            merged_busy.append((start, end))
        else:
            prev_start, prev_end = merged_busy[-1]
            if start <= prev_end:
                # Overlap, merge
                merged_busy[-1] = (prev_start, max(prev_end, end))
            else:
                merged_busy.append((start, end))
                
    # Find free time intervals
    free_intervals = []
    curr_time = day_start
    
    for start, end in merged_busy:
        if curr_time < start:
            free_intervals.append((curr_time, start))
        curr_time = max(curr_time, end)
        
    if curr_time < day_end:
        free_intervals.append((curr_time, day_end))
        
    # Format free intervals as human-readable time strings
    free_slots = []
    for start, end in free_intervals:
        # Only list slots of at least 30 minutes
        if (end - start).total_seconds() >= 1800:
            free_slots.append(f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}")
            
    return free_slots

if __name__ == "__main__":
    mcp.run(show_banner=False)
