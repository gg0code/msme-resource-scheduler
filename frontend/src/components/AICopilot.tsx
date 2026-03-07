// src/components/AICopilot.tsx — V3.0
// AI Copilot side panel — slides in from right
// Page-aware suggestions + free text input
// Calls POST /api/ai/chat with full conversation history

import { useState, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { X, Send, Bot, Sparkles, ChevronRight } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'

// ── Types ─────────────────────────────────────────────────────────────────────
interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface AICopilotProps {
  isOpen: boolean
  onClose: () => void
}

// ── Page context suggestions ──────────────────────────────────────────────────
const PAGE_SUGGESTIONS: Record<string, { icon: string; text: string }[]> = {
  dashboard: [
    { icon: '📊', text: "Today's shop floor summary" },
    { icon: '⚠️', text: 'Any alerts or delays?' },
    { icon: '💰', text: 'Revenue this month?' },
  ],
  jobs: [
    { icon: '💰', text: 'Cost breakdown for latest job?' },
    { icon: '👷', text: 'Best employee to assign?' },
    { icon: '📈', text: 'Any jobs running late?' },
  ],
  machines: [
    { icon: '✅', text: 'Which machines are free today?' },
    { icon: '📊', text: 'Machine utilisation this week?' },
    { icon: '🔧', text: 'Any maintenance due?' },
  ],
  employees: [
    { icon: '🙋', text: 'Who is available tomorrow?' },
    { icon: '🏆', text: 'Top performer this week?' },
    { icon: '⏰', text: 'Overtime hours this month?' },
  ],
  gantt: [
    { icon: '⚠️', text: 'Any scheduling conflicts?' },
    { icon: '📅', text: 'Busiest day this month?' },
    { icon: '🔄', text: 'Suggest reschedule for delays?' },
  ],
  availability: [
    { icon: '👷', text: 'Who is free this week?' },
    { icon: '⚙️', text: 'Any machine conflicts?' },
    { icon: '📆', text: 'Availability summary today?' },
  ],
}

const DEFAULT_SUGGESTIONS = [
  { icon: '📊', text: "Today's shop floor summary" },
  { icon: '⚠️', text: 'Any alerts or delays?' },
  { icon: '💰', text: 'Revenue this month?' },
]

function getPageContext(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean)
  return segments[0] || 'dashboard'
}

function getPageLabel(context: string): string {
  const labels: Record<string, string> = {
    dashboard: 'Dashboard',
    jobs: 'Jobs',
    machines: 'Machines',
    employees: 'Employees',
    gantt: 'Production Timeline',
    availability: 'Availability',
    skills: 'Skills',
    checker: 'Availability Checker',
  }
  return labels[context] || 'Dashboard'
}

// ── Message bubble ────────────────────────────────────────────────────────────
function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const time = message.timestamp.toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit',
  })

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end`}>
      {/* Avatar */}
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold
        ${isUser
          ? 'bg-gray-200 text-gray-600'
          : 'bg-gradient-to-br from-blue-600 to-violet-600 text-white'
        }`}>
        {isUser ? 'G' : <Bot size={14} />}
      </div>

      {/* Bubble */}
      <div className={`max-w-[80%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        <div className={`px-3 py-2.5 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-br-sm'
            : 'bg-gray-50 border border-gray-200 text-gray-800 rounded-bl-sm'
          }`}
          dangerouslySetInnerHTML={{ __html: formatMessage(message.content) }}
        />
        <span className="text-[10px] text-gray-400 px-1">{time}</span>
      </div>
    </div>
  )
}

// ── Format AI response — bold, line breaks ────────────────────────────────────
function formatMessage(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
    .replace(/₹([\d,]+)/g, '<span style="font-family:monospace;font-weight:600">₹$1</span>')
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="flex gap-2 items-end">
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0">
        <Bot size={14} className="text-white" />
      </div>
      <div className="bg-gray-50 border border-gray-200 px-4 py-3 rounded-2xl rounded-bl-sm">
        <div className="flex gap-1 items-center">
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AICopilot({ isOpen, onClose }: AICopilotProps) {
  const location = useLocation()
  const { user } = useAuth()
  const pageContext = getPageContext(location.pathname)
  const pageLabel   = getPageLabel(pageContext)
  const suggestions = PAGE_SUGGESTIONS[pageContext] || DEFAULT_SUGGESTIONS

  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Namaste! 👋 I'm your AI Copilot.\n\nI can see you're on **${pageLabel}**. Ask me anything about your shop floor — costs, jobs, machines, employees, or just tap a suggestion below.`,
      timestamp: new Date(),
    }
  ])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const messagesEndRef           = useRef<HTMLDivElement>(null)
  const inputRef                 = useRef<HTMLInputElement>(null)

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 300)
  }, [isOpen])

  // Update welcome message when page changes
  useEffect(() => {
    if (messages.length === 1) {
      setMessages([{
        role: 'assistant',
        content: `Namaste! 👋 I'm your AI Copilot.\n\nI can see you're on **${pageLabel}**. Ask me anything about your shop floor — costs, jobs, machines, employees, or just tap a suggestion below.`,
        timestamp: new Date(),
      }])
    }
  }, [pageContext])

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return

    const userMessage: Message = { role: 'user', content: text, timestamp: new Date() }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setLoading(true)

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({
          messages: updatedMessages.map(m => ({ role: m.role, content: m.content })),
          page_context: pageContext,
        }),
      })

      if (!response.ok) throw new Error('AI request failed')
      const data = await response.json()

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.reply,
        timestamp: new Date(),
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I ran into an issue. Please try again in a moment.',
        timestamp: new Date(),
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const clearChat = () => {
    setMessages([{
      role: 'assistant',
      content: `Namaste! 👋 Chat cleared. I'm still here — ask me anything about your shop floor.`,
      timestamp: new Date(),
    }])
  }

  return (
    <>
      {/* Backdrop — subtle on mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/10 z-30 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Side Panel */}
      <div className={`
        fixed top-0 right-0 h-full z-40
        w-[360px] bg-white border-l border-gray-200
        flex flex-col shadow-2xl
        transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : 'translate-x-full'}
      `}>

        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-3 flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center">
            <Bot size={18} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-white font-bold text-sm">AI Copilot</div>
            <div className="text-blue-100 text-xs flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
              Online · Llama 3.3 via Groq
            </div>
          </div>
          <button
            onClick={clearChat}
            className="text-blue-100 hover:text-white text-xs px-2 py-1 rounded hover:bg-white/10 transition-colors"
            title="Clear chat"
          >
            Clear
          </button>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-white/15 hover:bg-white/25 flex items-center justify-center transition-colors"
          >
            <X size={14} className="text-white" />
          </button>
        </div>

        {/* Context bar */}
        <div className="px-3 py-2 bg-blue-50 border-b border-blue-100 flex items-center gap-2 shrink-0">
          <Sparkles size={12} className="text-blue-500 shrink-0" />
          <span className="text-xs text-blue-600 font-medium">Context:</span>
          <span className="text-xs text-blue-800 font-semibold bg-blue-100 px-2 py-0.5 rounded-full">
            {pageLabel}
          </span>
          <span className="text-xs text-blue-400 ml-auto">Ask about any page</span>
        </div>

        {/* Suggestions */}
        <div className="px-3 pt-3 pb-2 border-b border-gray-100 shrink-0">
          <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide mb-2">
            💡 Suggested for {pageLabel}
          </p>
          <div className="flex flex-col gap-1.5">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => sendMessage(s.text)}
                disabled={loading}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 hover:bg-blue-50 border border-gray-200 hover:border-blue-300 text-left transition-all group disabled:opacity-50"
              >
                <span className="text-sm">{s.icon}</span>
                <span className="text-xs text-gray-700 group-hover:text-blue-700 font-medium flex-1">{s.text}</span>
                <ChevronRight size={12} className="text-gray-300 group-hover:text-blue-400 shrink-0" />
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-3">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}
          {loading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-3 py-3 border-t border-gray-200 bg-gray-50 shrink-0">
          <div className="flex gap-2 items-center">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about your shop..."
              disabled={loading}
              className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 placeholder-gray-400"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || loading}
              className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0 disabled:opacity-40 hover:shadow-md transition-all hover:scale-105 disabled:hover:scale-100"
            >
              <Send size={15} className="text-white" />
            </button>
          </div>
          <p className="text-[10px] text-gray-400 text-center mt-2">
            You can ask about any page even when viewing another
          </p>
        </div>

      </div>
    </>
  )
}
