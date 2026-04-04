"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { tasks } from "@/lib/api/endpoints";
import { Plus, CheckSquare, Loader2, Circle, CheckCircle2, Clock, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Circle className="h-4 w-4 text-muted-foreground" />,
  in_progress: <Clock className="h-4 w-4 text-blue-500" />,
  completed: <CheckCircle2 className="h-4 w-4 text-emerald-500" />,
  blocked: <AlertTriangle className="h-4 w-4 text-red-500" />,
};

const PRIORITY_LABELS: Record<number, { label: string; variant: "destructive" | "warning" | "secondary" | "outline" }> = {
  1: { label: "Critical", variant: "destructive" },
  2: { label: "High", variant: "warning" },
  3: { label: "Medium", variant: "secondary" },
  4: { label: "Low", variant: "outline" },
};

function CreateTaskDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", priority: 3, due_date: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => tasks.create({ ...form, due_date: form.due_date ? new Date(form.due_date).toISOString() : undefined }),
    onSuccess: () => { toast.success("Task created"); queryClient.invalidateQueries({ queryKey: ["tasks"] }); setOpen(false); setForm({ title: "", description: "", priority: 3, due_date: "" }); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Task</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Task</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.title} onChange={update("title")} placeholder="Task title" />
          <Textarea value={form.description} onChange={update("description")} placeholder="Description (optional)" />
          <div className="grid grid-cols-2 gap-3">
            <Select value={String(form.priority)} onValueChange={(v) => setForm((p) => ({ ...p, priority: Number(v) }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Critical</SelectItem>
                <SelectItem value="2">High</SelectItem>
                <SelectItem value="3">Medium</SelectItem>
                <SelectItem value="4">Low</SelectItem>
              </SelectContent>
            </Select>
            <Input type="date" value={form.due_date} onChange={update("due_date")} />
          </div>
          <Button className="w-full" disabled={!form.title || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Create Task"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function TasksPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const { data: taskList, isLoading } = useQuery({ queryKey: ["tasks", statusFilter], queryFn: () => tasks.list(statusFilter ? { status: statusFilter } : undefined) });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => tasks.update(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="blocked">Blocked</SelectItem>
          </SelectContent>
        </Select>
        <CreateTaskDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !taskList?.length ? (
        <div className="flex flex-col items-center py-20"><CheckSquare className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No tasks</p></div>
      ) : (
        <div className="space-y-2">
          {taskList.map((task: any) => {
            const pri = PRIORITY_LABELS[task.priority] || PRIORITY_LABELS[3];
            return (
              <Card key={task.id} className="transition-colors hover:bg-secondary/30">
                <CardContent className="flex items-center gap-3 p-3">
                  <button
                    onClick={() => updateMutation.mutate({ id: task.id, status: task.status === "completed" ? "pending" : "completed" })}
                    className="shrink-0"
                  >
                    {STATUS_ICONS[task.status] || STATUS_ICONS.pending}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm font-medium ${task.status === "completed" ? "line-through text-muted-foreground" : ""}`}>{task.title}</p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      {task.due_date && <span>{new Date(task.due_date).toLocaleDateString()}</span>}
                      {task.matter_id && <span>Matter linked</span>}
                    </div>
                  </div>
                  <Badge variant={pri.variant} className="text-[10px]">{pri.label}</Badge>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
