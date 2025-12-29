import { useState, useEffect, useRef } from "react";
import {
  Send,
  Moon,
  Sun,
  Mail,
  Calendar,
  FolderOpen,
  Loader2,
  Trash2,
  MessageSquare,
  Plus,
  CheckCircle2,
  LogOut,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: {
    text: string;
    actions?: string[];
  };
  intent?: any;
  created_at?: string;
}

interface Conversation {
  id: string;
  name: string;
  created_at: string;
  updated_at?: string;
}

const App = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [authStatus, setAuthStatus] = useState({
    connected: false,
    services: { gmail: false, calendar: false, drive: false },
    user_email: null as string | null,
  });
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<
    string | null
  >(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    checkAuthStatus();
    loadConversations();
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const checkAuthStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/auth/status`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setAuthStatus(data);
      }
    } catch (err) {
      console.error("Auth check failed:", err);
    }
  };

  const loadConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/conversations`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setConversations(data.conversations || []);
      }
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  };

  const loadConversationMessages = async (conversationId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/v1/conversations/${conversationId}/messages`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
        setCurrentConversationId(conversationId);
      }
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  };

  const deleteConversation = async (conversationId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/v1/conversations/${conversationId}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== conversationId));
        if (currentConversationId === conversationId) {
          setMessages([]);
          setCurrentConversationId(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const connectGoogle = () => {
    window.location.href = `${API_BASE}/v1/auth/google`;
  };

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
      setAuthStatus({
        connected: false,
        services: { gmail: false, calendar: false, drive: false },
        user_email: null,
      });
      setMessages([]);
      setConversations([]);
      setCurrentConversationId(null);
    } catch (err) {
      console.error("Logout failed:", err);
    }
  };

  const startNewConversation = () => {
    setMessages([]);
    setCurrentConversationId(null);
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: { text: input },
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/v1/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          query: input,
          conversation_id: currentConversationId,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (data.detail?.requires_auth || data.requires_auth) {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now().toString(),
              role: "assistant",
              content: {
                text:
                  data.detail?.message ||
                  data.message ||
                  "Please connect your Google account to continue.",
              },
            },
          ]);
        } else {
          throw new Error(data.detail || "Request failed");
        }
      } else {
        const assistantMsg: Message = {
          id: Date.now().toString(),
          role: "assistant",
          content: {
            text: data.response,
            actions: data.actions_taken,
          },
          intent: data.intent,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        if (data.conversation_id && !currentConversationId) {
          setCurrentConversationId(data.conversation_id);
          loadConversations();
        }
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: { text: `Error: ${err.message}` },
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const ServiceBadge = ({
    service,
    connected,
  }: {
    service: string;
    connected: boolean;
  }) => {
    const icons: Record<string, any> = {
      gmail: Mail,
      calendar: Calendar,
      drive: FolderOpen,
    };
    const Icon = icons[service];
    return (
      <div
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
          connected
            ? "bg-green-500/20 text-green-600 dark:text-green-400"
            : "bg-gray-200/50 text-gray-500 dark:bg-gray-800/50 dark:text-gray-400"
        }`}
      >
        <Icon size={14} />
        <span className="capitalize">{service}</span>
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors">
      {showSidebar && (
        <div className="w-80 border-r border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-gray-900">
          <div className="p-4 border-b border-gray-200 dark:border-gray-800">
            <button
              onClick={startNewConversation}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
            >
              <Plus size={20} />
              New Conversation
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 px-2">
              Recent Conversations
            </div>
            {conversations.length === 0 ? (
              <div className="text-center py-8 text-sm text-gray-500">
                No conversations yet
              </div>
            ) : (
              <div className="space-y-1">
                {conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
                      currentConversationId === conv.id
                        ? "bg-blue-50 dark:bg-blue-900/20"
                        : "hover:bg-gray-100 dark:hover:bg-gray-800"
                    }`}
                  >
                    <div
                      onClick={() => loadConversationMessages(conv.id)}
                      className="flex-1 min-w-0"
                    >
                      <div className="flex items-center gap-2">
                        <MessageSquare
                          size={16}
                          className="text-gray-400 shrink-0"
                        />
                        <div className="text-sm font-medium truncate">
                          {conv.name}
                        </div>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {new Date(
                          conv.updated_at || conv.created_at
                        ).toLocaleDateString()}
                      </div>
                    </div>
                    <button
                      onClick={() => deleteConversation(conv.id)}
                      className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-opacity"
                    >
                      <Trash2 size={16} className="text-red-500" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-4 border-t border-gray-200 dark:border-gray-800">
            {authStatus.user_email && (
              <div className="mb-3">
                <div className="text-xs text-gray-500 mb-1">Signed in as</div>
                <div className="text-sm font-medium truncate">
                  {authStatus.user_email}
                </div>
              </div>
            )}
            <button
              onClick={() => setShowSidebar(false)}
              className="w-full text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 py-2"
            >
              Hide Sidebar
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div className="flex items-center gap-4">
            {!showSidebar && (
              <button
                onClick={() => setShowSidebar(true)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              >
                <MessageSquare size={20} />
              </button>
            )}
            <div>
              <h1 className="text-xl font-semibold">Workspace Orchestrator</h1>
              <div className="flex gap-2 mt-2">
                <ServiceBadge
                  service="gmail"
                  connected={authStatus.services.gmail}
                />
                <ServiceBadge
                  service="calendar"
                  connected={authStatus.services.calendar}
                />
                <ServiceBadge
                  service="drive"
                  connected={authStatus.services.drive}
                />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {authStatus.connected && (
              <button
                onClick={logout}
                className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <LogOut size={18} />
                Logout
              </button>
            )}
            <button
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="max-w-2xl mx-auto text-center py-12">
              <div className="mb-6">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/20 mb-4">
                  <MessageSquare
                    size={32}
                    className="text-blue-600 dark:text-blue-400"
                  />
                </div>
                <h2 className="text-2xl font-semibold mb-2">
                  Welcome to Workspace Orchestrator
                </h2>
                <p className="text-gray-600 dark:text-gray-400 mb-6">
                  Ask me anything about your Gmail, Calendar, or Drive
                </p>
              </div>

              {!authStatus.connected && (
                <div className="mb-8 p-6 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 rounded-xl">
                  <h3 className="font-semibold mb-2">Get Started</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    Connect your Google account to start using the orchestrator
                  </p>
                  <button
                    onClick={connectGoogle}
                    className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
                  >
                    Connect Google Account
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left">
                <div className="p-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
                  <Mail
                    className="text-blue-600 dark:text-blue-400 mb-2"
                    size={24}
                  />
                  <h3 className="font-semibold mb-1">Gmail</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    "Find emails from sarah@company.com"
                  </p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
                  <Calendar
                    className="text-green-600 dark:text-green-400 mb-2"
                    size={24}
                  />
                  <h3 className="font-semibold mb-1">Calendar</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    "What's on my calendar next week?"
                  </p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
                  <FolderOpen
                    className="text-purple-600 dark:text-purple-400 mb-2"
                    size={24}
                  />
                  <h3 className="font-semibold mb-1">Drive</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    "Show me PDFs from last month"
                  </p>
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`mb-6 flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800"
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content.text}</div>

                {!authStatus.connected && msg.role === "assistant" && (
                  <button
                    onClick={connectGoogle}
                    className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                  >
                    Connect Google Account
                  </button>
                )}

                {msg.content.actions && msg.content.actions.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
                      Actions Performed:
                    </div>
                    <div className="space-y-1">
                      {msg.content.actions.map((action, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm">
                          <CheckCircle2
                            size={16}
                            className="text-green-500 mt-0.5 flex-shrink-0"
                          />
                          <span className="text-gray-700 dark:text-gray-300">
                            {action}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {msg.intent && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
                      Intent: {msg.intent.intent}
                    </div>
                    {msg.intent.services && msg.intent.services.length > 0 && (
                      <div className="flex gap-1 flex-wrap mt-1">
                        {msg.intent.services.map((svc: string) => (
                          <span
                            key={svc}
                            className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded"
                          >
                            {svc}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start mb-6">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl px-5 py-4">
                <Loader2 className="animate-spin text-blue-600" size={24} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div className="max-w-4xl mx-auto flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) =>
                e.key === "Enter" && !e.shiftKey && sendMessage()
              }
              placeholder="Ask about your workspace..."
              className="flex-1 px-4 py-3 bg-gray-100 dark:bg-gray-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
              disabled={loading}
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
            >
              <Send size={20} />
            </button>
          </div>
          <div className="max-w-4xl mx-auto mt-2 text-xs text-center text-gray-500">
            {authStatus.connected
              ? "Connected to Google Workspace"
              : "Connect your Google account to get started"}
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;
