"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils/cn";
import {
  Scale, MessageSquare, Search, FileText, Briefcase, BookOpen,
  PenTool, GitCompare, Bell, Shield, ClipboardList, Settings,
  ChevronLeft, ChevronRight, Users, CheckSquare, Clock,
  Receipt, Calendar, Building2, UsersRound,
} from "lucide-react";
import { useState } from "react";

const navigation = [
  // Practice management — the core
  { name: "Clients", href: "/clients", icon: Building2, group: "Practice" },
  { name: "Matters", href: "/matters", icon: Briefcase, group: "Practice" },
  { name: "Documents", href: "/documents", icon: FileText, group: "Practice" },
  { name: "Tasks", href: "/tasks", icon: CheckSquare, group: "Practice" },
  { name: "Calendar", href: "/calendar", icon: Calendar, group: "Practice" },
  { name: "Billing", href: "/billing", icon: Receipt, group: "Practice" },

  // AI intelligence — woven through everything
  { name: "Ask", href: "/ask", icon: MessageSquare, group: "Intelligence" },
  { name: "Research", href: "/research", icon: Search, group: "Intelligence" },
  { name: "Compare", href: "/compare", icon: GitCompare, group: "Intelligence" },
  { name: "Draft", href: "/draft", icon: PenTool, group: "Intelligence" },
  { name: "Playbooks", href: "/playbooks", icon: BookOpen, group: "Intelligence" },

  // Firm operations
  { name: "Monitor", href: "/monitor", icon: Bell, group: "Operations" },
  { name: "Conflicts", href: "/conflicts", icon: Shield, group: "Operations" },
  { name: "Portal", href: "/portal-clients", icon: Users, group: "Operations" },
  { name: "Team", href: "/team", icon: UsersRound, group: "Operations" },
  { name: "Audit", href: "/audit", icon: ClipboardList, group: "Operations" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  let lastGroup = "";

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r bg-card transition-all duration-200",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Scale className="h-4 w-4" />
        </div>
        {!collapsed && <span className="text-sm font-semibold tracking-tight">MyDenning</span>}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-2">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          const showGroup = !collapsed && item.group !== lastGroup;
          lastGroup = item.group;

          return (
            <div key={item.href}>
              {showGroup && (
                <p className="mt-4 mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {item.group}
                </p>
              )}
              <Link
                href={item.href}
                title={collapsed ? item.name : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span>{item.name}</span>}
              </Link>
            </div>
          );
        })}
      </nav>

      {/* Settings + Collapse */}
      <div className="border-t p-2 space-y-1">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground",
            pathname === "/settings" && "bg-secondary text-foreground"
          )}
        >
          <Settings className="h-4 w-4 shrink-0" />
          {!collapsed && <span>Settings</span>}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/50"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
