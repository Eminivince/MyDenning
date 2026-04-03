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
import { Calendar, Plus, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

export default function MatterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: matter, isLoading } = useQuery({ queryKey: ["matter", id], queryFn: () => matters.get(id) });
  const { data: deadlines } = useQuery({ queryKey: ["matter-deadlines", id], queryFn: () => matters.deadlines(id) });
  const { data: notes } = useQuery({ queryKey: ["matter-notes", id], queryFn: () => matters.notes(id) });

  const [noteContent, setNoteContent] = useState("");
  const noteMutation = useMutation({
    mutationFn: () => matters.createNote(id, { content: noteContent }),
    onSuccess: () => { setNoteContent(""); queryClient.invalidateQueries({ queryKey: ["matter-notes", id] }); toast.success("Note added"); },
  });

  const [dlTitle, setDlTitle] = useState("");
  const [dlDate, setDlDate] = useState("");
  const dlMutation = useMutation({
    mutationFn: () => matters.createDeadline(id, { title: dlTitle, due_date: new Date(dlDate).toISOString(), priority: 2 }),
    onSuccess: () => { setDlTitle(""); setDlDate(""); queryClient.invalidateQueries({ queryKey: ["matter-deadlines", id] }); toast.success("Deadline added"); },
  });

  if (isLoading) return <div className="space-y-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  if (!matter) return <p className="text-muted-foreground">Matter not found</p>;

  return (
    <div className="space-y-6">
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

      <Tabs defaultValue="deadlines">
        <TabsList>
          <TabsTrigger value="deadlines">Deadlines ({deadlines?.length || 0})</TabsTrigger>
          <TabsTrigger value="notes">Notes ({notes?.length || 0})</TabsTrigger>
        </TabsList>

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
                    <p className="mt-1 text-xs text-muted-foreground">{new Date(n.created_at).toLocaleDateString()}</p>
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
