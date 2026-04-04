"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { documents, playbooks, legalFeatures, analysis } from "@/lib/api/endpoints";
import { GitCompare, Swords, Loader2, ChevronDown, ChevronRight, AlertTriangle, Shield, Target, Download } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils/cn";

const GAP_COLORS: Record<string, string> = {
  critical: "destructive", major: "destructive", minor: "warning", aligned: "success",
};

function NegotiationClauseCard({ clause, index }: { clause: any; index: number }) {
  const [open, setOpen] = useState(index < 3);
  return (
    <div className="rounded-md border">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 p-3 text-left text-sm font-medium hover:bg-secondary/50">
        {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
        <span className="flex-1 capitalize">{clause.clause_type?.replace(/_/g, " ") || `Clause ${index + 1}`}</span>
        <Badge variant={(GAP_COLORS[clause.gap_severity] || "secondary") as any} className="text-[10px]">{clause.gap_severity}</Badge>
        {clause.priority && <Badge variant="outline" className="text-[10px]">P{clause.priority}</Badge>}
      </button>
      {open && (
        <div className="space-y-3 border-t p-3 text-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md bg-red-50 p-2 dark:bg-red-950/20">
              <p className="mb-1 text-[10px] font-semibold uppercase text-red-600 dark:text-red-400">Their Position</p>
              <p className="text-xs">{clause.their_position}</p>
            </div>
            <div className="rounded-md bg-emerald-50 p-2 dark:bg-emerald-950/20">
              <p className="mb-1 text-[10px] font-semibold uppercase text-emerald-600 dark:text-emerald-400">Our Preferred</p>
              <p className="text-xs">{clause.our_preferred_position}</p>
            </div>
          </div>

          {clause.pushback_likelihood && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Pushback likelihood:</span>
              <Badge variant={clause.pushback_likelihood === "high" ? "destructive" : clause.pushback_likelihood === "medium" ? "warning" : "secondary"} className="text-[10px]">{clause.pushback_likelihood}</Badge>
              {clause.pushback_reason && <span className="text-xs text-muted-foreground">— {clause.pushback_reason}</span>}
            </div>
          )}

          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">Strategy</p>
            <p className="text-xs">{clause.strategy}</p>
          </div>

          {clause.counter_language && (
            <div className="rounded-md border bg-blue-50 p-2 dark:bg-blue-950/20">
              <p className="mb-1 text-[10px] font-semibold uppercase text-blue-600 dark:text-blue-400">Proposed Counter-Language</p>
              <p className="text-xs font-mono">{clause.counter_language}</p>
            </div>
          )}

          {clause.fallback_positions?.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">Fallback Positions (in order)</p>
              <ol className="list-decimal pl-4 text-xs space-y-1">
                {clause.fallback_positions.map((fb: string, i: number) => <li key={i}>{fb}</li>)}
              </ol>
            </div>
          )}

          {clause.walk_away_trigger && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 p-2 dark:bg-red-950/20">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
              <div>
                <p className="text-[10px] font-semibold text-red-600 dark:text-red-400">Walk-Away Trigger</p>
                <p className="text-xs">{clause.walk_away_trigger}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  const { data: docs } = useQuery({ queryKey: ["documents"], queryFn: () => documents.list() });
  const { data: pbs } = useQuery({ queryKey: ["playbooks"], queryFn: () => playbooks.list() });
  const completedDocs = docs?.filter((d) => d.processing_status === "completed") ?? [];

  // Redline state
  const [doc1, setDoc1] = useState("");
  const [doc2, setDoc2] = useState("");
  const [redlineLoading, setRedlineLoading] = useState(false);
  const [redlineResult, setRedlineResult] = useState<any>(null);

  // Negotiation state
  const [negDoc, setNegDoc] = useState("");
  const [negPlaybook, setNegPlaybook] = useState("");
  const [negCounterparty, setNegCounterparty] = useState("");
  const [negContext, setNegContext] = useState("");
  const [negPriorities, setNegPriorities] = useState("");
  const [negLoading, setNegLoading] = useState(false);
  const [negResult, setNegResult] = useState<any>(null);

  async function handleRedline() {
    if (!doc1 || !doc2) return;
    setRedlineLoading(true);
    try {
      const res = await legalFeatures.redline({ document_id_1: doc1, document_id_2: doc2 });
      setRedlineResult(res);
    } catch (err: any) { toast.error(err.detail || "Comparison failed"); }
    finally { setRedlineLoading(false); }
  }

  async function handleNegotiation() {
    if (!negDoc || !negPlaybook) return;
    setNegLoading(true);
    try {
      const res = await legalFeatures.negotiationStrategy({
        document_id: negDoc,
        playbook_id: negPlaybook,
        counterparty_name: negCounterparty || undefined,
        deal_context: negContext || undefined,
        priorities: negPriorities ? negPriorities.split(",").map((p) => p.trim()) : undefined,
      });
      setNegResult(res);
    } catch (err: any) { toast.error(err.detail || "Strategy generation failed"); }
    finally { setNegLoading(false); }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Tabs defaultValue="negotiate">
        <TabsList>
          <TabsTrigger value="negotiate" className="gap-1.5"><Swords className="h-3.5 w-3.5" />Negotiate</TabsTrigger>
          <TabsTrigger value="redline" className="gap-1.5"><GitCompare className="h-3.5 w-3.5" />Redline</TabsTrigger>
        </TabsList>

        {/* ===== NEGOTIATION ===== */}
        <TabsContent value="negotiate" className="space-y-6 pt-4">
          <Card>
            <CardContent className="space-y-4 pt-6">
              <p className="text-sm text-muted-foreground">
                Upload the counterparty&apos;s contract and select your playbook. Get a full negotiation strategy
                with counter-language, fallback positions, and pushback predictions.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">Counterparty&apos;s document</label>
                  <Select value={negDoc} onValueChange={setNegDoc}>
                    <SelectTrigger><SelectValue placeholder="Select document" /></SelectTrigger>
                    <SelectContent>{completedDocs.map((d) => <SelectItem key={d.id} value={d.id}>{d.title}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">Your playbook</label>
                  <Select value={negPlaybook} onValueChange={setNegPlaybook}>
                    <SelectTrigger><SelectValue placeholder="Select playbook" /></SelectTrigger>
                    <SelectContent>{pbs?.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input value={negCounterparty} onChange={(e) => setNegCounterparty(e.target.value)} placeholder="Counterparty name (for history lookup)" />
                <Input value={negPriorities} onChange={(e) => setNegPriorities(e.target.value)} placeholder="Priorities, comma separated (e.g. limit liability, retain IP)" />
              </div>
              <Textarea value={negContext} onChange={(e) => setNegContext(e.target.value)} placeholder="Deal context (e.g. Key vendor, must close by Q2, can't accept uncapped liability)" className="min-h-[60px]" />
              <Button onClick={handleNegotiation} disabled={!negDoc || !negPlaybook || negLoading}>
                {negLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Swords className="mr-2 h-4 w-4" />}
                {negLoading ? "Generating strategy..." : "Generate Negotiation Strategy"}
              </Button>
            </CardContent>
          </Card>

          {negResult && (
            <div className="space-y-4">
              {/* Executive Summary */}
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Negotiation Strategy</CardTitle>
                    <div className="flex items-center gap-2">
                      <Badge variant={negResult.overall_risk_level === "high" || negResult.overall_risk_level === "critical" ? "destructive" : "warning"}>
                        Risk: {negResult.overall_risk_level}
                      </Badge>
                      <Badge variant="outline">Stance: {negResult.counterparty_stance}</Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm">{negResult.executive_summary}</p>
                </CardContent>
              </Card>

              {/* Key intel cards */}
              <div className="grid gap-3 sm:grid-cols-3">
                {negResult.key_leverage_points?.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-xs flex items-center gap-1"><Target className="h-3.5 w-3.5" />Leverage Points</CardTitle></CardHeader>
                    <CardContent><ul className="space-y-1">{negResult.key_leverage_points.map((p: string, i: number) => <li key={i} className="text-xs text-muted-foreground">{p}</li>)}</ul></CardContent>
                  </Card>
                )}
                {negResult.concession_candidates?.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-xs flex items-center gap-1"><Shield className="h-3.5 w-3.5" />Concession Chips</CardTitle></CardHeader>
                    <CardContent><ul className="space-y-1">{negResult.concession_candidates.map((c: string, i: number) => <li key={i} className="text-xs text-muted-foreground">{c}</li>)}</ul></CardContent>
                  </Card>
                )}
                {negResult.red_lines?.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-xs flex items-center gap-1 text-red-500"><AlertTriangle className="h-3.5 w-3.5" />Red Lines</CardTitle></CardHeader>
                    <CardContent><ul className="space-y-1">{negResult.red_lines.map((r: string, i: number) => <li key={i} className="text-xs text-red-600 dark:text-red-400">{r}</li>)}</ul></CardContent>
                  </Card>
                )}
              </div>

              {/* Opening talking points */}
              {negResult.opening_talking_points?.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">Opening Talking Points</CardTitle></CardHeader>
                  <CardContent>
                    <ol className="list-decimal pl-4 space-y-1">
                      {negResult.opening_talking_points.map((p: string, i: number) => <li key={i} className="text-sm">{p}</li>)}
                    </ol>
                  </CardContent>
                </Card>
              )}

              {/* Clause-by-clause strategy */}
              {negResult.clauses?.length > 0 && (
                <Card>
                  <CardHeader className="pb-3"><CardTitle className="text-sm">Clause-by-Clause Strategy ({negResult.clauses.length} clauses)</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {negResult.clauses.map((clause: any, i: number) => (
                      <NegotiationClauseCard key={i} clause={clause} index={i} />
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Counterparty history */}
              {negResult.counterparty_history?.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">Prior Dealings with {negResult.counterparty}</CardTitle></CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {negResult.counterparty_history.map((h: any, i: number) => (
                        <div key={i} className="flex items-center justify-between rounded-md border p-2 text-xs">
                          <div>
                            <span className="font-medium">{h.matter_title}</span>
                            <span className="ml-2 text-muted-foreground">{h.role} — {h.jurisdiction}</span>
                          </div>
                          <Badge variant="secondary" className="text-[10px]">{h.matter_status}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        {/* ===== REDLINE ===== */}
        <TabsContent value="redline" className="space-y-6 pt-4">
          <Card>
            <CardContent className="space-y-4 pt-6">
              <p className="text-sm text-muted-foreground">Select two documents to generate a tracked-changes redline with legal commentary.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">Document 1 (original)</label>
                  <Select value={doc1} onValueChange={setDoc1}>
                    <SelectTrigger><SelectValue placeholder="Select document" /></SelectTrigger>
                    <SelectContent>{completedDocs.map((d) => <SelectItem key={d.id} value={d.id}>{d.title}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">Document 2 (revised)</label>
                  <Select value={doc2} onValueChange={setDoc2}>
                    <SelectTrigger><SelectValue placeholder="Select document" /></SelectTrigger>
                    <SelectContent>{completedDocs.filter((d) => d.id !== doc1).map((d) => <SelectItem key={d.id} value={d.id}>{d.title}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <Button onClick={handleRedline} disabled={!doc1 || !doc2 || redlineLoading}>
                {redlineLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <GitCompare className="mr-2 h-4 w-4" />}
                {redlineLoading ? "Generating redline..." : "Generate Redline"}
              </Button>
            </CardContent>
          </Card>

          {redlineResult && (
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Redline Summary</CardTitle>
                    <div className="flex items-center gap-2">
                      <Badge variant="success">{redlineResult.additions} additions</Badge>
                      <Badge variant="destructive">{redlineResult.deletions} deletions</Badge>
                      <Badge variant="warning">{redlineResult.modifications} modifications</Badge>
                      {redlineResult.id && (
                        <Button variant="outline" size="sm" onClick={async () => {
                          try {
                            const { blob, filename } = await analysis.exportDocx(String(redlineResult.id));
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a"); a.href = url; a.download = filename;
                            document.body.appendChild(a); a.click(); document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                          } catch { toast.error("Export failed"); }
                        }}>
                          <Download className="mr-1 h-3.5 w-3.5" />Word
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent><p className="text-sm">{redlineResult.summary}</p></CardContent>
              </Card>

              <Tabs defaultValue="changes">
                <TabsList>
                  <TabsTrigger value="changes">Changes ({redlineResult.total_changes})</TabsTrigger>
                  <TabsTrigger value="redline-view">Redline View</TabsTrigger>
                </TabsList>
                <TabsContent value="changes" className="space-y-2 pt-4">
                  {redlineResult.changes?.map((c: any, i: number) => (
                    <Card key={i}>
                      <CardContent className="p-3 text-sm">
                        <div className="flex items-center justify-between mb-2">
                          <Badge variant="outline" className="capitalize text-[10px]">{c.change_type}</Badge>
                          {c.risk_level && <Badge variant={c.risk_level === "high" || c.risk_level === "critical" ? "destructive" : c.risk_level === "medium" ? "warning" : "secondary"} className="text-[10px]">{c.risk_level}</Badge>}
                        </div>
                        {c.legal_significance && <p className="text-sm">{c.legal_significance}</p>}
                        {c.commentary && <p className="mt-1 text-xs text-muted-foreground">{c.commentary}</p>}
                      </CardContent>
                    </Card>
                  ))}
                </TabsContent>
                <TabsContent value="redline-view" className="pt-4">
                  <Card>
                    <CardContent className="p-4">
                      <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap font-mono text-xs" dangerouslySetInnerHTML={{ __html: redlineResult.html_redline || "" }} />
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
