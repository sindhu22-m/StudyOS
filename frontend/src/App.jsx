import React, { useState, useEffect, useRef } from "react";
import {
  MessageSquare,
  Calendar as CalendarIcon,
  Mail,
  FileText,
  Upload,
  Activity,
  ArrowRight,
  Clock,
  Sparkles,
  Database,
  Cpu,
  CheckCircle,
  AlertCircle,
  ChevronRight,
  RefreshCw,
  Eye,
  FileUp
} from "lucide-react";

const API_BASE = "http://127.0.0.1:8000/api";

export default function App() {
  // Chat state
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "system",
      agent: "CoordinatorAgent",
      text: "Welcome to StudyOS, your AI Academic Operating System. I can orchestrate specialized agents to read your emails, inspect study notes, and organize your calendar. Ask me anything, or try one of the quick prompts below!"
    }
  ]);
  const [inputText, setInputText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  
  // Dashboard data state
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [emails, setEmails] = useState([]);
  const [notes, setNotes] = useState([]);
  const [selectedNote, setSelectedNote] = useState(null);
  
  // Orchestration telemetry state
  const [activeAgent, setActiveAgent] = useState("CoordinatorAgent");
  const [agentLogs, setAgentLogs] = useState([]);
  const [activeTab, setActiveTab] = useState("calendar");
  const [uploadStatus, setUploadStatus] = useState("");
  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  // Quick Action Prompts
  const QUICK_PROMPTS = [
    {
      label: "Prepare DBMS Exam",
      text: "I have a DBMS exam next week. Help me prepare."
    },
    {
      label: "List Deadlines",
      text: "What assignments and deadlines do I have coming up in my emails?"
    },
    {
      label: "Summarize DBMS Notes",
      text: "Find my DBMS notes in the workspace and give me a summary of SQL Joins and Relational Algebra."
    },
    {
      label: "Schedule OS Study",
      text: "Schedule a 2-hour study block for my upcoming OS Lab assignment in a free slot."
    }
  ];

  // Fetch dashboard data
  const fetchDashboardData = async () => {
    try {
      const [calRes, mailRes, notesRes] = await Promise.all([
        fetch(`${API_BASE}/calendar`),
        fetch(`${API_BASE}/emails`),
        fetch(`${API_BASE}/notes`)
      ]);
      if (calRes.ok) setCalendarEvents(await calRes.json());
      if (mailRes.ok) setEmails(await mailRes.json());
      if (notesRes.ok) setNotes(await notesRes.json());
    } catch (err) {
      console.error("Error fetching dashboard data:", err);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentLogs]);

  // Handle Note View
  const handleViewNote = async (filename) => {
    try {
      const res = await fetch(`${API_BASE}/notes/content/${filename}`);
      if (res.ok) {
        setSelectedNote(await res.json());
      }
    } catch (err) {
      console.error("Error fetching note content:", err);
    }
  };

  // Handle File Upload
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setUploadStatus("Uploading...");
    try {
      const res = await fetch(`${API_BASE}/notes/upload`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        setUploadStatus("Upload successful!");
        fetchDashboardData();
        setTimeout(() => setUploadStatus(""), 3000);
      } else {
        setUploadStatus("Upload failed.");
      }
    } catch (err) {
      setUploadStatus("Upload error.");
      console.error(err);
    }
  };

  // Submit Query to Coordinator
  const handleSendMessage = async (textToSend) => {
    const text = textToSend || inputText;
    if (!text.trim() || isStreaming) return;

    setInputText("");
    setIsStreaming(true);
    setActiveAgent("CoordinatorAgent");
    setAgentLogs([]);
    
    // Add user message
    const userMsgId = `user-${Date.now()}`;
    setMessages(prev => [...prev, { id: userMsgId, role: "user", text }]);

    // Add empty placeholder message for model streaming
    const modelMsgId = `model-${Date.now()}`;
    setMessages(prev => [...prev, { id: modelMsgId, role: "model", agent: "CoordinatorAgent", text: "" }]);

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          user_id: "default_student",
          session_id: "studyos_session"
        })
      });

      if (!response.ok) {
        throw new Error("Failed to connect to chat API");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // Keep the remaining chunk

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;

            try {
              const event = JSON.parse(dataStr);
              
              if (event.type === "agent_start") {
                setActiveAgent(event.agent);
                setAgentLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), message: `Agent Active: ${event.agent}` }]);
              } 
              else if (event.type === "transfer") {
                setActiveAgent(event.to);
                setAgentLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), message: `Handoff: ${event.from} ➔ ${event.to}` }]);
              } 
              else if (event.type === "tool_call") {
                setAgentLogs(prev => [...prev, { 
                  time: new Date().toLocaleTimeString(), 
                  message: `Tool Call (${event.agent}): ${event.tool}`, 
                  meta: event.args 
                }]);
              }
              else if (event.type === "tool_response") {
                setAgentLogs(prev => [...prev, { 
                  time: new Date().toLocaleTimeString(), 
                  message: `Tool Response (${event.agent}): ${event.tool} completed` 
                }]);
              }
              else if (event.type === "text") {
                setMessages(prev => prev.map(m => {
                  if (m.id === modelMsgId) {
                    return { ...m, agent: event.agent, text: m.text + event.text };
                  }
                  return m;
                }));
              }
              else if (event.type === "done") {
                setAgentLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), message: `Workflow completed successfully.` }]);
                fetchDashboardData(); // Refresh calendar, notes, etc.
              }
              else if (event.type === "error") {
                setMessages(prev => [...prev, { id: `err-${Date.now()}`, role: "system", text: `Error: ${event.message}`, isError: true }]);
              }
            } catch (jsonErr) {
              console.error("Error parsing event line", jsonErr, line);
            }
          }
        }
      }
    } catch (error) {
      console.error("Streaming error:", error);
      setMessages(prev => [...prev, { id: `err-${Date.now()}`, role: "system", text: `System Error: ${error.message}`, isError: true }]);
    } finally {
      setIsStreaming(false);
    }
  };

  // Helper to format ISO dates
  const formatEventTime = (isoString) => {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatEventDate = (isoString) => {
    const d = new Date(isoString);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col antialiased">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50 px-6 py-4 flex items-center justify-between shadow-xs">
        <div className="flex items-center space-x-3">
          <div className="bg-blue-600 text-white p-2 rounded-xl shadow-md">
            <Cpu className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-800 tracking-tight m-0 leading-none">StudyOS</h1>
            <p className="text-xs text-slate-500 mt-1">Multi-Agent Academic Coordinator Engine</p>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="text-xs font-semibold text-emerald-700">Agents Online</span>
          </div>
          <button 
            onClick={fetchDashboardData} 
            className="p-2 text-slate-500 hover:bg-slate-100 rounded-lg transition-colors"
            title="Refresh Data"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Main Workspace Dashboard */}
      <div className="flex-1 max-w-[1600px] w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Side: Agent Orchestrator & Chat Control (Col 5) */}
        <section className="lg:col-span-5 flex flex-col space-y-6 min-h-[calc(100vh-140px)]">
          
          {/* Agent Activity Telemetry Panel */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
            <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider mb-4 flex items-center">
              <Activity className="h-4 w-4 text-blue-600 mr-2" />
              Agent Orchestration Sequence
            </h2>
            
            {/* Visual Agent Flow Diagram */}
            <div className="grid grid-cols-4 gap-2 items-center text-center py-2 relative">
              {[
                { name: "Coordinator", key: "CoordinatorAgent", desc: "Intent Router" },
                { name: "Email Agent", key: "EmailAgent", desc: "Gmail Parser" },
                { name: "Notes Agent", key: "NotesAgent", desc: "Filesystem" },
                { name: "Planner", key: "PlannerAgent", desc: "Calendar" }
              ].map((agent, idx) => {
                const isActive = activeAgent === agent.key;
                return (
                  <div key={agent.key} className="flex flex-col items-center relative z-10">
                    <div 
                      className={`h-12 w-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                        isActive 
                          ? "bg-blue-600 text-white ring-4 ring-blue-100 scale-110 shadow-md pulse-active"
                          : "bg-slate-100 text-slate-400 border border-slate-200"
                      }`}
                    >
                      {agent.name === "Coordinator" && <Cpu className="h-5 w-5" />}
                      {agent.name === "Email Agent" && <Mail className="h-5 w-5" />}
                      {agent.name === "Notes Agent" && <FileText className="h-5 w-5" />}
                      {agent.name === "Planner" && <CalendarIcon className="h-5 w-5" />}
                    </div>
                    <span className={`text-xs font-bold mt-2 ${isActive ? "text-blue-600" : "text-slate-500"}`}>
                      {agent.name}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5">{agent.desc}</span>
                  </div>
                );
              })}
            </div>

            {/* Micro-logs / Tool-trace panel */}
            <div className="mt-4 bg-slate-50 border border-slate-200 rounded-xl p-3 h-24 overflow-y-auto">
              {agentLogs.length === 0 ? (
                <p className="text-xs text-slate-400 italic text-center py-6">Orchestration logs will stream here...</p>
              ) : (
                <div className="space-y-1.5">
                  {agentLogs.map((log, idx) => (
                    <div key={idx} className="text-xs flex items-start space-x-1">
                      <span className="text-[10px] font-mono text-slate-400 mt-0.5">[{log.time}]</span>
                      <span className="text-slate-600 font-medium">{log.message}</span>
                      {log.meta && (
                        <span className="text-[10px] text-blue-600 bg-blue-50 px-1.5 py-0.2 rounded border border-blue-100 font-mono overflow-hidden truncate max-w-[150px]">
                          {JSON.stringify(log.meta)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Interactive Chat Panel */}
          <div className="bg-white rounded-2xl border border-slate-200 flex-1 flex flex-col overflow-hidden shadow-xs">
            {/* Thread Container */}
            <div className="flex-1 p-4 overflow-y-auto space-y-4 max-h-[420px]">
              {messages.map((msg, index) => {
                const isUser = msg.role === "user";
                const isSystem = msg.role === "system";
                return (
                  <div key={msg.id || index} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                    <div 
                      className={`max-w-[85%] rounded-2xl p-4 animate-fade-in ${
                        isUser 
                          ? "bg-blue-600 text-white rounded-tr-none"
                          : msg.isError 
                            ? "bg-rose-50 border border-rose-200 text-rose-800 rounded-tl-none flex items-center space-x-2"
                            : "bg-slate-100 text-slate-800 border border-slate-200 rounded-tl-none"
                      }`}
                    >
                      {!isUser && !isSystem && (
                        <div className="flex items-center space-x-1.5 mb-1.5 border-b border-slate-200 pb-1 text-[10px] uppercase tracking-wider font-bold text-slate-500">
                          <Activity className="h-3 w-3 text-blue-600" />
                          <span>{msg.agent || "Coordinator"} Output</span>
                        </div>
                      )}
                      {msg.isError && <AlertCircle className="h-5 w-5 text-rose-500 shrink-0" />}
                      <p className="text-sm whitespace-pre-wrap leading-relaxed m-0">{msg.text || (isStreaming ? "Thinking..." : "")}</p>
                    </div>
                  </div>
                );
              })}
              <div ref={chatEndRef} />
            </div>

            {/* Quick Action Pills */}
            <div className="px-4 py-2 border-t border-slate-150 flex flex-wrap gap-1.5 bg-slate-50">
              {QUICK_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(prompt.text)}
                  disabled={isStreaming}
                  className="text-xs bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 px-3 py-1.5 rounded-full transition-colors font-medium shadow-xs disabled:opacity-50"
                >
                  {prompt.label}
                </button>
              ))}
            </div>

            {/* Input Bar */}
            <div className="p-3 border-t border-slate-200 bg-white">
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                  placeholder="Ask Coordinator (e.g. Prepare for DBMS midterm)..."
                  className="flex-1 bg-slate-50 text-slate-800 text-sm border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all"
                  disabled={isStreaming}
                />
                <button
                  onClick={() => handleSendMessage()}
                  disabled={!inputText.trim() || isStreaming}
                  className="bg-blue-600 hover:bg-blue-700 text-white p-3 rounded-xl transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ArrowRight className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Right Side: Tabbed Academic Workspace Panels (Col 7) */}
        <section className="lg:col-span-7 flex flex-col space-y-6 min-h-[calc(100vh-140px)]">
          
          {/* Tab Selector */}
          <div className="bg-white rounded-2xl border border-slate-200 p-2 flex space-x-1 shadow-xs">
            <button
              onClick={() => setActiveTab("calendar")}
              className={`flex-1 py-3 px-4 rounded-xl text-sm font-semibold flex items-center justify-center space-x-2 transition-all ${
                activeTab === "calendar"
                  ? "bg-blue-600 text-white shadow-md"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <CalendarIcon className="h-4 w-4" />
              <span>Calendar Summary</span>
            </button>
            <button
              onClick={() => setActiveTab("emails")}
              className={`flex-1 py-3 px-4 rounded-xl text-sm font-semibold flex items-center justify-center space-x-2 transition-all ${
                activeTab === "emails"
                  ? "bg-blue-600 text-white shadow-md"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <Mail className="h-4 w-4" />
              <span>Academic Inbox</span>
            </button>
            <button
              onClick={() => setActiveTab("notes")}
              className={`flex-1 py-3 px-4 rounded-xl text-sm font-semibold flex items-center justify-center space-x-2 transition-all ${
                activeTab === "notes"
                  ? "bg-blue-600 text-white shadow-md"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <FileText className="h-4 w-4" />
              <span>Notes Workspace</span>
            </button>
          </div>

          {/* Workspace Panels */}
          <div className="flex-1 bg-white rounded-2xl border border-slate-200 p-6 flex flex-col shadow-xs overflow-hidden">
            
            {/* 1. Calendar Panel */}
            {activeTab === "calendar" && (
              <div className="flex-1 flex flex-col space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-800 m-0">Student Study Schedule</h2>
                    <p className="text-xs text-slate-500 mt-1">Calendar events synced from Google Calendar MCP</p>
                  </div>
                  <span className="text-xs bg-blue-50 text-blue-700 px-3 py-1 rounded-full border border-blue-200 font-semibold">
                    {calendarEvents.length} Scheduled Blocks
                  </span>
                </div>

                {calendarEvents.length === 0 ? (
                  <p className="text-sm text-slate-400 italic text-center py-12">No events scheduled. Ask Planner Agent to arrange study time!</p>
                ) : (
                  <div className="overflow-y-auto max-h-[460px] space-y-3 pr-1">
                    {calendarEvents.map((ev) => {
                      const isStudyBlock = ev.title.toLowerCase().includes("study") || ev.title.toLowerCase().includes("prepare");
                      return (
                        <div 
                          key={ev.id} 
                          className={`p-4 rounded-xl border flex items-start space-x-3 transition-all duration-300 hover:-translate-y-0.5 ${
                            isStudyBlock 
                              ? "bg-blue-50 border-blue-200 text-blue-800" 
                              : "bg-slate-50 border-slate-200 text-slate-800"
                          }`}
                        >
                          <div className={`p-2.5 rounded-lg ${isStudyBlock ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-600"}`}>
                            {isStudyBlock ? <Sparkles className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
                          </div>
                          <div className="flex-1">
                            <h3 className="text-sm font-bold m-0">{ev.title}</h3>
                            {ev.description && <p className="text-xs opacity-75 mt-1">{ev.description}</p>}
                            <div className="flex items-center space-x-2 mt-2 text-[10px] font-semibold opacity-70">
                              <span>{formatEventDate(ev.start)}</span>
                              <span>•</span>
                              <span>{formatEventTime(ev.start)} - {formatEventTime(ev.end)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* 2. Inbox / Emails Panel */}
            {activeTab === "emails" && (
              <div className="flex-1 flex flex-col space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-800 m-0">Gmail Student Inbox</h2>
                    <p className="text-xs text-slate-500 mt-1">Class announcements and homework alerts from Gmail MCP</p>
                  </div>
                </div>

                <div className="overflow-y-auto max-h-[460px] space-y-3 pr-1">
                  {emails.map((mail) => {
                    const bodyLower = mail.body.toLowerCase();
                    const hasDeadline = bodyLower.includes("deadline") || bodyLower.includes("due") || bodyLower.includes("exam");
                    return (
                      <div key={mail.id} className="bg-white border border-slate-200 rounded-xl p-4 hover:border-blue-300 transition-all">
                        <div className="flex justify-between items-start">
                          <div>
                            <span className="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono font-semibold">
                              From: {mail.sender}
                            </span>
                            <h3 className="text-sm font-bold text-slate-800 mt-1">{mail.subject}</h3>
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">{new Date(mail.date).toLocaleDateString()}</span>
                        </div>
                        <p className="text-xs text-slate-600 mt-2 leading-relaxed">{mail.body}</p>
                        {hasDeadline && (
                          <div className="mt-3 flex items-center space-x-1.5 bg-amber-50 text-amber-800 border border-amber-200 px-2.5 py-1 rounded-lg w-fit text-[10px] font-bold">
                            <Clock className="h-3 w-3 text-amber-600" />
                            <span>Actionable Deadline / Announcement Detected</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 3. Workspace Notes Panel */}
            {activeTab === "notes" && (
              <div className="flex-1 flex flex-col space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-800 m-0">Syllabus & Lecture Notes</h2>
                    <p className="text-xs text-slate-500 mt-1">Uploaded course sheets read by Filesystem MCP</p>
                  </div>
                  <div className="flex items-center space-x-2">
                    {uploadStatus && <span className="text-xs text-blue-600 font-medium">{uploadStatus}</span>}
                    <button
                      onClick={() => fileInputRef.current.click()}
                      className="bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 text-xs px-3.5 py-2 rounded-lg font-semibold flex items-center space-x-1.5 transition-all shadow-xs"
                    >
                      <Upload className="h-3.5 w-3.5" />
                      <span>Upload Note</span>
                    </button>
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      className="hidden"
                      accept=".txt,.md,.pdf"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 overflow-y-auto max-h-[460px] pr-1">
                  {notes.map((note) => (
                    <div 
                      key={note.name}
                      onClick={() => handleViewNote(note.name)}
                      className="border border-slate-200 rounded-xl p-4 hover:border-blue-400 hover:bg-slate-50/50 cursor-pointer transition-all flex items-start space-x-3"
                    >
                      <div className={`p-2.5 rounded-lg ${note.type === "pdf" ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"}`}>
                        <FileText className="h-5 w-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-bold text-slate-800 truncate m-0">{note.name}</h3>
                        <p className="text-xs text-slate-400 mt-1">{(note.size / 1024).toFixed(1)} KB • {note.type.toUpperCase()} file</p>
                        <span className="text-[10px] text-blue-600 hover:underline flex items-center space-x-1 mt-2.5 font-bold">
                          <Eye className="h-3 w-3" />
                          <span>View Content</span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Note View Overlay Modal */}
      {selectedNote && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl animate-fade-in">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50 rounded-t-2xl">
              <div>
                <h3 className="text-sm font-mono font-bold text-slate-700 uppercase tracking-wider">Viewing Workspace File</h3>
                <h2 className="text-base font-bold text-slate-800 mt-1">{selectedNote.name}</h2>
              </div>
              <button 
                onClick={() => setSelectedNote(null)}
                className="bg-slate-200 hover:bg-slate-350 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
              >
                Close Note
              </button>
            </div>
            <div className="flex-1 p-6 overflow-y-auto">
              <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono bg-slate-50 border border-slate-200 p-4 rounded-xl leading-relaxed">
                {selectedNote.content}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
