"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { playbooks } from "@/lib/api/endpoints";
import { Plus, BookOpen, Loader2, ChevronDown, ChevronRight, Download, Globe, Shield } from "lucide-react";
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
      <DialogTrigger asChild><Button variant="outline"><Plus className="mr-2 h-4 w-4" />New Playbook</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Playbook</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.name} onChange={update("name")} placeholder="Playbook name" />
          <Textarea value={form.description} onChange={update("description")} placeholder="Description" />
          <Select value={form.document_type} onValueChange={(v) => setForm((p) => ({ ...p, document_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["nda", "service_agreement", "employment_agreement", "license", "dpa", "consulting", "other"].map((t) => (
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

function TemplateCard({ template }: { template: any }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => playbooks.useTemplate(template.id),
    onSuccess: () => {
      toast.success(`"${template.name}" added to your playbooks`);
      queryClient.invalidateQueries({ queryKey: ["playbooks"] });
    },
    onError: (err: any) => toast.error(err.detail || "Failed to add template"),
  });

  return (
    <Card className="transition-colors hover:bg-secondary/30">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 shrink-0 text-muted-foreground" />
              <p className="text-sm font-medium">{template.name}</p>
            </div>
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{template.description}</p>
            <div className="mt-2 flex items-center gap-2">
              <Badge variant="secondary" className="text-[10px]">{template.document_type?.replace(/_/g, " ")}</Badge>
              {template.jurisdiction && (
                <Badge variant="outline" className="text-[10px] gap-1">
                  <Globe className="h-2.5 w-2.5" />{template.jurisdiction}
                </Badge>
              )}
              <span className="text-[10px] text-muted-foreground">{template.clause_count} clauses</span>
            </div>
          </div>
          <Button size="sm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1 h-3.5 w-3.5" />}
            Use
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function PlaybooksPage() {
  const { data: myPlaybooks, isLoading } = useQuery({ queryKey: ["playbooks"], queryFn: () => playbooks.list() });
  const { data: templateList, isLoading: templatesLoading } = useQuery({ queryKey: ["playbook-templates"], queryFn: () => playbooks.templates() });
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Define standard clause positions for contract review</p>
        <CreatePlaybookDialog />
      </div>

      <Tabs defaultValue="my-playbooks">
        <TabsList>
          <TabsTrigger value="my-playbooks">My Playbooks ({myPlaybooks?.length || 0})</TabsTrigger>
          <TabsTrigger value="templates">Templates ({templateList?.length || 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="my-playbooks" className="space-y-3 pt-4">
          {isLoading ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : !myPlaybooks?.length ? (
            <div className="flex flex-col items-center py-16 text-center">
              <BookOpen className="mb-3 h-10 w-10 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">No playbooks yet</p>
              <p className="mt-1 text-xs text-muted-foreground">Create one from scratch or use a template from the Templates tab.</p>
            </div>
          ) : (
            myPlaybooks.map((pb) => (
              <Card key={pb.id}>
                <CardContent className="p-4">
                  <button onClick={() => setExpanded(expanded === pb.id ? null : pb.id)} className="flex w-full items-center gap-3 text-left">
                    {expanded === pb.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <div className="flex-1">
                      <p className="text-sm font-medium">{pb.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {pb.document_type.replace(/_/g, " ")}
                        {pb.jurisdiction && ` \u00b7 ${pb.jurisdiction}`}
                        {` \u00b7 ${pb.clauses?.length || 0} clauses`}
                      </p>
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
                          {c.negotiation_notes && (
                            <p className="mt-1 text-[10px] text-muted-foreground italic">Tip: {c.negotiation_notes.slice(0, 120)}...</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        <TabsContent value="templates" className="space-y-3 pt-4">
          {templatesLoading ? (
            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : !templateList?.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">No templates available</p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Pre-built playbooks with real clause language. Click &quot;Use&quot; to add to your library, then customize.
              </p>
              {templateList.map((tpl: any) => (
                <TemplateCard key={tpl.id} template={tpl} />
              ))}
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
