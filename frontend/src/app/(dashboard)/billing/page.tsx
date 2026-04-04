"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { billing } from "@/lib/api/endpoints";
import { Plus, Receipt, Clock, Loader2, DollarSign } from "lucide-react";
import { toast } from "sonner";

const STATUS_COLORS: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  draft: "secondary", sent: "warning", paid: "success", overdue: "destructive", cancelled: "secondary",
};

function LogTimeDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ date: "", hours: "", description: "", rate: "", is_billable: true });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => billing.logTime({
      date: new Date(form.date).toISOString(),
      hours: parseFloat(form.hours),
      description: form.description,
      rate: form.rate ? parseFloat(form.rate) : undefined,
      is_billable: form.is_billable,
    }),
    onSuccess: () => { toast.success("Time logged"); queryClient.invalidateQueries({ queryKey: ["time-entries"] }); queryClient.invalidateQueries({ queryKey: ["billing-summary"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />Log Time</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Log Time Entry</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input type="date" value={form.date} onChange={update("date")} />
            <Input type="number" step="0.25" value={form.hours} onChange={update("hours")} placeholder="Hours (e.g. 1.5)" />
          </div>
          <Textarea value={form.description} onChange={update("description")} placeholder="What did you work on?" />
          <Input type="number" value={form.rate} onChange={update("rate")} placeholder="Hourly rate (optional)" />
          <Button className="w-full" disabled={!form.date || !form.hours || !form.description || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Logging..." : "Log Time"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function BillingPage() {
  const { data: summary } = useQuery({ queryKey: ["billing-summary"], queryFn: () => billing.summary() });
  const { data: entries, isLoading: entriesLoading } = useQuery({ queryKey: ["time-entries"], queryFn: () => billing.timeEntries({ page_size: 50 }) });
  const { data: invoices, isLoading: invoicesLoading } = useQuery({ queryKey: ["invoices"], queryFn: () => billing.invoices() });

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-900/30">
                  <Clock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{summary.this_month?.billable_hours || 0}h</p>
                  <p className="text-xs text-muted-foreground">Billable hours this month</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-900/30">
                  <DollarSign className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{(summary.outstanding?.amount || 0).toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Outstanding ({summary.outstanding?.invoice_count || 0} invoices)</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
                  <Receipt className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{(summary.collected_this_month || 0).toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Collected this month</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="flex justify-end">
        <LogTimeDialog />
      </div>

      <Tabs defaultValue="time">
        <TabsList>
          <TabsTrigger value="time">Time Entries</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
        </TabsList>

        <TabsContent value="time" className="space-y-2 pt-4">
          {entriesLoading ? <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin" /></div> : !entries?.entries?.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No time entries yet</p>
          ) : (
            entries.entries.map((e: any) => (
              <Card key={e.id}>
                <CardContent className="flex items-center justify-between p-3">
                  <div>
                    <p className="text-sm">{e.description}</p>
                    <p className="text-xs text-muted-foreground">{new Date(e.date).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="font-mono font-bold">{e.hours}h</span>
                    {e.amount != null && <span className="text-muted-foreground">{e.amount.toLocaleString()}</span>}
                    <Badge variant={e.is_billable ? "success" : "secondary"} className="text-[10px]">{e.is_billable ? "Billable" : "Non-billable"}</Badge>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        <TabsContent value="invoices" className="space-y-2 pt-4">
          {invoicesLoading ? <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin" /></div> : !invoices?.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No invoices yet</p>
          ) : (
            invoices.map((inv: any) => (
              <Card key={inv.id}>
                <CardContent className="flex items-center justify-between p-3">
                  <div>
                    <p className="text-sm font-medium">{inv.invoice_number}</p>
                    <p className="text-xs text-muted-foreground">Due: {new Date(inv.due_date).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-bold">{inv.currency} {inv.total.toLocaleString()}</span>
                    <Badge variant={STATUS_COLORS[inv.status] || "secondary"} className="text-[10px] capitalize">{inv.status}</Badge>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
