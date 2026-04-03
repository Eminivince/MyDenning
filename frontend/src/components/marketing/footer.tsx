import Link from "next/link";
import { Scale } from "lucide-react";

const footerLinks = {
  Product: [
    { name: "Ask", href: "/#product" },
    { name: "Research", href: "/#product" },
    { name: "Document Review", href: "/#product" },
    { name: "Contract Playbooks", href: "/#product" },
    { name: "Regulatory Monitor", href: "/#product" },
  ],
  Developers: [
    { name: "API Documentation", href: "/api-docs" },
    { name: "API Status", href: "/api-docs" },
  ],
  Company: [
    { name: "About", href: "/about" },
    { name: "Pricing", href: "/pricing" },
    { name: "Contact", href: "mailto:hello@mydenning.com" },
  ],
  Legal: [
    { name: "Privacy Policy", href: "#" },
    { name: "Terms of Service", href: "#" },
    { name: "Security", href: "#" },
  ],
};

export function Footer() {
  return (
    <footer className="border-t bg-card">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid gap-8 md:grid-cols-5">
          {/* Brand */}
          <div className="md:col-span-1">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Scale className="h-3.5 w-3.5" />
              </div>
              <span className="font-semibold">MyDenning</span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              Legal intelligence for companies that take law seriously.
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title}>
              <h4 className="text-sm font-semibold">{title}</h4>
              <ul className="mt-3 space-y-2">
                {links.map((link) => (
                  <li key={link.name}>
                    <Link href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                      {link.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t pt-8 text-center text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} MyDenning. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
