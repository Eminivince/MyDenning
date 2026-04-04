"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { calendar } from "@/lib/api/endpoints";
import { Plus, Calendar as CalIcon, Loader2, MapPin, Clock } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";

const TYPE_COLORS: Record<string, string> = {
  hearing: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  filing: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  deadline: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  meeting: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  conference: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  deposition: "bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-400",
  other: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300",
};

function CreateEventDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", event_type: "meeting", start_time: "", end_time: "", location: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => calendar.create({
      ...form,
      start_time: new Date(form.start_time).toISOString(),
      end_time: form.end_time ? new Date(form.end_time).toISOString() : undefined,
    }),
    onSuccess: () => { toast.success("Event created"); queryClient.invalidateQueries({ queryKey: ["calendar"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Event</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Event</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.title} onChange={update("title")} placeholder="Event title" />
          <Select value={form.event_type} onValueChange={(v) => setForm((p) => ({ ...p, event_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["hearing", "conference", "deadline", "meeting", "filing", "deposition", "mediation", "arbitration", "other"].map((t) => (
                <SelectItem key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Start</label>
              <Input type="datetime-local" value={form.start_time} onChange={update("start_time")} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">End</label>
              <Input type="datetime-local" value={form.end_time} onChange={update("end_time")} />
            </div>
          </div>
          <Input value={form.location} onChange={update("location")} placeholder="Location (optional)" />
          <Button className="w-full" disabled={!form.title || !form.start_time || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Create Event"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function CalendarPage() {
  const { data: events, isLoading } = useQuery({ queryKey: ["calendar"], queryFn: () => calendar.list() });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Court dates, meetings, filings, and deadlines</p>
        <CreateEventDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !events?.length ? (
        <div className="flex flex-col items-center py-20"><CalIcon className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No events</p></div>
      ) : (
        <div className="space-y-2">
          {events.map((event: any) => (
            <Card key={event.id}>
              <CardContent className="flex items-center gap-4 p-3">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${TYPE_COLORS[event.event_type] || TYPE_COLORS.other}`}>
                  {format(new Date(event.start_time), "dd")}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{event.title}</p>
                  <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {format(new Date(event.start_time), "MMM dd, yyyy HH:mm")}
                      {event.end_time && ` — ${format(new Date(event.end_time), "HH:mm")}`}
                    </span>
                    {event.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{event.location}</span>}
                  </div>
                </div>
                <Badge className={`text-[10px] ${TYPE_COLORS[event.event_type] || ""}`}>{event.event_type}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
