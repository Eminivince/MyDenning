"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { audit } from "@/lib/api/endpoints";
import { Loader2, ClipboardList } from "lucide-react";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";

const ACTION_COLORS: Record<string, "default" | "info" | "warning" | "success" | "secondary"> = {
  upload: "info", create: "success", delete: "destructive" as any,
  ask_question: "info", review_document: "warning", generate_draft: "info",
  external_legal_search: "secondary", conflict_check: "warning",
  assert_privilege: "warning", waive_privilege: "destructive" as any,
};

export default function AuditPage() {
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["audit", actionFilter, resourceFilter],
    queryFn: () => audit.logs({ action: actionFilter || undefined, resource_type: resourceFilter || undefined, page_size: 100 }),
  });

  const logs = data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex gap-3">
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Filter by action" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All actions</SelectItem>
            <SelectItem value="upload">Upload</SelectItem>
            <SelectItem value="create">Create</SelectItem>
            <SelectItem value="delete">Delete</SelectItem>
            <SelectItem value="ask_question">Ask Question</SelectItem>
            <SelectItem value="review_document">Review</SelectItem>
            <SelectItem value="generate_draft">Draft</SelectItem>
            <SelectItem value="external_legal_search">Legal Search</SelectItem>
            <SelectItem value="conflict_check">Conflict Check</SelectItem>
          </SelectContent>
        </Select>
        <Select value={resourceFilter} onValueChange={setResourceFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Filter by resource" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All resources</SelectItem>
            <SelectItem value="document">Documents</SelectItem>
            <SelectItem value="matter">Matters</SelectItem>
            <SelectItem value="analysis">Analysis</SelectItem>
            <SelectItem value="legal_source">Legal Sources</SelectItem>
            <SelectItem value="privilege_tag">Privilege</SelectItem>
            <SelectItem value="conflict_check">Conflicts</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : logs.length === 0 ? (
        <div className="flex flex-col items-center py-20"><ClipboardList className="mb-3 h-10 w-10 text-muted-foreground/50" /><p className="text-sm text-muted-foreground">No audit logs found</p></div>
      ) : (
        <div className="space-y-2">
          {logs.map((log: any) => (
            <Card key={log.id}>
              <CardContent className="flex items-center gap-4 p-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{log.description || `${log.action} on ${log.resource_type}`}</p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}</span>
                    {log.model_used && <span>Model: {log.model_used}</span>}
                    {log.confidence_score != null && <span>Confidence: {Math.round(log.confidence_score * 100)}%</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={ACTION_COLORS[log.action] || "secondary"} className="text-[10px]">{log.action.replace(/_/g, " ")}</Badge>
                  <Badge variant="outline" className="text-[10px]">{log.resource_type}</Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
