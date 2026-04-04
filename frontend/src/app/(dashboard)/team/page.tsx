"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { teams } from "@/lib/api/endpoints";
import { Plus, UsersRound, Loader2 } from "lucide-react";
import { toast } from "sonner";

function CreateTeamDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", practice_area: "" });
  const update = (f: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((p) => ({ ...p, [f]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () => teams.create(form),
    onSuccess: () => { toast.success("Team created"); queryClient.invalidateQueries({ queryKey: ["teams"] }); setOpen(false); },
    onError: (err: any) => toast.error(err.detail || "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 h-4 w-4" />New Team</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Team / Department</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input value={form.name} onChange={update("name")} placeholder="Team name (e.g. Litigation)" />
          <Input value={form.practice_area} onChange={update("practice_area")} placeholder="Practice area (e.g. corporate, IP, employment)" />
          <Button className="w-full" disabled={!form.name || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Creating..." : "Create Team"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function TeamPage() {
  const { data: teamList, isLoading } = useQuery({ queryKey: ["teams"], queryFn: () => teams.list() });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Departments and practice groups</p>
        <CreateTeamDialog />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : !teamList?.length ? (
        <div className="flex flex-col items-center py-20"><UsersRound className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No teams yet</p></div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {teamList.map((team: any) => (
            <Card key={team.id}>
              <CardContent className="p-4">
                <p className="text-sm font-semibold">{team.name}</p>
                {team.practice_area && <p className="mt-1 text-xs text-muted-foreground capitalize">{team.practice_area}</p>}
                {team.description && <p className="mt-1 text-xs text-muted-foreground">{team.description}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
