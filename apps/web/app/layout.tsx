import type { Metadata } from "next";
import { SidebarStateProvider } from "@/components/layout/sidebar-state-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AION",
  description: "Artificial Intelligence Operating Nervous System",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{document.documentElement.dataset.sidebarCollapsed=String(localStorage.getItem("aion-sidebar-collapsed")==="true")}catch(e){document.documentElement.dataset.sidebarCollapsed="false"}`,
          }}
        />
      </head>
      <body>
        <SidebarStateProvider>{children}</SidebarStateProvider>
      </body>
    </html>
  );
}
