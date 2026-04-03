import Link from "next/link";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Minus } from "lucide-react";
import { cn } from "@/lib/utils/cn";

const plans = [
  {
    name: "Starter",
    description: "For solo practitioners and small teams getting started.",
    price: "$99",
    period: "/month",
    cta: "Start free trial",
    href: "/register",
    featured: false,
    features: [
      { name: "5 users", included: true },
      { name: "100 documents", included: true },
      { name: "Ask (legal Q&A)", included: true },
      { name: "Document review", included: true },
      { name: "5 matters", included: true },
      { name: "Basic research (3 jurisdictions)", included: true },
      { name: "Contract playbooks", included: false },
      { name: "Conflict checking", included: false },
      { name: "Regulatory monitoring", included: false },
      { name: "API access", included: false },
      { name: "Priority support", included: false },
    ],
  },
  {
    name: "Professional",
    description: "For growing firms and in-house legal teams.",
    price: "$349",
    period: "/month",
    cta: "Start free trial",
    href: "/register",
    featured: true,
    features: [
      { name: "25 users", included: true },
      { name: "Unlimited documents", included: true },
      { name: "Ask (legal Q&A)", included: true },
      { name: "Document review & redline", included: true },
      { name: "Unlimited matters", included: true },
      { name: "Full research (all jurisdictions)", included: true },
      { name: "Contract playbooks", included: true },
      { name: "Conflict checking", included: true },
      { name: "Regulatory monitoring", included: true },
      { name: "API access", included: false },
      { name: "Priority support", included: true },
    ],
  },
  {
    name: "Enterprise",
    description: "For large organizations with custom requirements.",
    price: "Custom",
    period: "",
    cta: "Talk to sales",
    href: "mailto:hello@mydenning.com",
    featured: false,
    features: [
      { name: "Unlimited users", included: true },
      { name: "Unlimited documents", included: true },
      { name: "All Professional features", included: true },
      { name: "Multi-jurisdiction comparison", included: true },
      { name: "Citation validation", included: true },
      { name: "Privilege tagging & log", included: true },
      { name: "Full API access", included: true },
      { name: "SSO / SAML", included: true },
      { name: "Custom integrations", included: true },
      { name: "Dedicated account manager", included: true },
      { name: "SLA guarantee", included: true },
    ],
  },
];

const faqs = [
  {
    q: "Is there a free trial?",
    a: "Yes. Every plan starts with a 14-day free trial. No credit card required.",
  },
  {
    q: "Can I switch plans later?",
    a: "Yes. Upgrade or downgrade at any time. Changes take effect at the next billing cycle.",
  },
  {
    q: "What jurisdictions are covered?",
    a: "We cover 30+ jurisdictions including Nigeria, UK, US, EU, Kenya, South Africa, Ghana, Canada, India, and Australia through 11 authoritative legal database integrations.",
  },
  {
    q: "Do you offer annual billing?",
    a: "Yes. Annual billing gives you 2 months free (pay for 10, get 12).",
  },
  {
    q: "Is my data secure?",
    a: "All data is encrypted in transit and at rest. We support organization-level isolation, privilege tagging, and full audit trails. Enterprise plans include SSO.",
  },
  {
    q: "Can I use the API to build my own tools?",
    a: "Yes. Enterprise plans include full API access with 60+ endpoints. You can build custom workflows, integrations, and white-label solutions.",
  },
];

export default function PricingPage() {
  return (
    <>
      {/* Header */}
      <section className="py-20">
        <div className="mx-auto max-w-6xl px-6 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Simple, transparent pricing
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-muted-foreground">
            Start free. Scale as your legal operations grow. No hidden fees.
          </p>
        </div>
      </section>

      {/* Plans */}
      <section className="pb-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="grid gap-8 lg:grid-cols-3">
            {plans.map((plan) => (
              <div
                key={plan.name}
                className={cn(
                  "relative rounded-lg border bg-card p-8",
                  plan.featured && "border-primary shadow-lg ring-1 ring-primary"
                )}
              >
                {plan.featured && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-xs font-medium text-primary-foreground">
                    Most popular
                  </div>
                )}
                <div>
                  <h3 className="text-lg font-semibold">{plan.name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>
                  <div className="mt-6">
                    <span className="text-4xl font-bold">{plan.price}</span>
                    <span className="text-muted-foreground">{plan.period}</span>
                  </div>
                </div>
                <Link href={plan.href} className="mt-6 block">
                  <Button className="w-full" variant={plan.featured ? "default" : "outline"}>
                    {plan.cta}
                  </Button>
                </Link>
                <ul className="mt-8 space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature.name} className="flex items-center gap-3 text-sm">
                      {feature.included ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                      ) : (
                        <Minus className="h-4 w-4 shrink-0 text-muted-foreground/40" />
                      )}
                      <span className={cn(!feature.included && "text-muted-foreground")}>{feature.name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t bg-card py-24">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="text-center text-2xl font-bold tracking-tight">Frequently asked questions</h2>
          <div className="mt-12 space-y-8">
            {faqs.map((faq) => (
              <div key={faq.q}>
                <h3 className="font-medium">{faq.q}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
