"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { conversations, analysis } from "@/lib/api/endpoints";
import {
  Send, Loader2, AlertTriangle, BookOpen, ChevronDown,
  ChevronRight, Plus, MessageSquare, Scale, User,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils/cn";
import type { AskResponse, Conversation, IssueAnalysis, Message, RiskLevel } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import { formatDistanceToNow } from "date-fns";

// ===== Constants =====

const RISK_VARIANT: Record<RiskLevel, "destructive" | "warning" | "info" | "success" | "secondary"> = {
  critical: "destructive", high: "destructive", medium: "warning", low: "success", info: "info",
};

const JURISDICTIONS = [
  { value: "", label: "Any jurisdiction" },
  { value: "NG", label: "Nigeria" },
  { value: "GB", label: "United Kingdom" },
  { value: "US", label: "United States" },
  { value: "EU", label: "European Union" },
  { value: "KE", label: "Kenya" },
  { value: "ZA", label: "South Africa" },
  { value: "GH", label: "Ghana" },
  { value: "CA", label: "Canada" },
  { value: "IN", label: "India" },
  { value: "AU", label: "Australia" },
];

// ===== Sub-components =====

function IssueCard({ issue, index }: { issue: IssueAnalysis; index: number }) {
  const [open, setOpen] = useState(index === 0);
  return (
    <div className="rounded-md border">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium hover:bg-secondary/50"
      >
        {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
        <span className="flex-1">{issue.issue}</span>
        <Badge variant={RISK_VARIANT[issue.risk_level]}>{issue.risk_level}</Badge>
      </button>
      {open && (
        <div className="space-y-3 border-t p-3 text-sm">
          <div>
            <p className="mb-1 font-medium text-muted-foreground">Rule</p>
            <p>{issue.rule}</p>
          </div>
          {issue.authority?.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-muted-foreground">Authority</p>
              <ul className="space-y-1">
                {issue.authority.map((a, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <BookOpen className="h-3 w-3 shrink-0 text-muted-foreground" />
                    <span>{a.citation_text}</span>
                    {a.authority_level === "binding" && (
                      <Badge variant="outline" className="text-[10px]">Binding</Badge>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <p className="mb-1 font-medium text-muted-foreground">Analysis</p>
            <p>{issue.analysis}</p>
          </div>
          {issue.uncertainty && (
            <div className="flex items-start gap-2 rounded-md bg-amber-50 p-2 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{issue.uncertainty}</p>
            </div>
          )}
          <div>
            <p className="mb-1 font-medium text-muted-foreground">Recommendation</p>
            <p>{issue.recommendation}</p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Try to parse a message's content as structured IRAC JSON. Falls back to plain markdown. */
function AssistantMessage({ content }: { content: string }) {
  let parsed: AskResponse | null = null;
  try {
    const obj = JSON.parse(content);
    if (obj.answer || obj.issues) parsed = obj;
  } catch {
    // not JSON — render as markdown
  }

  if (!parsed) {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Main answer */}
      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{parsed.answer}</ReactMarkdown>
      </div>

      {/* Confidence + risk */}
      <div className="flex flex-wrap items-center gap-2">
        {parsed.confidence_score != null && (
          <Badge variant="outline">Confidence: {Math.round(parsed.confidence_score * 100)}%</Badge>
        )}
        {parsed.risk_flags?.map((flag, i) => (
          <Badge key={i} variant="warning" className="gap-1">
            <AlertTriangle className="h-3 w-3" />{flag}
          </Badge>
        ))}
      </div>

      {/* IRAC Issues */}
      {parsed.issues?.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Legal Analysis (IRAC)</p>
          {parsed.issues.map((issue, i) => (
            <IssueCard key={i} issue={issue} index={i} />
          ))}
        </div>
      )}

      {/* Citations */}
      {parsed.citations?.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Sources</p>
          {parsed.citations.map((cite, i) => (
            <div key={i} className="flex items-start gap-2 rounded-md border p-2 text-sm">
              <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="font-medium">{cite.citation_text}</p>
                {cite.source_title && <p className="text-xs text-muted-foreground">{cite.source_title}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === "user";
  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      <div className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
        isUser ? "bg-primary text-primary-foreground" : "bg-secondary"
      )}>
        {isUser ? <User className="h-3.5 w-3.5" /> : <Scale className="h-3.5 w-3.5" />}
      </div>
      <div className={cn(
        "max-w-[85%] rounded-lg px-4 py-3",
        isUser ? "bg-primary text-primary-foreground" : "bg-card border"
      )}>
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{content}</p>
        ) : (
          <AssistantMessage content={content} />
        )}
      </div>
    </div>
  );
}

// ===== Conversation Sidebar =====

function ConversationList({
  active,
  onSelect,
  onNew,
}: {
  active: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const { data: convos } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => conversations.list({ page_size: 50 }),
  });

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r bg-card">
      <div className="flex items-center justify-between border-b px-3 py-3">
        <span className="text-sm font-semibold">Conversations</span>
        <Button variant="ghost" size="icon" onClick={onNew} title="New conversation">
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {convos?.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={cn(
              "flex w-full flex-col gap-0.5 border-b px-3 py-2.5 text-left transition-colors hover:bg-secondary/50",
              active === c.id && "bg-secondary"
            )}
          >
            <span className="truncate text-sm font-medium">
              {c.title || "New conversation"}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {formatDistanceToNow(new Date(c.updated_at), { addSuffix: true })}
            </span>
          </button>
        ))}
        {(!convos || convos.length === 0) && (
          <p className="p-4 text-center text-xs text-muted-foreground">No conversations yet</p>
        )}
      </div>
    </div>
  );
}

// ===== Main Page =====

export default function AskPage() {
  const queryClient = useQueryClient();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [activeConvo, setActiveConvo] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [sending, setSending] = useState(false);

  // Fetch messages for active conversation
  const { data: messages, refetch: refetchMessages } = useQuery({
    queryKey: ["messages", activeConvo],
    queryFn: () => (activeConvo ? conversations.messages(activeConvo) : Promise.resolve([])),
    enabled: !!activeConvo,
  });

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Create a new conversation
  async function handleNewConversation() {
    setActiveConvo(null);
    setQuestion("");
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  // Send a message (creates conversation if none active)
  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      let convoId = activeConvo;

      // Create conversation if none active
      if (!convoId) {
        const convo = await conversations.create({
          mode: "ask",
          title: text.length > 60 ? text.slice(0, 57) + "..." : text,
        });
        convoId = convo.id;
        setActiveConvo(convoId);
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
      }

      // Send the message — backend handles the full reasoning pipeline
      // and returns the assistant's response
      await conversations.send(convoId, text);
      setQuestion("");
      await refetchMessages();
    } catch (err: any) {
      toast.error(err.detail || "Failed to send message");
    } finally {
      setSending(false);
    }
  }

  // Click a follow-up suggestion
  function handleFollowUp(text: string) {
    setQuestion(text);
  }

  // Extract follow-up questions from the last assistant message
  let followUps: string[] = [];
  if (messages && messages.length > 0) {
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    if (lastAssistant) {
      try {
        const parsed = JSON.parse(lastAssistant.content);
        if (parsed.follow_up_questions) followUps = parsed.follow_up_questions;
      } catch {
        // not JSON
      }
    }
  }

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)]">
      {/* Sidebar */}
      <ConversationList
        active={activeConvo}
        onSelect={(id) => { setActiveConvo(id); setQuestion(""); }}
        onNew={handleNewConversation}
      />

      {/* Main area */}
      <div className="flex flex-1 flex-col">
        {/* Jurisdiction selector */}
        <div className="flex items-center gap-3 border-b px-4 py-2">
          <Select value={jurisdiction} onValueChange={setJurisdiction}>
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue placeholder="Jurisdiction" />
            </SelectTrigger>
            <SelectContent>
              {JURISDICTIONS.map((j) => (
                <SelectItem key={j.value} value={j.value}>{j.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {activeConvo && messages && messages.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {messages.length} message{messages.length !== 1 ? "s" : ""} in this conversation
            </span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!activeConvo && (!messages || messages.length === 0) ? (
            // Empty state
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-secondary">
                <Scale className="h-7 w-7 text-muted-foreground" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">Ask MyDenning</h2>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">
                Ask any legal question. Get IRAC-structured analysis with citations,
                risk flags, and confidence scores. Follow up to dig deeper.
              </p>
              <div className="mt-6 grid gap-2">
                {[
                  "Can we tokenize this asset under Nigerian law?",
                  "What are the termination risks in this agreement?",
                  "Compare data protection under GDPR vs NDPR",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setQuestion(q)}
                    className="rounded-lg border px-4 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            // Message thread
            <div className="mx-auto max-w-3xl space-y-4">
              {messages?.map((msg) => (
                <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
              ))}
              {sending && (
                <div className="flex gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary">
                    <Scale className="h-3.5 w-3.5" />
                  </div>
                  <div className="rounded-lg border bg-card px-4 py-3">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Analyzing...
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Follow-up suggestions */}
        {followUps.length > 0 && !sending && (
          <div className="border-t bg-card/50 px-6 py-2">
            <div className="mx-auto flex max-w-3xl gap-2 overflow-x-auto">
              {followUps.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleFollowUp(q)}
                  className="shrink-0 rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                >
                  {q.length > 60 ? q.slice(0, 57) + "..." : q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input */}
        <div className="border-t bg-card px-6 py-3">
          <form onSubmit={handleSend} className="mx-auto flex max-w-3xl gap-3">
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(e); }
              }}
              placeholder={activeConvo ? "Follow up..." : "Ask a legal question..."}
              className="min-h-[44px] max-h-[120px] resize-none"
              rows={1}
            />
            <Button type="submit" size="icon" disabled={sending || !question.trim()} className="shrink-0 self-end">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
