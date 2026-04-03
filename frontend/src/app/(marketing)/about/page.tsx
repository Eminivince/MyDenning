import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowRight, Scale, Shield, Globe, BookOpen } from "lucide-react";

const values = [
  {
    icon: BookOpen,
    title: "Citation-backed, always",
    description: "Every answer comes with sources. We never guess. If we don't have authority, we say so.",
  },
  {
    icon: Shield,
    title: "Trust through transparency",
    description: "Full audit trail on every operation. You can trace any answer back to the exact source and model that produced it.",
  },
  {
    icon: Globe,
    title: "Global from day one",
    description: "Built for multi-jurisdiction work. Connected to official legal databases, not scraped from the internet.",
  },
  {
    icon: Scale,
    title: "For lawyers, by lawyers",
    description: "We don't replace legal counsel. We make legal work faster, more accurate, and more auditable.",
  },
];

export default function AboutPage() {
  return (
    <>
      {/* Hero */}
      <section className="py-20">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Legal intelligence that{" "}
            <span className="text-muted-foreground">shows its work</span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground leading-relaxed">
            MyDenning is a legal intelligence platform built for companies and law firms
            that need answers they can verify, cite, and defend. We combine research,
            document intelligence, memory, and workflow automation into one system.
          </p>
        </div>
      </section>

      {/* Story */}
      <section className="border-t bg-card py-24">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="text-2xl font-bold tracking-tight">Why we built this</h2>
          <div className="mt-6 space-y-4 text-muted-foreground leading-relaxed">
            <p>
              Legal professionals don't need another chatbot. They need a system that can
              read their documents, understand their legal problems, retrieve the right
              authority, reason in a structured way, and produce usable outputs with
              citations and risk flags.
            </p>
            <p>
              A legal intelligence buddy should look less like "ChatGPT but for law" and
              more like a legal work copilot with memory, sources, and workflow awareness.
            </p>
            <p>
              That's what MyDenning is. A citation-backed legal copilot that combines
              research, document intelligence, memory, and workflow automation into one system.
            </p>
          </div>
        </div>
      </section>

      {/* Values */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-2xl font-bold tracking-tight">What we believe</h2>
          <div className="mt-12 grid gap-8 md:grid-cols-2">
            {values.map((value) => (
              <div key={value.title} className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary">
                  <value.icon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold">{value.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground leading-relaxed">{value.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t bg-card py-24">
        <div className="mx-auto max-w-2xl px-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight">Work with us</h2>
          <p className="mt-4 text-muted-foreground">
            We're building the operating system for legal intelligence. If that matters to you,
            we'd love to hear from you.
          </p>
          <div className="mt-8 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Link href="/register">
              <Button size="lg" className="gap-2">Start free trial <ArrowRight className="h-4 w-4" /></Button>
            </Link>
            <Link href="mailto:hello@mydenning.com">
              <Button variant="outline" size="lg">Contact us</Button>
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
