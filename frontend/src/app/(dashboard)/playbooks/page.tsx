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
import { playbooks } from "@/lib/api/endpoints";
import { Plus, BookOpen, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";

function CreatePlaybookDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", document_type: "nda", jurisdiction: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => playbooks.create(form),
    onSuccess: () => { toast.success("Playbook created"); queryClient.invalidateQueries({ queryKey: ["playbooks"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Playbook</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Playbook</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.name} onChange={update("name")} placeholder="Playbook name" />
          <Textarea value={form.description} onChange={update("description")} placeholder="Description" />
          <Select value={form.document_type} onValueChange={(v) => setForm((p) => ({ ...p, document_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["nda","service_agreement","employment_agreement","license","partnership","joint_venture","supply","distribution","consulting","other"].map((t) => (
                <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input value={form.jurisdiction} onChange={update("jurisdiction")} placeholder="Jurisdiction (optional)" />
          <Button className="w-full" disabled={!form.name || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Create Playbook"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function PlaybooksPage() {
  const { data, isLoading } = useQuery({ queryKey: ["playbooks"], queryFn: () => playbooks.list() });
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Define standard clause positions for contract review</p>
        <CreatePlaybookDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !data?.length ? (
        <div className="flex flex-col items-center py-20"><BookOpen className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No playbooks yet</p></div>
      ) : (
        <div className="space-y-3">
          {data.map((pb) => (
            <Card key={pb.id}>
              <CardContent className="p-4">
                <button onClick={() => setExpanded(expanded === pb.id ? null : pb.id)} className="flex w-full items-center gap-3 text-left">
                  {expanded === pb.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <div className="flex-1">
                    <p className="text-sm font-medium">{pb.name}</p>
                    <p className="text-xs text-muted-foreground">{pb.document_type.replace(/_/g, " ")} {pb.jurisdiction && `\u00b7 ${pb.jurisdiction}`} \u00b7 {pb.clauses?.length || 0} clauses</p>
                  </div>
                  <Badge variant="secondary">v{pb.version}</Badge>
                </button>
                {expanded === pb.id && pb.clauses?.length > 0 && (
                  <div className="mt-3 space-y-2 border-t pt-3">
                    {pb.clauses.map((c) => (
                      <div key={c.id} className="rounded border p-2 text-sm">
                        <div className="flex items-center justify-between">
                          <span className="font-medium capitalize">{c.clause_name}</span>
                          <Badge variant="outline" className="text-[10px] capitalize">{c.position}</Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{c.standard_language}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
