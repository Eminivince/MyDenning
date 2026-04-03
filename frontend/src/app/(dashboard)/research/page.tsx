"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { legalSources } from "@/lib/api/endpoints";
import { Search, Loader2, ExternalLink, BookOpen, Scale } from "lucide-react";
import { toast } from "sonner";
import type { ExternalSearchResult } from "@/lib/types";

export default function ResearchPage() {
  const [query, setQuery] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [contentType, setContentType] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ExternalSearchResult[]>([]);
  const [sources, setSources] = useState<any[]>([]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await legalSources.search({
        query,
        jurisdiction: jurisdiction || undefined,
        content_type: contentType || undefined,
      });
      setResults(res.results || []);
      setSources(res.sources_queried || []);
    } catch (err: any) {
      toast.error(err.detail || "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search case law, statutes, regulations across jurisdictions..."
                className="pl-9"
              />
            </div>
            <div className="flex gap-3">
              <Select value={jurisdiction} onValueChange={setJurisdiction}>
                <SelectTrigger className="w-48"><SelectValue placeholder="Jurisdiction" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All jurisdictions</SelectItem>
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
              <Select value={contentType} onValueChange={setContentType}>
                <SelectTrigger className="w-48"><SelectValue placeholder="Content type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All types</SelectItem>
                  <SelectItem value="case_law">Case Law</SelectItem>
                  <SelectItem value="statute">Statutes</SelectItem>
                  <SelectItem value="regulation">Regulations</SelectItem>
                  <SelectItem value="guidance">Guidance</SelectItem>
                </SelectContent>
              </Select>
              <Button type="submit" disabled={loading || !query.trim()}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                Search
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Sources queried */}
      {sources.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Sources searched:</span>
          {sources.map((s: any, i: number) => (
            <Badge key={i} variant="outline" className="text-[10px]">
              {s.adapter} ({s.results} results, {s.time_ms}ms)
            </Badge>
          ))}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{results.length} results found</p>
          {results.map((r, i) => (
            <Card key={i} className="transition-colors hover:bg-secondary/30">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {r.content_type === "case_law" ? <Scale className="h-4 w-4 shrink-0 text-muted-foreground" /> : <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" />}
                      <p className="text-sm font-medium">{r.title}</p>
                    </div>
                    {r.citation && <p className="mt-1 text-xs font-mono text-muted-foreground">{r.citation}</p>}
                    {r.summary && <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{r.summary}</p>}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="text-[10px] capitalize">{r.content_type.replace(/_/g, " ")}</Badge>
                      <Badge variant="secondary" className="text-[10px]">{r.jurisdiction}</Badge>
                      {r.court_name && <span className="text-[10px] text-muted-foreground">{r.court_name}</span>}
                      {(r.date_decided || r.date_enacted) && <span className="text-[10px] text-muted-foreground">{r.date_decided || r.date_enacted}</span>}
                      <Badge variant={r.authority_level === "binding" ? "default" : "secondary"} className="text-[10px]">{r.authority_level}</Badge>
                      <span className="text-[10px] text-muted-foreground">via {r.source_adapter}</span>
                    </div>
                  </div>
                  {r.source_url && (
                    <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="shrink-0">
                      <Button variant="ghost" size="icon"><ExternalLink className="h-4 w-4" /></Button>
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
