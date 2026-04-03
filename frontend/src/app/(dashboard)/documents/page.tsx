"use client";

import { useCallback, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { documents } from "@/lib/api/endpoints";
import { Upload, FileText, Search, Loader2, Clock, CheckCircle2, XCircle, MoreVertical } from "lucide-react";
import { toast } from "sonner";
import type { Document, DocumentType, ProcessingStatus } from "@/lib/types";
import { formatDistanceToNow } from "date-fns";

const STATUS_ICON: Record<ProcessingStatus, React.ReactNode> = {
  pending: <Clock className="h-3.5 w-3.5 text-muted-foreground" />,
  parsing: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  chunking: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  embedding: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  indexing: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  completed: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />,
  failed: <XCircle className="h-3.5 w-3.5 text-red-500" />,
};

function UploadDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState<DocumentType>("contract");
  const [jurisdiction, setJurisdiction] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("No file selected");
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", title || file.name);
      formData.append("document_type", docType);
      if (jurisdiction) formData.append("jurisdiction", jurisdiction);
      return documents.upload(formData);
    },
    onSuccess: () => {
      toast.success("Document uploaded — processing started");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setOpen(false);
      setTitle(""); setFile(null);
    },
    onError: (err: any) => toast.error(err.detail || "Upload failed"),
  });

  const onDrop = useCallback((files: File[]) => {
    if (files[0]) { setFile(files[0]); if (!title) setTitle(files[0].name.replace(/\.[^.]+$/, "")); }
  }, [title]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, maxFiles: 1, accept: { "application/pdf": [], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [], "text/plain": [] } });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Upload className="mr-2 h-4 w-4" />Upload Document</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Upload Document</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div {...getRootProps()} className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors ${isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"}`}>
            <input {...getInputProps()} />
            <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
            {file ? <p className="text-sm font-medium">{file.name}</p> : <p className="text-sm text-muted-foreground">Drop a file here, or click to select</p>}
            <p className="mt-1 text-xs text-muted-foreground">PDF, DOCX, or TXT — max 50MB</p>
          </div>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Document title" />
          <Select value={docType} onValueChange={(v) => setDocType(v as DocumentType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {["contract", "policy", "memo", "pleading", "nda", "employment_agreement", "board_resolution", "compliance_doc", "other"].map((t) => (
                <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={jurisdiction} onValueChange={setJurisdiction}>
            <SelectTrigger><SelectValue placeholder="Jurisdiction (optional)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="">None</SelectItem>
              <SelectItem value="NG">Nigeria</SelectItem>
              <SelectItem value="GB">United Kingdom</SelectItem>
              <SelectItem value="US">United States</SelectItem>
              <SelectItem value="EU">European Union</SelectItem>
            </SelectContent>
          </Select>
          <Button className="w-full" disabled={!file || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>
            {uploadMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {uploadMutation.isPending ? "Uploading..." : "Upload & Process"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function DocumentsPage() {
  const [search, setSearch] = useState("");
  const { data: docs, isLoading } = useQuery({ queryKey: ["documents"], queryFn: () => documents.list() });

  const filtered = docs?.filter((d) => d.title.toLowerCase().includes(search.toLowerCase()) || d.file_name.toLowerCase().includes(search.toLowerCase())) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search documents..." className="pl-9" />
        </div>
        <UploadDialog />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">No documents yet. Upload your first document to get started.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((doc) => (
            <Link key={doc.id} href={`/documents/${doc.id}`} className="block">
              <Card className="transition-colors hover:bg-secondary/30">
                <CardContent className="flex items-center gap-4 p-4">
                  <FileText className="h-8 w-8 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{doc.title}</p>
                    <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{doc.file_name}</span>
                      <span>{(doc.file_size / 1024).toFixed(0)} KB</span>
                      {doc.jurisdiction && <span>{doc.jurisdiction}</span>}
                      <span>{formatDistanceToNow(new Date(doc.created_at), { addSuffix: true })}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="capitalize text-[10px]">{doc.document_type.replace(/_/g, " ")}</Badge>
                    <div className="flex items-center gap-1" title={doc.processing_status}>
                      {STATUS_ICON[doc.processing_status]}
                    </div>
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
