import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hearthline · Property Planner",
  description:
    "Turn your finances and risk preferences into property buying ranges, listing matches, and rental investment analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
