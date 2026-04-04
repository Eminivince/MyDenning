"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { analysis } from "@/lib/api/endpoints";
import { PenTool, Loader2, Copy, Check, Download } from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const DRAFT_TYPES = [
  { value: "memo", label: "Legal Memo" },
  { value: "contract", label: "Contract Draft" },
  { value: "board_resolution", label: "Board Resolution" },
  { value: "legal_email", label: "Legal Email" },
  { value: "negotiation_fallback", label: "Negotiation Language" },
  { value: "issue_list", label: "Issue List" },
];

export default function DraftPage() {
  const [draftType, setDraftType] = useState("memo");
  const [instructions, setInstructions] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [tone, setTone] = useState("formal");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  async function handleGenerate() {
    if (!instructions.trim()) return;
    setLoading(true);
    try {
      const res = await analysis.draft({ draft_type: draftType, instructions, jurisdiction: jurisdiction || undefined, tone });
      setResult(res);
    } catch (err: any) {
      toast.error(err.detail || "Failed to generate");
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    if (result?.content) { navigator.clipboard.writeText(result.content); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <Select value={draftType} onValueChange={setDraftType}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{DRAFT_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={jurisdiction} onValueChange={setJurisdiction}>
              <SelectTrigger><SelectValue placeholder="Jurisdiction" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">Any</SelectItem>
                <SelectItem value="NG">Nigeria</SelectItem>
                <SelectItem value="GB">United Kingdom</SelectItem>
                <SelectItem value="US">United States</SelectItem>
              </SelectContent>
            </Select>
            <Select value={tone} onValueChange={setTone}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="formal">Formal</SelectItem>
                <SelectItem value="advisory">Advisory</SelectItem>
                <SelectItem value="internal">Internal</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Describe what you need drafted...&#10;&#10;e.g. Draft a memo analyzing whether our client can enforce the non-compete clause in the employment agreement given that the employee relocated to a different jurisdiction." className="min-h-[120px]" />
          <Button onClick={handleGenerate} disabled={loading || !instructions.trim()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PenTool className="mr-2 h-4 w-4" />}
            {loading ? "Generating..." : "Generate Draft"}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <CardTitle className="text-base capitalize">{result.draft_type?.replace(/_/g, " ")} Draft</CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant="outline">Confidence: {Math.round((result.confidence_score || 0) * 100)}%</Badge>
              <Button variant="ghost" size="sm" onClick={handleCopy}>
                {copied ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </Button>
              {result.id && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    try {
                      const { blob, filename } = await analysis.exportDocx(result.id);
                      triggerDownload(blob, filename);
                      toast.success("Downloaded as Word document");
                    } catch { toast.error("Export failed"); }
                  }}
                >
                  <Download className="mr-1 h-3.5 w-3.5" />Word
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <ReactMarkdown>{result.content}</ReactMarkdown>
            </div>
            {result.risk_flags?.length > 0 && (
              <div className="mt-4 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Risk Flags</p>
                {result.risk_flags.map((f: string, i: number) => <p key={i} className="text-xs text-amber-600 dark:text-amber-400">{f}</p>)}
              </div>
            )}
            {result.assumptions?.length > 0 && (
              <div className="mt-3 space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Assumptions</p>
                {result.assumptions.map((a: string, i: number) => <p key={i} className="text-xs text-muted-foreground">{a}</p>)}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
