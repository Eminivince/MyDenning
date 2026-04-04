"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { clients } from "@/lib/api/endpoints";
import { Building2, Briefcase, Mail, Phone, Globe, MapPin } from "lucide-react";

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: client, isLoading } = useQuery({ queryKey: ["client", id], queryFn: () => clients.get(id) });

  if (isLoading) return <div className="space-y-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}</div>;
  if (!client) return <p className="text-muted-foreground">Client not found</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
          <Building2 className="h-6 w-6 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-xl font-semibold">{client.name}</h2>
          <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
            <Badge variant="outline" className="capitalize">{client.client_type}</Badge>
            <Badge variant={client.status === "active" ? "success" : "secondary"} className="capitalize">{client.status}</Badge>
            {client.industry && <span>{client.industry}</span>}
            {client.risk_rating && <span>Risk: {client.risk_rating}/5</span>}
          </div>
        </div>
      </div>

      {/* Contact info */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Contact Information</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {client.email && (
              <div className="flex items-center gap-2"><Mail className="h-3.5 w-3.5 text-muted-foreground" />{client.email}</div>
            )}
            {client.phone && (
              <div className="flex items-center gap-2"><Phone className="h-3.5 w-3.5 text-muted-foreground" />{client.phone}</div>
            )}
            {client.jurisdiction && (
              <div className="flex items-center gap-2"><Globe className="h-3.5 w-3.5 text-muted-foreground" />{client.jurisdiction}</div>
            )}
            {client.primary_contact_name && (
              <div className="text-muted-foreground">Primary contact: {client.primary_contact_name}</div>
            )}
            {!client.email && !client.phone && <p className="text-muted-foreground">No contact info</p>}
          </CardContent>
        </Card>
        {client.notes && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Notes</CardTitle></CardHeader>
            <CardContent><p className="text-sm text-muted-foreground">{client.notes}</p></CardContent>
          </Card>
        )}
      </div>

      {/* Matters */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Matters ({client.matters?.length || 0})</CardTitle>
        </CardHeader>
        <CardContent>
          {client.matters?.length ? (
            <div className="space-y-2">
              {client.matters.map((m: any) => (
                <Link key={m.id} href={`/matters/${m.id}`} className="block">
                  <div className="flex items-center justify-between rounded-md border p-3 text-sm transition-colors hover:bg-secondary/30">
                    <div className="flex items-center gap-2">
                      <Briefcase className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{m.title}</span>
                      {m.reference && <span className="text-xs text-muted-foreground">{m.reference}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] capitalize">{m.type?.replace(/_/g, " ")}</Badge>
                      <Badge variant={m.status === "active" ? "success" : "secondary"} className="text-[10px] capitalize">{m.status}</Badge>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-muted-foreground">No matters for this client</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
