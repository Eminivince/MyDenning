"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { matters } from "@/lib/api/endpoints";
import { Plus, Briefcase, Search, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import type { MatterType } from "@/lib/types";

const STATUS_COLORS: Record<string, "default" | "secondary" | "success" | "warning" | "destructive"> = {
  active: "success", on_hold: "warning", closed: "secondary", archived: "secondary",
};

function CreateMatterDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", matter_type: "advisory" as MatterType, description: "", jurisdiction: "", counterparty: "", client_name: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => matters.create(form),
    onSuccess: () => { toast.success("Matter created"); queryClient.invalidateQueries({ queryKey: ["matters"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Matter</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Matter</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.title} onChange={update("title")} placeholder="Matter title" />
          <Select value={form.matter_type} onValueChange={(v) => setForm((p) => ({ ...p, matter_type: v as MatterType }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["litigation","transaction","advisory","regulatory","corporate","employment","ip","real_estate","other"].map((t) => (
                <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Textarea value={form.description} onChange={update("description")} placeholder="Description (optional)" />
          <div className="grid grid-cols-2 gap-3">
            <Input value={form.client_name} onChange={update("client_name")} placeholder="Client name" />
            <Input value={form.counterparty} onChange={update("counterparty")} placeholder="Counterparty" />
          </div>
          <Input value={form.jurisdiction} onChange={update("jurisdiction")} placeholder="Jurisdiction (e.g. NG, GB, US)" />
          <Button className="w-full" disabled={!form.title || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Create Matter"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function MattersPage() {
  const [search, setSearch] = useState("");
  const { data: matterList, isLoading } = useQuery({ queryKey: ["matters"], queryFn: () => matters.list() });
  const filtered = matterList?.filter((m) => m.title.toLowerCase().includes(search.toLowerCase())) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search matters..." className="pl-9" />
        </div>
        <CreateMatterDialog />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Briefcase className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">No matters yet. Create your first matter.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((m) => (
            <Link key={m.id} href={`/matters/${m.id}`} className="block">
              <Card className="transition-colors hover:bg-secondary/30">
                <CardContent className="flex items-center gap-4 p-4">
                  <Briefcase className="h-8 w-8 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium">{m.title}</p>
                      {m.reference_number && <span className="text-xs text-muted-foreground">{m.reference_number}</span>}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="capitalize">{m.matter_type.replace(/_/g, " ")}</span>
                      {m.client_name && <span>{m.client_name}</span>}
                      {m.counterparty && <span>vs {m.counterparty}</span>}
                      {m.jurisdiction && <span>{m.jurisdiction}</span>}
                      <span>{formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</span>
                    </div>
                  </div>
                  <Badge variant={STATUS_COLORS[m.status] || "secondary"} className="capitalize">{m.status.replace(/_/g, " ")}</Badge>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
