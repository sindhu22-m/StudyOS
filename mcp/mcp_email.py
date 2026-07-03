import sys
import json
from pathlib import Path
from fastmcp import FastMCP

# Add project root to sys.path so we can import config
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

# Initialize FastMCP
mcp = FastMCP("StudyOS Email MCP")

def load_emails_data() -> list[dict]:
    path = settings.EMAIL_DATA_PATH
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error loading email data: {e}\n")
        return []

@mcp.tool
def list_recent_emails() -> list[dict]:
    """List recent emails received by the student. Returns a list containing metadata like sender, subject, date, and body snippets."""
    sys.stderr.write("Email MCP: Listing recent emails\n")
    emails = load_emails_data()
    summary_list = []
    for mail in emails:
        summary_list.append({
            "id": mail["id"],
            "sender": mail["sender"],
            "subject": mail["subject"],
            "date": mail["date"],
            "snippet": mail["body"][:80] + "..." if len(mail["body"]) > 80 else mail["body"]
        })
    return summary_list

@mcp.tool
def get_email_details(email_id: str) -> dict:
    """Retrieve the full details and complete body text of a specific email by its ID."""
    sys.stderr.write(f"Email MCP: Getting details for email {email_id}\n")
    emails = load_emails_data()
    for mail in emails:
        if mail["id"] == email_id:
            return mail
    return {"error": f"Email with ID {email_id} not found."}

if __name__ == "__main__":
    mcp.run(show_banner=False)
