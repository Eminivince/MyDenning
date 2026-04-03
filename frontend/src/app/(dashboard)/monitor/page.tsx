"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { legalFeatures } from "@/lib/api/endpoints";
import { Bell, Plus, Loader2, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

function CreateMonitorDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", jurisdiction: "NG", source_type: "regulation", description: "", keywords: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => legalFeatures.createMonitor({ ...form, keywords: form.keywords ? form.keywords.split(",").map((k) => k.trim()) : undefined }),
    onSuccess: () => { toast.success("Monitor created"); queryClient.invalidateQueries({ queryKey: ["monitors"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Monitor</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Monitor Regulation</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.title} onChange={update("title")} placeholder="What to monitor (e.g. Nigeria Data Protection Regulation)" />
          <div className="grid grid-cols-2 gap-3">
            <Select value={form.jurisdiction} onValueChange={(v) => setForm((p) => ({ ...p, jurisdiction: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="NG">Nigeria</SelectItem><SelectItem value="GB">UK</SelectItem>
                <SelectItem value="US">US</SelectItem><SelectItem value="EU">EU</SelectItem>
                <SelectItem value="KE">Kenya</SelectItem><SelectItem value="ZA">South Africa</SelectItem>
              </SelectContent>
            </Select>
            <Select value={form.source_type} onValueChange={(v) => setForm((p) => ({ ...p, source_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="statute">Statute</SelectItem><SelectItem value="regulation">Regulation</SelectItem>
                <SelectItem value="case_law">Case Law</SelectItem><SelectItem value="guidance">Guidance</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Textarea value={form.description} onChange={update("description")} placeholder="Description (optional)" />
          <Input value={form.keywords} onChange={update("keywords")} placeholder="Keywords (comma separated)" />
          <Button className="w-full" disabled={!form.title || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Start Monitoring"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function MonitorPage() {
  const { data: monitors, isLoading: monitorsLoading } = useQuery({ queryKey: ["monitors"], queryFn: () => legalFeatures.regulatoryMonitors() });
  const { data: alerts, isLoading: alertsLoading } = useQuery({ queryKey: ["alerts"], queryFn: () => legalFeatures.regulatoryAlerts({ limit: 50 }) });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Track regulatory changes across jurisdictions</p>
        <CreateMonitorDialog />
      </div>

      <Tabs defaultValue="alerts">
        <TabsList>
          <TabsTrigger value="alerts">Alerts ({alerts?.length || 0})</TabsTrigger>
          <TabsTrigger value="monitors">Monitors ({monitors?.length || 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="alerts" className="space-y-3 pt-4">
          {alertsLoading ? <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin" /></div> : !alerts?.length ? (
            <div className="flex flex-col items-center py-16"><Bell className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No alerts yet</p></div>
          ) : (
            alerts.map((a) => (
              <Card key={a.id} className={a.is_read ? "opacity-60" : ""}>
                <CardContent className="flex items-start gap-3 p-4">
                  {a.risk_level === "critical" || a.risk_level === "high" ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" /> : <Bell className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{a.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{a.summary}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] capitalize">{a.alert_type.replace(/_/g, " ")}</Badge>
                      {a.risk_level && <Badge variant={a.risk_level === "high" || a.risk_level === "critical" ? "destructive" : "warning"} className="text-[10px]">{a.risk_level}</Badge>}
                      <span className="text-[10px] text-muted-foreground">{formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}</span>
                    </div>
                  </div>
                  {a.source_url && <a href={a.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline shrink-0">View source</a>}
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        <TabsContent value="monitors" className="space-y-3 pt-4">
          {monitorsLoading ? <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin" /></div> : !monitors?.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No monitors configured</p>
          ) : (
            monitors.map((m: any) => (
              <Card key={m.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm font-medium">{m.title}</p>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{m.jurisdiction}</span><span>{m.source_type}</span>
                      {m.last_checked_at && <span>Checked {formatDistanceToNow(new Date(m.last_checked_at), { addSuffix: true })}</span>}
                    </div>
                  </div>
                  <Badge variant={m.is_active ? "success" : "secondary"}>{m.is_active ? "Active" : "Paused"}</Badge>
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
