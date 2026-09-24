import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/shell/AppShell";
import { ProcessProvider } from "@/components/shell/Processes";
import { TooltipProvider } from "@/components/ui/Overlay";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PactScan",
  description: "Contract compliance for vendor data-processing agreements",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="h-screen">
        <TooltipProvider>
          <ProcessProvider>
            <AppShell>{children}</AppShell>
          </ProcessProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
