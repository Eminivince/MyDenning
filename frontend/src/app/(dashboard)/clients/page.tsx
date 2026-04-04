"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { clientPortal } from "@/lib/api/endpoints";
import { UserPlus, Users, Loader2, Mail, Building2, Clock } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

function InviteClientDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", company_name: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => clientPortal.inviteClient(form),
    onSuccess: () => {
      toast.success("Client invited");
      queryClient.invalidateQueries({ queryKey: ["portal-clients"] });
      setOpen(false);
      setForm({ email: "", full_name: "", password: "", company_name: "" });
    },
    onError: (err: any) => toast.error(err.detail || "Failed to invite client"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><UserPlus className="mr-2 h-4 w-4" />Invite Client</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite Client to Portal</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input value={form.full_name} onChange={update("full_name")} placeholder="Full name" />
          <Input type="email" value={form.email} onChange={update("email")} placeholder="Email address" />
          <Input value={form.company_name} onChange={update("company_name")} placeholder="Company name (optional)" />
          <Input type="password" value={form.password} onChange={update("password")} placeholder="Set a password for them" />
          <p className="text-xs text-muted-foreground">
            The client will be able to view matters you grant them access to.
            They cannot see internal notes, analysis results, or privileged documents.
          </p>
          <Button className="w-full" disabled={!form.email || !form.full_name || !form.password || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Inviting..." : "Send Invitation"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ClientsPage() {
  const { data: clients, isLoading } = useQuery({
    queryKey: ["portal-clients"],
    queryFn: () => clientPortal.listClients(),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Give clients read-only access to their matters. They can view status, deadlines,
            and documents — but not internal notes, analysis, or privileged content.
          </p>
        </div>
        <InviteClientDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !clients?.length ? (
        <div className="flex flex-col items-center py-20 text-center">
          <Users className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">No client portal users yet</p>
          <p className="mt-1 text-xs text-muted-foreground">Invite a client to give them visibility into their matters.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {clients.map((client: any) => (
            <Card key={client.id}>
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
                  <Users className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{client.full_name}</p>
                  <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{client.email}</span>
                    {client.company_name && <span className="flex items-center gap-1"><Building2 className="h-3 w-3" />{client.company_name}</span>}
                    {client.last_login && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />Last login: {formatDistanceToNow(new Date(client.last_login), { addSuffix: true })}
                      </span>
                    )}
                  </div>
                </div>
                <Badge variant={client.is_active ? "success" : "secondary"} className="text-[10px]">
                  {client.is_active ? "Active" : "Inactive"}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
