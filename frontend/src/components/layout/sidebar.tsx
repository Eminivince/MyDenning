"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils/cn";
import {
  Scale, MessageSquare, Search, FileText, Briefcase, BookOpen,
  PenTool, GitCompare, Bell, Shield, ClipboardList, Settings,
  ChevronLeft, ChevronRight,
} from "lucide-react";
import { useState } from "react";

const navigation = [
  { name: "Ask", href: "/ask", icon: MessageSquare, description: "Legal Q&A" },
  { name: "Research", href: "/research", icon: Search, description: "Search authorities" },
  { name: "Documents", href: "/documents", icon: FileText, description: "Manage documents" },
  { name: "Matters", href: "/matters", icon: Briefcase, description: "Track matters" },
  { name: "Playbooks", href: "/playbooks", icon: BookOpen, description: "Contract playbooks" },
  { name: "Draft", href: "/draft", icon: PenTool, description: "Generate work products" },
  { name: "Compare", href: "/compare", icon: GitCompare, description: "Redline & compare" },
  { name: "Monitor", href: "/monitor", icon: Bell, description: "Regulatory alerts" },
  { name: "Conflicts", href: "/conflicts", icon: Shield, description: "Conflict checks" },
  { name: "Audit", href: "/audit", icon: ClipboardList, description: "Audit trail" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

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
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.name : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.name}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Settings + Collapse */}
      <div className="border-t p-2 space-y-1">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground",
            pathname === "/settings" && "bg-secondary text-foreground"
          )}
        >
          <Settings className="h-4 w-4 shrink-0" />
          {!collapsed && <span>Settings</span>}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/50"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
