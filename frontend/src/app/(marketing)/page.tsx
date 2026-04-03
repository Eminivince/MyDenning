import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  MessageSquare, Search, FileText, GitCompare, PenTool, Bell,
  Shield, BookOpen, Scale, ArrowRight, CheckCircle2, Globe,
  Briefcase, Zap, Lock, BarChart3,
} from "lucide-react";

const features = [
  {
    icon: MessageSquare,
    title: "Ask",
    description: "Ask legal questions in plain English. Get IRAC-structured answers with citations, risk flags, and confidence scores.",
  },
  {
    icon: Search,
    title: "Research",
    description: "Search case law, statutes, and regulations across 30+ jurisdictions. Distinguish binding from persuasive authority.",
  },
  {
    icon: FileText,
    title: "Review Documents",
    description: "Upload contracts and policies. Extract clauses, flag risks, detect deviations from your playbook automatically.",
  },
  {
    icon: GitCompare,
    title: "Compare & Redline",
    description: "Compare documents or versions with tracked-changes output. Every change annotated with legal significance.",
  },
  {
    icon: PenTool,
    title: "Draft",
    description: "Generate legal memos, board resolutions, contract drafts, and negotiation language with full citations.",
  },
  {
    icon: Bell,
    title: "Monitor",
    description: "Track regulatory changes across jurisdictions. Get alerts when laws change that affect your matters.",
  },
];

const jurisdictions = [
  "Nigeria", "United Kingdom", "United States", "European Union",
  "Kenya", "South Africa", "Ghana", "Canada", "India", "Australia",
];

const capabilities = [
  { icon: Shield, title: "Conflict Checking", description: "Cross-matter conflict detection with party normalization" },
  { icon: Lock, title: "Privilege Tagging", description: "Attorney-client privilege, work product, litigation hold" },
  { icon: BookOpen, title: "Contract Playbooks", description: "Standard positions, fallback language, deviation scoring" },
  { icon: Briefcase, title: "Matter Management", description: "Track matters, deadlines, parties, and context" },
  { icon: BarChart3, title: "Citation Validation", description: "Check if cited authority is still good law" },
  { icon: Globe, title: "Multi-Jurisdiction", description: "Compare legal positions across jurisdictions side by side" },
];

const trustedBy = [
  "Law Firms", "In-House Legal Teams", "Compliance Departments",
  "Corporate Counsel", "Government Agencies", "Legal Tech Companies",
];

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-6 pb-24 pt-20 md:pb-32 md:pt-28">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border bg-card px-4 py-1.5 text-sm">
              <Zap className="h-3.5 w-3.5" />
              <span className="text-muted-foreground">Legal intelligence, not legal chatbot</span>
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
              Your legal work,{" "}
              <span className="text-muted-foreground">done right</span>
            </h1>
            <p className="mt-6 text-lg text-muted-foreground md:text-xl">
              MyDenning combines research, document intelligence, memory, and workflow
              automation into one citation-backed legal copilot. Built for lawyers who
              need answers they can trust.
            </p>
            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <Link href="/register">
                <Button size="lg" className="gap-2 px-8">
                  Start free trial <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/api-docs">
                <Button variant="outline" size="lg" className="px-8">
                  View API docs
                </Button>
              </Link>
            </div>
          </div>

          {/* Stats */}
          <div className="mx-auto mt-20 grid max-w-2xl grid-cols-3 gap-8 text-center">
            <div>
              <div className="text-3xl font-bold">30+</div>
              <div className="mt-1 text-sm text-muted-foreground">Jurisdictions</div>
            </div>
            <div>
              <div className="text-3xl font-bold">11</div>
              <div className="mt-1 text-sm text-muted-foreground">Legal databases</div>
            </div>
            <div>
              <div className="text-3xl font-bold">60+</div>
              <div className="mt-1 text-sm text-muted-foreground">API endpoints</div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="product" className="border-t bg-card py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Six modes. One system.</h2>
            <p className="mt-3 text-muted-foreground">
              Not just chat. A complete legal intelligence operating system.
            </p>
          </div>
          <div className="mt-16 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div key={feature.title} className="rounded-lg border bg-background p-6">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                  <feature.icon className="h-5 w-5" />
                </div>
                <h3 className="mt-4 font-semibold">{feature.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Jurisdictions */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Global coverage. Local precision.</h2>
            <p className="mt-3 text-muted-foreground">
              Connected to authoritative legal databases worldwide. No scraping. Only official APIs.
            </p>
          </div>
          <div className="mt-12 flex flex-wrap justify-center gap-3">
            {jurisdictions.map((j) => (
              <div key={j} className="flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm">
                <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                {j}
              </div>
            ))}
            <div className="flex items-center gap-2 rounded-full border border-dashed px-4 py-2 text-sm text-muted-foreground">
              + more coming
            </div>
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="border-t bg-card py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Enterprise-grade capabilities</h2>
            <p className="mt-3 text-muted-foreground">
              Built for serious legal operations. Every feature lawyers actually need.
            </p>
          </div>
          <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {capabilities.map((cap) => (
              <div key={cap.title} className="flex items-start gap-4 rounded-lg border bg-background p-5">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-secondary">
                  <cap.icon className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="font-medium">{cap.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{cap.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* API Section */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="grid items-center gap-12 md:grid-cols-2">
            <div>
              <h2 className="text-3xl font-bold tracking-tight">API-first architecture</h2>
              <p className="mt-4 text-muted-foreground leading-relaxed">
                Every feature available via REST API. Build your own legal tools on top of MyDenning.
                Integrate with your existing systems. White-label for your clients.
              </p>
              <ul className="mt-6 space-y-3">
                {["60+ typed API endpoints", "JWT authentication", "Webhook notifications", "Full audit trail on every operation", "Multi-tenant with organization isolation"].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                    {item}
                  </li>
                ))}
              </ul>
              <Link href="/api-docs" className="mt-8 inline-block">
                <Button variant="outline" className="gap-2">
                  Explore the API <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>
            <div className="rounded-lg border bg-card p-6">
              <pre className="overflow-x-auto text-sm">
                <code className="text-muted-foreground">{`POST /api/v1/analysis/ask
{
  "question": "Can we tokenize this
    asset under Nigerian law?",
  "jurisdiction": "NG",
  "include_sources": true
}

// Response: IRAC-structured analysis
// with citations, confidence score,
// risk flags, and follow-up questions`}</code>
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section className="border-t bg-card py-24">
        <div className="mx-auto max-w-6xl px-6 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Built for legal professionals</h2>
          <p className="mt-3 text-muted-foreground">
            Not a toy. A production legal intelligence system.
          </p>
          <div className="mt-12 flex flex-wrap justify-center gap-4">
            {trustedBy.map((item) => (
              <div key={item} className="rounded-md border bg-background px-5 py-3 text-sm font-medium">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-2xl px-6 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Ready to work smarter?</h2>
          <p className="mt-4 text-muted-foreground">
            Start with a free trial. No credit card required. Upload your first document in under a minute.
          </p>
          <div className="mt-8 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Link href="/register">
              <Button size="lg" className="gap-2 px-8">
                Start free trial <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="mailto:hello@mydenning.com">
              <Button variant="outline" size="lg" className="px-8">
                Talk to sales
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
