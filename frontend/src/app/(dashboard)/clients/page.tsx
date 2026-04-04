"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { clients } from "@/lib/api/endpoints";
import { Plus, Building2, Search, Loader2, Briefcase } from "lucide-react";
import { toast } from "sonner";

function CreateClientDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", client_type: "company", email: "", phone: "", industry: "", jurisdiction: "", notes: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => clients.create(form),
    onSuccess: () => { toast.success("Client created"); queryClient.invalidateQueries({ queryKey: ["firm-clients"] }); setOpen(false); setForm({ name: "", client_type: "company", email: "", phone: "", industry: "", jurisdiction: "", notes: "" }); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Client</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add Client</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.name} onChange={update("name")} placeholder="Client name" />
          <Select value={form.client_type} onValueChange={(v) => setForm((p) => ({ ...p, client_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="company">Company</SelectItem>
              <SelectItem value="individual">Individual</SelectItem>
              <SelectItem value="government">Government</SelectItem>
              <SelectItem value="nonprofit">Non-profit</SelectItem>
              <SelectItem value="trust">Trust</SelectItem>
            </SelectContent>
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <Input value={form.email} onChange={update("email")} placeholder="Email" />
            <Input value={form.phone} onChange={update("phone")} placeholder="Phone" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input value={form.industry} onChange={update("industry")} placeholder="Industry" />
            <Input value={form.jurisdiction} onChange={update("jurisdiction")} placeholder="Jurisdiction" />
          </div>
          <Textarea value={form.notes} onChange={update("notes")} placeholder="Notes (optional)" />
          <Button className="w-full" disabled={!form.name || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Add Client"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ClientsPage() {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["firm-clients", search], queryFn: () => clients.list(search ? { q: search } : undefined) });
  const clientList = data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search clients..." className="pl-9" />
        </div>
        <CreateClientDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !clientList.length ? (
        <div className="flex flex-col items-center py-20"><Building2 className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No clients yet</p></div>
      ) : (
        <div className="space-y-2">
          {clientList.map((client: any) => (
            <Link key={client.id} href={`/clients/${client.id}`}>
            <Card className="transition-colors hover:bg-secondary/30">
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-secondary">
                  <Building2 className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{client.name}</p>
                  <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="capitalize">{client.client_type}</span>
                    {client.industry && <span>{client.industry}</span>}
                    {client.jurisdiction && <span>{client.jurisdiction}</span>}
                    {client.email && <span>{client.email}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {client.matter_count > 0 && (
                    <Badge variant="outline" className="gap-1 text-[10px]">
                      <Briefcase className="h-2.5 w-2.5" />{client.matter_count}
                    </Badge>
                  )}
                  <Badge variant={client.status === "active" ? "success" : "secondary"} className="text-[10px] capitalize">{client.status}</Badge>
                </div>
              </CardContent>
            </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
