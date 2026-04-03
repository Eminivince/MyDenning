"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { documents } from "@/lib/api/endpoints";
import { legalFeatures } from "@/lib/api/endpoints";
import { GitCompare, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function ComparePage() {
  const { data: docs } = useQuery({ queryKey: ["documents"], queryFn: () => documents.list() });
  const [doc1, setDoc1] = useState("");
  const [doc2, setDoc2] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function handleCompare() {
    if (!doc1 || !doc2) return;
    setLoading(true);
    try {
      const res = await legalFeatures.redline({ document_id_1: doc1, document_id_2: doc2 });
      setResult(res);
    } catch (err: any) {
      toast.error(err.detail || "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  const completedDocs = docs?.filter((d) => d.processing_status === "completed") ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
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
          <Button onClick={handleCompare} disabled={!doc1 || !doc2 || loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <GitCompare className="mr-2 h-4 w-4" />}
            {loading ? "Generating redline..." : "Generate Redline"}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Redline Summary</CardTitle>
                <div className="flex gap-2">
                  <Badge variant="success">{result.additions} additions</Badge>
                  <Badge variant="destructive">{result.deletions} deletions</Badge>
                  <Badge variant="warning">{result.modifications} modifications</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent><p className="text-sm">{result.summary}</p></CardContent>
          </Card>

          <Tabs defaultValue="changes">
            <TabsList>
              <TabsTrigger value="changes">Changes ({result.total_changes})</TabsTrigger>
              <TabsTrigger value="redline">Redline View</TabsTrigger>
            </TabsList>
            <TabsContent value="changes" className="space-y-2 pt-4">
              {result.changes?.map((c: any, i: number) => (
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
            <TabsContent value="redline" className="pt-4">
              <Card>
                <CardContent className="p-4">
                  <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap font-mono text-xs" dangerouslySetInnerHTML={{ __html: result.html_redline || "" }} />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
