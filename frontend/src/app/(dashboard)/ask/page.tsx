"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { analysis } from "@/lib/api/endpoints";
import { Send, Loader2, AlertTriangle, BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import type { AskResponse, IssueAnalysis, RiskLevel } from "@/lib/types";
import ReactMarkdown from "react-markdown";

const RISK_VARIANT: Record<RiskLevel, "destructive" | "warning" | "info" | "success" | "secondary"> = {
  critical: "destructive",
  high: "destructive",
  medium: "warning",
  low: "success",
  info: "info",
};

function IssueCard({ issue, index }: { issue: IssueAnalysis; index: number }) {
  const [open, setOpen] = useState(index === 0);
  return (
    <div className="rounded-md border">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium hover:bg-secondary/50">
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
                    {a.authority_level === "binding" && <Badge variant="outline" className="text-[10px]">Binding</Badge>}
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

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    try {
      const res = await analysis.ask({
        question,
        jurisdiction: jurisdiction || undefined,
      });
      setResult(res);
    } catch (err: any) {
      toast.error(err.detail || "Failed to get answer");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Query form */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a legal question...&#10;&#10;e.g. Can we tokenize this asset under Nigerian law?&#10;e.g. What are the termination risks in this agreement?"
              className="min-h-[120px] resize-none"
            />
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-xs text-muted-foreground">Jurisdiction (optional)</label>
                <Select value={jurisdiction} onValueChange={setJurisdiction}>
                  <SelectTrigger>
                    <SelectValue placeholder="Any jurisdiction" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Any</SelectItem>
                    <SelectItem value="NG">Nigeria</SelectItem>
                    <SelectItem value="GB">United Kingdom</SelectItem>
                    <SelectItem value="US">United States</SelectItem>
                    <SelectItem value="EU">European Union</SelectItem>
                    <SelectItem value="KE">Kenya</SelectItem>
                    <SelectItem value="ZA">South Africa</SelectItem>
                    <SelectItem value="GH">Ghana</SelectItem>
                    <SelectItem value="CA">Canada</SelectItem>
                    <SelectItem value="IN">India</SelectItem>
                    <SelectItem value="AU">Australia</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={loading || !question.trim()}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                {loading ? "Analyzing..." : "Ask"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Answer */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Answer</CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">Confidence: {Math.round(result.confidence_score * 100)}%</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown>{result.answer}</ReactMarkdown>
              </div>
            </CardContent>
          </Card>

          {/* Risk Flags */}
          {result.risk_flags?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {result.risk_flags.map((flag, i) => (
                <Badge key={i} variant="warning" className="gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {flag}
                </Badge>
              ))}
            </div>
          )}

          {/* IRAC Issues */}
          {result.issues?.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Legal Analysis (IRAC)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {result.issues.map((issue, i) => (
                  <IssueCard key={i} issue={issue} index={i} />
                ))}
              </CardContent>
            </Card>
          )}

          {/* Citations */}
          {result.citations?.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Sources Cited</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {result.citations.map((cite, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                      <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <div>
                        <p className="font-medium">{cite.citation_text}</p>
                        {cite.source_title && <p className="text-muted-foreground">{cite.source_title}</p>}
                        {cite.relevant_passage && (
                          <p className="mt-1 text-xs text-muted-foreground italic">"{cite.relevant_passage.slice(0, 200)}..."</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Follow-up Questions */}
          {result.follow_up_questions?.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Follow-up Questions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {result.follow_up_questions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => { setQuestion(q); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                      className="block w-full rounded-md p-2 text-left text-sm text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
