import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, Code2, Lock, Zap } from "lucide-react";

const endpointGroups = [
  {
    name: "Authentication",
    endpoints: [
      { method: "POST", path: "/auth/register", description: "Create account and organization" },
      { method: "POST", path: "/auth/login", description: "Get access token" },
      { method: "POST", path: "/auth/refresh", description: "Refresh expired token" },
    ],
  },
  {
    name: "Analysis",
    endpoints: [
      { method: "POST", path: "/analysis/ask", description: "Ask a legal question with IRAC analysis" },
      { method: "POST", path: "/analysis/research", description: "Search legal authorities" },
      { method: "POST", path: "/analysis/review", description: "Extract clauses and flag risks" },
      { method: "POST", path: "/analysis/compare", description: "Compare against playbook or another doc" },
      { method: "POST", path: "/analysis/draft", description: "Generate legal work products" },
      { method: "POST", path: "/analysis/risk-matrix/{id}", description: "Generate risk assessment matrix" },
    ],
  },
  {
    name: "Documents",
    endpoints: [
      { method: "POST", path: "/documents", description: "Upload and process a document" },
      { method: "GET", path: "/documents", description: "List documents with filters" },
      { method: "GET", path: "/documents/{id}", description: "Get document details and metadata" },
      { method: "POST", path: "/documents/{id}/reprocess", description: "Re-run ingestion pipeline" },
    ],
  },
  {
    name: "Legal Sources",
    endpoints: [
      { method: "POST", path: "/legal-sources/search", description: "Search 11 external legal databases" },
      { method: "POST", path: "/legal-sources/citation-lookup", description: "Look up a specific citation" },
      { method: "POST", path: "/legal-sources/good-law-check", description: "Verify citation is still current" },
      { method: "GET", path: "/legal-sources/adapters", description: "List connected source adapters" },
    ],
  },
  {
    name: "Legal Features",
    endpoints: [
      { method: "POST", path: "/redline/compare", description: "Generate tracked-changes redline" },
      { method: "POST", path: "/conflicts/check", description: "Run conflict-of-interest check" },
      { method: "POST", path: "/citations/validate", description: "Check if citation is still good law" },
      { method: "POST", path: "/multi-jurisdiction/compare", description: "Compare across jurisdictions" },
      { method: "POST", path: "/privilege/tag", description: "Assert attorney-client privilege" },
      { method: "POST", path: "/regulatory/monitors", description: "Monitor regulation for changes" },
    ],
  },
  {
    name: "Matters & Workflow",
    endpoints: [
      { method: "POST", path: "/matters", description: "Create a matter" },
      { method: "GET", path: "/matters/{id}/deadlines", description: "List matter deadlines" },
      { method: "POST", path: "/memory/preferences", description: "Set organization preferences" },
      { method: "GET", path: "/audit/logs", description: "Query audit trail" },
    ],
  },
];

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  POST: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  PATCH: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  DELETE: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

export default function APIDocsPage() {
  return (
    <>
      {/* Hero */}
      <section className="py-20">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">API Reference</h1>
          <p className="mt-4 text-lg text-muted-foreground">
            Build on MyDenning. Every feature available via REST API.
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Lock className="h-4 w-4" /> JWT Authentication
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Code2 className="h-4 w-4" /> JSON responses
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Zap className="h-4 w-4" /> 60+ endpoints
            </div>
          </div>
        </div>
      </section>

      {/* Base URL */}
      <section className="border-t bg-card py-8">
        <div className="mx-auto max-w-4xl px-6">
          <div className="rounded-lg border bg-background p-4">
            <p className="text-sm text-muted-foreground">Base URL</p>
            <code className="mt-1 block font-mono text-sm">https://api.mydenning.com/api/v1</code>
          </div>
        </div>
      </section>

      {/* Endpoints */}
      <section className="py-16">
        <div className="mx-auto max-w-4xl px-6 space-y-12">
          {endpointGroups.map((group) => (
            <div key={group.name}>
              <h2 className="text-xl font-semibold">{group.name}</h2>
              <div className="mt-4 space-y-2">
                {group.endpoints.map((ep) => (
                  <div key={ep.path} className="flex items-center gap-3 rounded-md border bg-card p-3">
                    <span className={`inline-block w-14 rounded px-2 py-0.5 text-center text-xs font-semibold ${METHOD_COLORS[ep.method]}`}>
                      {ep.method}
                    </span>
                    <code className="flex-1 font-mono text-sm">{ep.path}</code>
                    <span className="hidden text-sm text-muted-foreground sm:inline">{ep.description}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Interactive docs */}
      <section className="border-t bg-card py-16">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight">Full interactive docs</h2>
          <p className="mt-3 text-muted-foreground">
            The backend ships with auto-generated OpenAPI/Swagger documentation.
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <Link href="https://api.mydenning.com/docs" target="_blank">
              <Button className="gap-2">Swagger UI <ArrowRight className="h-4 w-4" /></Button>
            </Link>
            <Link href="https://api.mydenning.com/redoc" target="_blank">
              <Button variant="outline" className="gap-2">ReDoc <ArrowRight className="h-4 w-4" /></Button>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
