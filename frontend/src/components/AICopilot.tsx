// src/components/AICopilot.tsx — V3.2
// - Chat tab: page-aware suggestions + free text
// - Tools tab: 50 pre-built prompts by category
// - Usage bar: daily query counter, 90% warning, 100% block

import { useState, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { X, Send, Bot, Sparkles, ChevronRight, Zap, MessageSquare } from 'lucide-react'
import { AI_TOOLS, AI_TOOL_CATEGORIES } from '../data/aiTools'
import apiClient from '../api/client'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface Usage {
  queries_used: number
  queries_limit: number
  queries_remaining: number
  usage_pct: number
  plan: string
}

interface AICopilotProps {
  isOpen: boolean
  onClose: () => void
}

const PAGE_SUGGESTIONS: Record<string, { icon: string; text: string }[]> = {
  dashboard:    [{ icon: '📊', text: "Today's shop floor summary" }, { icon: '⚠️', text: 'Any alerts or delays?' }, { icon: '💰', text: 'Revenue this month?' }],
  jobs:         [{ icon: '💰', text: 'Cost breakdown for latest job?' }, { icon: '👷', text: 'Best employee to assign?' }, { icon: '📈', text: 'Any jobs running late?' }],
  machines:     [{ icon: '✅', text: 'Which machines are free today?' }, { icon: '📊', text: 'Machine utilisation this week?' }, { icon: '🔧', text: 'Any maintenance due?' }],
  employees:    [{ icon: '🙋', text: 'Who is available tomorrow?' }, { icon: '🏆', text: 'Top performer this week?' }, { icon: '⏰', text: 'Overtime hours this month?' }],
  gantt:        [{ icon: '⚠️', text: 'Any scheduling conflicts?' }, { icon: '📅', text: 'Busiest day this month?' }, { icon: '🔄', text: 'Suggest reschedule for delays?' }],
  availability: [{ icon: '👷', text: 'Who is free this week?' }, { icon: '⚙️', text: 'Any machine conflicts?' }, { icon: '📆', text: 'Availability summary today?' }],
}

const DEFAULT_SUGGESTIONS = [
  { icon: '📊', text: "Today's shop floor summary" },
  { icon: '⚠️', text: 'Any alerts or delays?' },
  { icon: '💰', text: 'Revenue this month?' },
]

function getPageContext(p: string) { return p.split('/').filter(Boolean)[0] || 'dashboard' }
function getPageLabel(c: string) {
  return ({ dashboard: 'Dashboard', jobs: 'Jobs', machines: 'Machines', employees: 'Employees', gantt: 'Production Timeline', availability: 'Availability', skills: 'Skills', checker: 'Checker' })[c] || 'Dashboard'
}
function fmt(text: string) {
  return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>').replace(/₹([\d,]+)/g, '<span style="font-family:monospace;font-weight:600">₹$1</span>')
}

function UsageBar({ usage }: { usage: Usage | null }) {
  if (!usage) return null
  const pct = usage.usage_pct
  const bar = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-green-500'
  return (
    <div className="px-3 py-2 bg-gray-50 border-b border-gray-100 shrink-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wide">AI Queries · {usage.plan} plan</span>
        <span className={`text-[10px] font-bold ${pct >= 90 ? 'text-red-600' : 'text-gray-600'}`}>{usage.queries_used}/{usage.queries_limit}</span>
      </div>
      <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${bar}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      {pct >= 90 && pct < 100 && <p className="text-[10px] text-amber-600 mt-1 font-medium">⚠️ {usage.queries_remaining} queries remaining today</p>}
    </div>
  )
}

function LimitReached({ usage }: { usage: Usage }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 text-center gap-4">
      <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center"><span className="text-3xl">🚫</span></div>
      <div>
        <p className="font-bold text-gray-800 text-sm">Daily limit reached</p>
        <p className="text-xs text-gray-500 mt-1">You've used all {usage.queries_limit} AI queries today on the <strong>{usage.plan}</strong> plan.</p>
      </div>
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 w-full">
        <p className="text-xs font-semibold text-blue-800 mb-2">Upgrade your plan</p>
        <div className="space-y-1 text-xs text-blue-700">
          <p>✅ Pro — 500 queries/day</p>
          <p>✅ Enterprise — Unlimited</p>
        </div>
        <button className="mt-3 w-full py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-colors">Upgrade Plan</button>
      </div>
      <p className="text-[10px] text-gray-400">Resets at midnight</p>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const time   = message.timestamp.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${isUser ? 'bg-gray-200 text-gray-600' : 'bg-gradient-to-br from-blue-600 to-violet-600 text-white'}`}>
        {isUser ? 'U' : <Bot size={14} />}
      </div>
      <div className={`max-w-[80%] flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`px-3 py-2.5 rounded-2xl text-sm leading-relaxed ${isUser ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-br-sm' : 'bg-gray-50 border border-gray-200 text-gray-800 rounded-bl-sm'}`}
          dangerouslySetInnerHTML={{ __html: fmt(message.content) }}
        />
        <span className="text-[10px] text-gray-400 px-1">{time}</span>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-2 items-end">
      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0"><Bot size={14} className="text-white" /></div>
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

export default function AICopilot({ isOpen, onClose }: AICopilotProps) {
  const location    = useLocation()
  const pageContext = getPageContext(location.pathname)
  const pageLabel   = getPageLabel(pageContext)
  const suggestions = PAGE_SUGGESTIONS[pageContext] || DEFAULT_SUGGESTIONS

  const [tab, setTab]           = useState<'chat' | 'tools'>('chat')
  const [toolCat, setToolCat]   = useState('reporting')
  const [messages, setMessages] = useState<Message[]>([{
    role: 'assistant',
    content: `Namaste! 👋 I'm your AI Copilot.\n\nI can see you're on **${pageLabel}**. Use suggestions below or switch to **Tools** for 50 pre-built queries.`,
    timestamp: new Date(),
  }])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [usage, setUsage]       = useState<Usage | null>(null)
  const messagesEndRef           = useRef<HTMLDivElement>(null)
  const inputRef                 = useRef<HTMLInputElement>(null)

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => { if (isOpen) { setTimeout(() => inputRef.current?.focus(), 300); fetchUsage() } }, [isOpen])

  const fetchUsage = async () => {
    try {
      const res = await apiClient.get('/api/ai/usage')
      setUsage(res.data)
    } catch { /* silent */ }
  }

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return
    if (usage && usage.queries_remaining <= 0) return

    const userMsg: Message = { role: 'user', content: text, timestamp: new Date() }
    const updated = [...messages, userMsg]
    setMessages(updated)
    setInput('')
    setLoading(true)
    if (tab === 'tools') setTab('chat')

    try {
      const res = await apiClient.post('/api/ai/chat', {
        messages: updated.map(m => ({ role: m.role, content: m.content })),
        page_context: pageContext,
      })

      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply, timestamp: new Date() }])
      setUsage(prev => prev ? {
        ...prev,
        queries_used: res.data.queries_used,
        queries_limit: res.data.queries_limit,
        queries_remaining: res.data.queries_remaining,
        usage_pct: (res.data.queries_used / res.data.queries_limit) * 100
      } : prev)

    } catch (err: any) {
      if (err?.response?.status === 429) {
        const detail = err.response?.data?.detail || 'Daily query limit reached.'
        setMessages(prev => [...prev, { role: 'assistant', content: detail, timestamp: new Date() }])
        fetchUsage()
        return
      }
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I ran into an issue. Please try again.', timestamp: new Date() }])
    } finally {
      setLoading(false)
    }
  }

  const isLimitReached = usage && usage.queries_remaining <= 0
  const filteredTools  = AI_TOOLS.filter(t => t.category === toolCat)

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/10 z-30 lg:hidden" onClick={onClose} />}

      <div className={`fixed top-0 right-0 h-full z-40 w-[360px] bg-white border-l border-gray-200 flex flex-col shadow-2xl transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>

        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-3 flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center"><Bot size={18} className="text-white" /></div>
          <div className="flex-1 min-w-0">
            <div className="text-white font-bold text-sm">AI Copilot</div>
            <div className="text-blue-100 text-xs flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
              Online · Llama 3.3 via Groq
            </div>
          </div>
          <button onClick={() => setMessages([{ role: 'assistant', content: 'Chat cleared!', timestamp: new Date() }])} className="text-blue-100 hover:text-white text-xs px-2 py-1 rounded hover:bg-white/10 transition-colors">Clear</button>
          <button onClick={onClose} className="w-7 h-7 rounded-full bg-white/15 hover:bg-white/25 flex items-center justify-center transition-colors"><X size={14} className="text-white" /></button>
        </div>

        {/* Usage bar */}
        <UsageBar usage={usage} />

        {/* Tabs */}
        <div className="flex border-b border-gray-200 shrink-0">
          <button onClick={() => setTab('chat')} className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-semibold transition-colors ${tab === 'chat' ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50' : 'text-gray-500 hover:text-gray-700'}`}>
            <MessageSquare size={13} /> Chat
          </button>
          <button onClick={() => setTab('tools')} className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-semibold transition-colors ${tab === 'tools' ? 'text-violet-600 border-b-2 border-violet-600 bg-violet-50/50' : 'text-gray-500 hover:text-gray-700'}`}>
            <Zap size={13} /> Tools <span className="bg-gray-100 text-gray-600 text-[9px] px-1.5 py-0.5 rounded-full font-bold ml-0.5">50</span>
          </button>
        </div>

        {/* Limit reached */}
        {isLimitReached && tab === 'chat' ? <LimitReached usage={usage} /> :

        tab === 'chat' ? (
          <>
            {/* Context bar */}
            <div className="px-3 py-2 bg-blue-50 border-b border-blue-100 flex items-center gap-2 shrink-0">
              <Sparkles size={12} className="text-blue-500 shrink-0" />
              <span className="text-xs text-blue-600 font-medium">Context:</span>
              <span className="text-xs text-blue-800 font-semibold bg-blue-100 px-2 py-0.5 rounded-full">{pageLabel}</span>
              <span className="text-xs text-blue-400 ml-auto">Ask about any page</span>
            </div>

            {/* Suggestions */}
            <div className="px-3 pt-2.5 pb-2 border-b border-gray-100 shrink-0">
              <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide mb-1.5">💡 Suggested</p>
              <div className="flex flex-col gap-1">
                {suggestions.map((s, i) => (
                  <button key={i} onClick={() => sendMessage(s.text)} disabled={loading || !!isLimitReached}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 hover:bg-blue-50 border border-gray-200 hover:border-blue-300 text-left transition-all group disabled:opacity-50">
                    <span className="text-sm">{s.icon}</span>
                    <span className="text-xs text-gray-700 group-hover:text-blue-700 font-medium flex-1">{s.text}</span>
                    <ChevronRight size={11} className="text-gray-300 group-hover:text-blue-400 shrink-0" />
                  </button>
                ))}
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-3">
              {messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}
              {loading && <TypingIndicator />}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="px-3 py-3 border-t border-gray-200 bg-gray-50 shrink-0">
              <div className="flex gap-2 items-center">
                <input ref={inputRef} type="text" value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
                  placeholder="Ask anything about your shop..."
                  disabled={loading || !!isLimitReached}
                  className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder-gray-400"
                />
                <button onClick={() => sendMessage(input)} disabled={!input.trim() || loading || !!isLimitReached}
                  className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0 disabled:opacity-40 hover:shadow-md transition-all hover:scale-105 disabled:hover:scale-100">
                  <Send size={15} className="text-white" />
                </button>
              </div>
              {usage && <p className="text-[10px] text-gray-400 text-center mt-1.5">{usage.queries_remaining} queries remaining today</p>}
            </div>
          </>
        ) : (
          /* Tools Tab */
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="px-3 py-2.5 border-b border-gray-100 shrink-0">
              <div className="flex gap-1.5 flex-wrap">
                {AI_TOOL_CATEGORIES.map(cat => (
                  <button key={cat.id} onClick={() => setToolCat(cat.id)}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all ${toolCat === cat.id ? 'bg-violet-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                    <span>{cat.icon}</span> {cat.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2.5 flex flex-col gap-1.5">
              {filteredTools.map(tool => (
                <button key={tool.id} onClick={() => sendMessage(tool.prompt)} disabled={loading || !!isLimitReached}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-gray-50 hover:bg-violet-50 border border-gray-200 hover:border-violet-300 text-left transition-all group disabled:opacity-50">
                  <span className="text-lg shrink-0">{tool.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-gray-800 group-hover:text-violet-700">{tool.label}</p>
                    <p className="text-[10px] text-gray-400 truncate mt-0.5">{tool.prompt}</p>
                  </div>
                  <ChevronRight size={12} className="text-gray-300 group-hover:text-violet-400 shrink-0" />
                </button>
              ))}
            </div>
            {isLimitReached && (
              <div className="px-3 py-2 bg-red-50 border-t border-red-200 shrink-0">
                <p className="text-xs text-red-600 text-center font-medium">Daily limit reached — upgrade to continue</p>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
