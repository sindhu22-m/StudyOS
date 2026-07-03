import sys
import os
from pathlib import Path
from fastmcp import FastMCP
from pypdf import PdfReader

# Add project root to sys.path so we can import config
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

# Initialize FastMCP
mcp = FastMCP("StudyOS Filesystem MCP")

@mcp.tool
def list_notes() -> list[str]:
    """List all notes and files available in the student's workspace."""
    sys.stderr.write("Filesystem MCP: Listing notes\n")
    workspace = settings.WORKSPACE_DIR
    if not workspace.exists():
        return []
    
    files = []
    for entry in workspace.iterdir():
        if entry.is_file():
            files.append(entry.name)
    return files

@mcp.tool
def read_note(filename: str) -> str:
    """Read the content of a specific note file by its filename (e.g. 'dbms_notes.txt' or 'syllabus.pdf')."""
    sys.stderr.write(f"Filesystem MCP: Reading note {filename}\n")
    workspace = settings.WORKSPACE_DIR
    filepath = workspace / filename
    
    if not filepath.exists():
        return f"Error: File {filename} does not exist in workspace."
    
    # Handle PDF files
    if filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(filepath)
            text = []
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted:
                    text.append(extracted)
            return f"--- PDF Extracted Text ({filename}) ---\n" + "\n".join(text)
        except Exception as e:
            return f"Error reading PDF {filename}: {str(e)}"
    
    # Handle text files
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # Fallback to latin-1
        with open(filepath, "r", encoding="latin-1") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {filename}: {str(e)}"

@mcp.tool
def search_notes(query: str) -> list[dict]:
    """Search for a keyword or phrase across all notes in the workspace and return matching lines."""
    sys.stderr.write(f"Filesystem MCP: Searching notes for '{query}'\n")
    workspace = settings.WORKSPACE_DIR
    if not workspace.exists():
        return []
    
    matches = []
    for entry in workspace.iterdir():
        if entry.is_file():
            # For PDFs, we extract text and search it
            if entry.name.lower().endswith(".pdf"):
                try:
                    reader = PdfReader(entry)
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text() or ""
                        for line_num, line in enumerate(text.splitlines()):
                            if query.lower() in line.lower():
                                matches.append({
                                    "filename": entry.name,
                                    "location": f"Page {page_num + 1}, Line {line_num + 1}",
                                    "line": line.strip()
                                })
                except Exception as e:
                    sys.stderr.write(f"Error searching PDF {entry.name}: {e}\n")
            else:
                # Text files
                try:
                    with open(entry, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f):
                            if query.lower() in line.lower():
                                matches.append({
                                    "filename": entry.name,
                                    "location": f"Line {line_num + 1}",
                                    "line": line.strip()
                                })
                except Exception as e:
                    sys.stderr.write(f"Error reading file {entry.name} for search: {e}\n")
    return matches

@mcp.tool
def write_note(filename: str, content: str) -> str:
    """Create or overwrite a note file in the workspace with the specified text content."""
    sys.stderr.write(f"Filesystem MCP: Writing note {filename}\n")
    workspace = settings.WORKSPACE_DIR
    workspace.mkdir(parents=True, exist_ok=True)
    filepath = workspace / filename
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to note: {filename}"
    except Exception as e:
        return f"Error writing note {filename}: {str(e)}"

if __name__ == "__main__":
    mcp.run(show_banner=False)
