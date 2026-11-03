import type { Metadata } from "next";
import { SidebarStateProvider } from "@/components/layout/sidebar-state-provider";
import { ThemeProvider } from "@/components/layout/theme-provider";
import { ProfileProvider } from "@/components/profile/profile-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AION",
  description: "Artificial Intelligence Operating Nervous System",
};

// Applies the stored theme before first paint to avoid a flash of the wrong
// theme. Falls back to the system preference only when no user choice exists.
const THEME_NO_FLASH_SCRIPT = `try{var s=localStorage.getItem("aion-theme");var t=s==="light"||s==="dark"?s:(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{document.documentElement.dataset.sidebarCollapsed=String(localStorage.getItem("aion-sidebar-collapsed")==="true")}catch(e){document.documentElement.dataset.sidebarCollapsed="false"}`,
          }}
        />
        <script dangerouslySetInnerHTML={{ __html: THEME_NO_FLASH_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <ProfileProvider>
            <SidebarStateProvider>{children}</SidebarStateProvider>
          </ProfileProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
