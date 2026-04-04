"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { matters } from "@/lib/api/endpoints";
import {
  Calendar, Plus, Loader2, AlertTriangle, FileText, MessageSquare,
  Zap, Brain, ClipboardList, Clock,
} from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

const EVENT_ICONS: Record<string, React.ReactNode> = {
  note: <MessageSquare className="h-3.5 w-3.5" />,
  deadline: <Calendar className="h-3.5 w-3.5" />,
  document: <FileText className="h-3.5 w-3.5" />,
  analysis: <Zap className="h-3.5 w-3.5" />,
  memory: <Brain className="h-3.5 w-3.5" />,
  audit: <ClipboardList className="h-3.5 w-3.5" />,
};

const EVENT_COLORS: Record<string, string> = {
  note: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  deadline: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  document: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  analysis: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  memory: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400",
  audit: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
};

function StatCard({ label, value, alert }: { label: string; value: number; alert?: boolean }) {
  return (
    <div className="rounded-lg border bg-card p-3 text-center">
      <div className={`text-2xl font-bold ${alert ? "text-red-500" : ""}`}>{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

export default function MatterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: matter, isLoading } = useQuery({ queryKey: ["matter", id], queryFn: () => matters.get(id) });
  const { data: deadlines } = useQuery({ queryKey: ["matter-deadlines", id], queryFn: () => matters.deadlines(id) });
  const { data: notes } = useQuery({ queryKey: ["matter-notes", id], queryFn: () => matters.notes(id) });
  const { data: activity } = useQuery({ queryKey: ["matter-activity", id], queryFn: () => matters.activity(id) });
  const { data: stats } = useQuery({ queryKey: ["matter-stats", id], queryFn: () => matters.stats(id) });

  const [noteContent, setNoteContent] = useState("");
  const noteMutation = useMutation({
    mutationFn: () => matters.createNote(id, { content: noteContent }),
    onSuccess: () => {
      setNoteContent("");
      queryClient.invalidateQueries({ queryKey: ["matter-notes", id] });
      queryClient.invalidateQueries({ queryKey: ["matter-activity", id] });
      queryClient.invalidateQueries({ queryKey: ["matter-stats", id] });
      toast.success("Note added");
    },
  });

  const [dlTitle, setDlTitle] = useState("");
  const [dlDate, setDlDate] = useState("");
  const dlMutation = useMutation({
    mutationFn: () => matters.createDeadline(id, { title: dlTitle, due_date: new Date(dlDate).toISOString(), priority: 2 }),
    onSuccess: () => {
      setDlTitle(""); setDlDate("");
      queryClient.invalidateQueries({ queryKey: ["matter-deadlines", id] });
      queryClient.invalidateQueries({ queryKey: ["matter-activity", id] });
      queryClient.invalidateQueries({ queryKey: ["matter-stats", id] });
      toast.success("Deadline added");
    },
  });

  if (isLoading) return <div className="space-y-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  if (!matter) return <p className="text-muted-foreground">Matter not found</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">{matter.title}</h2>
          <Badge variant="secondary" className="capitalize">{matter.status.replace(/_/g, " ")}</Badge>
          <Badge variant="outline" className="capitalize">{matter.matter_type.replace(/_/g, " ")}</Badge>
        </div>
        {matter.reference_number && <p className="mt-1 text-sm text-muted-foreground">{matter.reference_number}</p>}
        {matter.description && <p className="mt-2 text-sm">{matter.description}</p>}
        <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
          {matter.client_name && <span>Client: {matter.client_name}</span>}
          {matter.counterparty && <span>Counterparty: {matter.counterparty}</span>}
          {matter.jurisdiction && <span>Jurisdiction: {matter.jurisdiction}</span>}
        </div>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-5 gap-3">
          <StatCard label="Documents" value={stats.documents} />
          <StatCard label="Deadlines" value={stats.deadlines} />
          <StatCard label="Overdue" value={stats.overdue_deadlines} alert={stats.overdue_deadlines > 0} />
          <StatCard label="Notes" value={stats.notes} />
          <StatCard label="Analyses" value={stats.analyses} />
        </div>
      )}

      <Tabs defaultValue="activity">
        <TabsList>
          <TabsTrigger value="activity">Activity ({activity?.length || 0})</TabsTrigger>
          <TabsTrigger value="deadlines">Deadlines ({deadlines?.length || 0})</TabsTrigger>
          <TabsTrigger value="notes">Notes ({notes?.length || 0})</TabsTrigger>
        </TabsList>

        {/* Activity Feed */}
        <TabsContent value="activity" className="pt-4">
          {!activity?.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No activity yet</p>
          ) : (
            <div className="relative space-y-0">
              {/* Timeline line */}
              <div className="absolute left-[15px] top-2 bottom-2 w-px bg-border" />

              {activity.map((event: any, i: number) => (
                <div key={`${event.type}-${event.resource_id}-${i}`} className="relative flex gap-3 pb-4">
                  {/* Icon dot */}
                  <div className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${EVENT_COLORS[event.type] || EVENT_COLORS.audit}`}>
                    {EVENT_ICONS[event.type] || <ClipboardList className="h-3.5 w-3.5" />}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1 pt-0.5">
                    <p className="text-sm font-medium">{event.title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{event.description}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <Clock className="h-3 w-3 text-muted-foreground" />
                      <span className="text-[10px] text-muted-foreground">
                        {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                      </span>
                      {event.metadata?.risk_level && (
                        <Badge variant={event.metadata.risk_level === "high" || event.metadata.risk_level === "critical" ? "destructive" : "secondary"} className="text-[9px]">
                          {event.metadata.risk_level}
                        </Badge>
                      )}
                      {event.metadata?.confidence != null && (
                        <span className="text-[10px] text-muted-foreground">
                          {Math.round(event.metadata.confidence * 100)}% confidence
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Deadlines */}
        <TabsContent value="deadlines" className="space-y-4 pt-4">
          <div className="flex gap-2">
            <Input value={dlTitle} onChange={(e) => setDlTitle(e.target.value)} placeholder="Deadline title" className="flex-1" />
            <Input type="date" value={dlDate} onChange={(e) => setDlDate(e.target.value)} className="w-40" />
            <Button disabled={!dlTitle || !dlDate || dlMutation.isPending} onClick={() => dlMutation.mutate()}>
              <Plus className="mr-1 h-4 w-4" />Add
            </Button>
          </div>
          {deadlines?.length ? (
            <div className="space-y-2">
              {deadlines.map((dl: any) => (
                <Card key={dl.id}>
                  <CardContent className="flex items-center justify-between p-3">
                    <div className="flex items-center gap-3">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium">{dl.title}</p>
                        <p className="text-xs text-muted-foreground">{new Date(dl.due_date).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {dl.is_court_deadline && <Badge variant="destructive" className="text-[10px]">Court</Badge>}
                      <Badge variant={dl.status === "overdue" ? "destructive" : dl.status === "completed" ? "success" : "secondary"} className="capitalize text-[10px]">{dl.status}</Badge>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : <p className="py-8 text-center text-sm text-muted-foreground">No deadlines</p>}
        </TabsContent>

        {/* Notes */}
        <TabsContent value="notes" className="space-y-4 pt-4">
          <div className="flex gap-2">
            <Textarea value={noteContent} onChange={(e) => setNoteContent(e.target.value)} placeholder="Add a note..." className="flex-1" />
            <Button disabled={!noteContent || noteMutation.isPending} onClick={() => noteMutation.mutate()}>Add</Button>
          </div>
          {notes?.length ? (
            <div className="space-y-2">
              {notes.map((n: any) => (
                <Card key={n.id}>
                  <CardContent className="p-3">
                    <p className="text-sm">{n.content}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : <p className="py-8 text-center text-sm text-muted-foreground">No notes</p>}
        </TabsContent>
      </Tabs>
    </div>
  );
}
