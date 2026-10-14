import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "PropX CRM", description: "Broker workspace: leads, listings, viewings, follow-ups and deals." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  );
}
