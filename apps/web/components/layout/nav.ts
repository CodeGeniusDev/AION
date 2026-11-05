import {
  Bell,
  Bot,
  FlaskConical,
  LayoutDashboard,
  ListTodo,
  MemoryStick,
  MessageCircleMore,
  Monitor,
  Network,
  Settings,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Single source of truth for primary navigation — shared by the sidebar and
 * the global search so page results never drift from the actual routes. */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "AI Chat", href: "/chat", icon: MessageCircleMore },
      { label: "Tasks", href: "/tasks", icon: ListTodo },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { label: "Agents", href: "/agents", icon: Bot },
      { label: "Workflows", href: "/workflows", icon: Network },
      { label: "Memory", href: "/memory", icon: MemoryStick },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Desktop", href: "/desktop", icon: Monitor },
      { label: "Research", href: "/research", icon: FlaskConical },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

/** Pages reachable outside the sidebar (used as searchable destinations). */
export const EXTRA_PAGES: NavItem[] = [
  { label: "Profile", href: "/profile", icon: UserRound },
  { label: "Notifications", href: "/alert", icon: Bell },
];

export const FLAT_NAV: NavItem[] = [
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...EXTRA_PAGES,
];
