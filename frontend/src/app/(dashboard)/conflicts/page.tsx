"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { legalFeatures } from "@/lib/api/endpoints";
import { Shield, Plus, Loader2, X, AlertTriangle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ConflictsPage() {
  const [partyNames, setPartyNames] = useState<string[]>([]);
  const [currentName, setCurrentName] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  function addParty() {
    if (currentName.trim() && !partyNames.includes(currentName.trim())) {
      setPartyNames([...partyNames, currentName.trim()]);
      setCurrentName("");
    }
  }

  function removeParty(name: string) {
    setPartyNames(partyNames.filter((n) => n !== name));
  }

  async function handleCheck() {
    if (partyNames.length === 0) return;
    setLoading(true);
    try {
      const res = await legalFeatures.conflictCheck({ party_names: partyNames });
      setResult(res);
    } catch (err: any) {
      toast.error(err.detail || "Check failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Conflict of Interest Check</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">Enter party names to check for conflicts across all matters in your organization.</p>
          <div className="flex gap-2">
            <Input value={currentName} onChange={(e) => setCurrentName(e.target.value)} placeholder="Party name (e.g. Acme Corporation)" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addParty())} />
            <Button variant="outline" onClick={addParty} disabled={!currentName.trim()}><Plus className="h-4 w-4" /></Button>
          </div>
          {partyNames.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {partyNames.map((name) => (
                <Badge key={name} variant="secondary" className="gap-1 pr-1">
                  {name}
                  <button onClick={() => removeParty(name)} className="ml-1 rounded-full p-0.5 hover:bg-foreground/10"><X className="h-3 w-3" /></button>
                </Badge>
              ))}
            </div>
          )}
          <Button onClick={handleCheck} disabled={partyNames.length === 0 || loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4" />}
            {loading ? "Checking..." : "Run Conflict Check"}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Result</CardTitle>
              <Badge variant={result.status === "no_conflict" ? "success" : result.status === "potential_conflict" ? "warning" : "destructive"} className="capitalize">
                {result.status === "no_conflict" ? <CheckCircle2 className="mr-1 h-3 w-3" /> : <AlertTriangle className="mr-1 h-3 w-3" />}
                {result.status.replace(/_/g, " ")}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {result.conflict_count === 0 ? (
              <div className="flex items-center gap-2 rounded-md bg-emerald-50 p-3 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
                <CheckCircle2 className="h-4 w-4" />
                <p className="text-sm">No conflicts found. Clear to proceed.</p>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">{result.conflict_count} conflict(s) found</p>
                {result.conflicts_found?.map((c: any, i: number) => (
                  <div key={i} className="rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" />
                      <span className="text-sm font-medium text-red-800 dark:text-red-200">{c.party_name}</span>
                      <Badge variant="outline" className="text-[10px]">{c.role}</Badge>
                      {c.is_adverse && <Badge variant="destructive" className="text-[10px]">Adverse</Badge>}
                    </div>
                    <p className="mt-1 text-sm text-red-700 dark:text-red-300">{c.description}</p>
                    <p className="mt-1 text-xs text-red-600/70 dark:text-red-400/70">Matter: {c.matter_title} ({c.matter_status})</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
