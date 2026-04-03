"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { memory, legalSources } from "@/lib/api/endpoints";
import { useTheme } from "next-themes";
import { Save, Loader2, Sun, Moon, Monitor } from "lucide-react";
import { toast } from "sonner";

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
