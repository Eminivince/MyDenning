import type { Metadata } from "next";
import { Providers } from "@/components/shared/providers";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "MyDenning — Legal Intelligence",
  description: "Citation-backed legal copilot for research, document intelligence, and workflow automation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">{/* system font stack from tailwind */}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
