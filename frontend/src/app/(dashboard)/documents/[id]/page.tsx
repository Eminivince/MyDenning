"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { documents, analysis } from "@/lib/api/endpoints";
import { Download, FileText, RefreshCw, ShieldCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: doc, isLoading } = useQuery({ queryKey: ["document", id], queryFn: () => documents.get(id) });
  const [reviewing, setReviewing] = useState(false);
  const [reviewResult, setReviewResult] = useState<any>(null);

  async function handleReview() {
    setReviewing(true);
    try {
      const res = await analysis.review({ document_id: id });
      setReviewResult(res);
      toast.success("Document reviewed");
    } catch (err: any) {
      toast.error(err.detail || "Review failed");
    } finally {
      setReviewing(false);
    }
  }

  async function handleDownload() {
    try {
      const res = await documents.download(id);
      window.open(res.download_url, "_blank");
    } catch {}
  }

  if (isLoading) return <div className="space-y-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  if (!doc) return <p className="text-muted-foreground">Document not found</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">{doc.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{doc.file_name} &middot; {(doc.file_size / 1024).toFixed(0)} KB {doc.page_count && `\u00b7 ${doc.page_count} pages`}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleDownload}><Download className="mr-1 h-3.5 w-3.5" />Download</Button>
          <Button variant="outline" size="sm" onClick={handleReview} disabled={reviewing || doc.processing_status !== "completed"}>
            {reviewing ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="mr-1 h-3.5 w-3.5" />}
            Review
          </Button>
        </div>
      </div>

      <Tabs defaultValue="metadata">
        <TabsList>
          <TabsTrigger value="metadata">Metadata</TabsTrigger>
          <TabsTrigger value="review" disabled={!reviewResult}>Review Results</TabsTrigger>
        </TabsList>

        <TabsContent value="metadata" className="space-y-4 pt-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Details</CardTitle></CardHeader>
              <CardContent className="text-sm space-y-2">
                <Row label="Type" value={doc.document_type.replace(/_/g, " ")} />
                <Row label="Status" value={doc.processing_status} />
                <Row label="Jurisdiction" value={doc.jurisdiction || "—"} />
                <Row label="Governing Law" value={doc.governing_law || "—"} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Extracted Data</CardTitle></CardHeader>
              <CardContent className="text-sm space-y-2">
                <Row label="Parties" value={doc.parties ? JSON.stringify(doc.parties.extracted || []).slice(0, 80) : "—"} />
                <Row label="Effective Date" value={doc.effective_date ? new Date(doc.effective_date).toLocaleDateString() : "—"} />
                <Row label="Expiry Date" value={doc.expiry_date ? new Date(doc.expiry_date).toLocaleDateString() : "—"} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="review" className="space-y-4 pt-4">
          {reviewResult && (
            <>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm">Summary</CardTitle></CardHeader>
                <CardContent className="text-sm">{reviewResult.summary}</CardContent>
              </Card>
              {reviewResult.clauses?.length > 0 && (
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm">Clauses ({reviewResult.clauses.length})</CardTitle></CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {reviewResult.clauses.map((c: any, i: number) => (
                        <div key={i} className="rounded-md border p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span className="font-medium capitalize">{c.clause_type?.replace(/_/g, " ") || "Unknown"}</span>
                            {c.risk_level && <Badge variant={c.risk_level === "high" || c.risk_level === "critical" ? "destructive" : c.risk_level === "medium" ? "warning" : "secondary"}>{c.risk_level}</Badge>}
                          </div>
                          {c.clause_text && <p className="mt-1 text-muted-foreground line-clamp-2">{c.clause_text}</p>}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right capitalize">{value}</span>
    </div>
  );
}
