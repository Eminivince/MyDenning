"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { memory, legalSources, emailIntake } from "@/lib/api/endpoints";
import { useTheme } from "next-themes";
import { Save, Loader2, Sun, Moon, Monitor, Globe, Download, CheckCircle2, Mail, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";

function StarterPacksSection() {
  const { data: packs, isLoading } = useQuery({ queryKey: ["starter-packs"], queryFn: () => legalSources.starterPacks() });
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState<string | null>(null);
  const [imported, setImported] = useState<Set<string>>(new Set());

  async function handleImport(packId: string) {
    setImporting(packId);
    try {
      const result = await legalSources.importStarterPack(packId);
      setImported((prev) => new Set(prev).add(packId));
      toast.success(`Imported ${result.imported_count} sources from ${result.pack_name}. ${result.skipped_count} skipped, ${result.failed_count} failed.`);
    } catch (err: any) {
      toast.error(err.detail || "Import failed");
    } finally {
      setImporting(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Jurisdiction Starter Packs</CardTitle>
        <CardDescription>One-click import of key statutes, landmark cases, and regulations per jurisdiction</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : !packs?.length ? (
          <p className="text-sm text-muted-foreground">No starter packs available</p>
        ) : (
          <div className="space-y-3">
            {packs.map((pack: any) => (
              <div key={pack.id} className="flex items-center justify-between rounded-md border p-3">
                <div className="flex items-center gap-3">
                  <Globe className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{pack.name}</p>
                    <p className="text-xs text-muted-foreground">{pack.description?.slice(0, 80)}...</p>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">{pack.jurisdiction}</Badge>
                      <span className="text-[10px] text-muted-foreground">{pack.source_count} sources</span>
                    </div>
                  </div>
                </div>
                {imported.has(pack.id) ? (
                  <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" />Imported
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleImport(pack.id)}
                    disabled={importing === pack.id}
                  >
                    {importing === pack.id ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1 h-3.5 w-3.5" />}
                    {importing === pack.id ? "Importing..." : "Import"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EmailIntakeSection() {
  const queryClient = useQueryClient();
  const { data: config, isLoading } = useQuery({ queryKey: ["email-intake-config"], queryFn: () => emailIntake.getConfig() });
  const [copied, setCopied] = useState(false);

  const setupMutation = useMutation({
    mutationFn: () => emailIntake.configure({ default_document_type: "contract" }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["email-intake-config"] }); toast.success("Email intake configured"); },
    onError: (err: any) => toast.error(err.detail || "Setup failed"),
  });

  function handleCopy(text: string) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Email Intake</CardTitle>
        <CardDescription>Forward emails with document attachments to auto-ingest into MyDenning</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : config?.configured ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-md border bg-secondary/30 p-3">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <code className="flex-1 text-sm font-mono">{config.intake_email}</code>
              <Button variant="ghost" size="sm" onClick={() => handleCopy(config.intake_email)}>
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Forward any email with PDF, DOCX, or TXT attachments to this address. Documents will be
              automatically uploaded and processed.
            </p>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>Type: {config.default_document_type}</span>
              {config.default_jurisdiction && <span>Jurisdiction: {config.default_jurisdiction}</span>}
              <span>Auto-review: {config.auto_review ? "On" : "Off"}</span>
              <Badge variant={config.is_active ? "success" : "secondary"} className="text-[10px]">{config.is_active ? "Active" : "Inactive"}</Badge>
            </div>
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-sm text-muted-foreground mb-3">Not configured yet. Set up email intake to auto-ingest documents from your inbox.</p>
            <Button onClick={() => setupMutation.mutate()} disabled={setupMutation.isPending}>
              {setupMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
              Set Up Email Intake
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const { data: prefs } = useQuery({ queryKey: ["preferences"], queryFn: () => memory.preferences() });
  const { data: adapters } = useQuery({ queryKey: ["adapters"], queryFn: () => legalSources.adapters() });

  const [jurisdiction, setJurisdiction] = useState("");
  const [governingLaw, setGoverningLaw] = useState("");

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (jurisdiction) await memory.setPreference({ category: "legal", key: "default_jurisdiction", value: { value: jurisdiction }, description: "Default jurisdiction for analysis" });
      if (governingLaw) await memory.setPreference({ category: "legal", key: "default_governing_law", value: { value: governingLaw }, description: "Default governing law" });
    },
    onSuccess: () => { toast.success("Preferences saved"); queryClient.invalidateQueries({ queryKey: ["preferences"] }); },
    onError: (err: any) => toast.error(err.detail || "Failed to save"),
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Appearance */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appearance</CardTitle>
          <CardDescription>Choose your preferred theme</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {[
              { value: "light", icon: Sun, label: "Light" },
              { value: "dark", icon: Moon, label: "Dark" },
              { value: "system", icon: Monitor, label: "System" },
            ].map((t) => (
              <Button key={t.value} variant={theme === t.value ? "default" : "outline"} size="sm" onClick={() => setTheme(t.value)}>
                <t.icon className="mr-2 h-4 w-4" />{t.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Legal Defaults */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Legal Defaults</CardTitle>
          <CardDescription>Set default jurisdiction and governing law for your organization</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Default Jurisdiction</label>
            <Select value={jurisdiction} onValueChange={setJurisdiction}>
              <SelectTrigger><SelectValue placeholder="Select jurisdiction" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="NG">Nigeria</SelectItem>
                <SelectItem value="GB">United Kingdom</SelectItem>
                <SelectItem value="US">United States</SelectItem>
                <SelectItem value="EU">European Union</SelectItem>
                <SelectItem value="KE">Kenya</SelectItem>
                <SelectItem value="ZA">South Africa</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Default Governing Law</label>
            <Input value={governingLaw} onChange={(e) => setGoverningLaw(e.target.value)} placeholder="e.g. Laws of the Federal Republic of Nigeria" />
          </div>
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save Preferences
          </Button>
        </CardContent>
      </Card>

      {/* Active Preferences */}
      {prefs && prefs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Active Preferences</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {prefs.map((p: any) => (
                <div key={p.id} className="flex items-center justify-between rounded-md border p-2 text-sm">
                  <div>
                    <span className="font-medium">{p.key.replace(/_/g, " ")}</span>
                    <span className="ml-2 text-muted-foreground">{JSON.stringify(p.value?.value || p.value)}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{p.category}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Email Intake */}
      <EmailIntakeSection />

      {/* Starter Packs */}
      <StarterPacksSection />

      {/* Legal Source Adapters */}
      {adapters && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Legal Source Adapters</CardTitle>
            <CardDescription>Connected legal databases</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {adapters.adapters?.map((a: any) => (
                <div key={a.name} className="flex items-center justify-between rounded-md border p-2 text-sm">
                  <div>
                    <p className="font-medium">{a.display_name}</p>
                    <p className="text-xs text-muted-foreground">{a.jurisdictions?.join(", ")}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    {a.content_types?.map((ct: string) => (
                      <span key={ct} className="rounded bg-secondary px-1.5 py-0.5 text-[10px]">{ct.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
