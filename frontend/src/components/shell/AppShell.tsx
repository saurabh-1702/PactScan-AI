"use client";

import { Menu as MenuIcon, Search, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { AUTH_EVENT, clearToken, getCurrentUser, getToken } from "@/lib/auth";
import { canAccessRoute } from "@/lib/permissions";
import { SessionProvider } from "@/lib/session";
import { cn } from "@/components/ui/cn";
import CommandPalette from "./CommandPalette";
import NotificationsMenu from "./NotificationsMenu";
import ProcessIndicator from "./ProcessIndicator";
import Sidebar from "./Sidebar";
import UserMenu from "./UserMenu";

const COLLAPSE_KEY = "pactscan_sidebar_collapsed";
const PREFS_EVENT = "pactscan-prefs";

function subscribe(callback: () => void): () => void {
  window.addEventListener(AUTH_EVENT, callback);
  window.addEventListener(PREFS_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(AUTH_EVENT, callback);
    window.removeEventListener(PREFS_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Signed-in frame: route guard, left sidebar, top bar, command palette.
 * /login renders bare. The guard here is a UX convenience — the API enforces
 * the real permissions on every request. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);

  // The token lives in localStorage, so it is read as an external store: null on
  // the server / first paint, the real value once hydrated.
  const token = useSyncExternalStore(subscribe, getToken, () => null);
  const user = useMemo(() => (token ? getCurrentUser() : null), [token]);
  const collapsed = useSyncExternalStore(subscribe, readCollapsed, () => false);
  // false during server render / hydration, true afterwards — the guard must not
  // treat "token not read yet" as "signed out".
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const isLogin = pathname === "/login";
  const allowed = !!user && canAccessRoute(user.role, pathname);

  useEffect(() => {
    if (isLogin || !hydrated) return;
    if (!user) router.replace("/login");
    else if (!allowed) router.replace("/dashboard");
  }, [isLogin, hydrated, user, allowed, router]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const toggleCollapsed = useCallback(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, readCollapsed() ? "0" : "1");
    } catch {
      /* storage blocked — preference just won't persist */
    }
    window.dispatchEvent(new Event(PREFS_EVENT));
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    router.push("/login");
  }, [router]);

  if (isLogin) return <>{children}</>;
  if (!user || !allowed) return null;

  return (
    <SessionProvider value={user}>
      <div className="flex h-screen overflow-hidden">
        {/* Desktop sidebar */}
        <aside
          className="hidden shrink-0 transition-[width] duration-200 lg:block"
          style={{ width: collapsed ? "var(--sidebar-w-collapsed)" : "var(--sidebar-w)" }}
        >
          <Sidebar role={user.role} collapsed={collapsed} onToggle={toggleCollapsed} />
        </aside>

        {/* Mobile drawer */}
        {drawer && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="overlay-in absolute inset-0 bg-ink/30" onClick={() => setDrawer(false)} />
            <div className="popover-in absolute inset-y-0 left-0 w-64 shadow-lg">
              <Sidebar
                role={user.role}
                collapsed={false}
                mobile
                onToggle={() => {}}
                onNavigate={() => setDrawer(false)}
              />
              <button
                type="button"
                aria-label="Close menu"
                onClick={() => setDrawer(false)}
                className="absolute right-2 top-3 flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-hover"
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
            <button
              type="button"
              aria-label="Open menu"
              onClick={() => setDrawer(true)}
              className="flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-hover lg:hidden"
            >
              <MenuIcon className="h-5 w-5" aria-hidden />
            </button>

            <button
              type="button"
              onClick={() => setPalette(true)}
              className={cn(
                "flex h-9 w-full max-w-md items-center gap-2 rounded-md border border-line bg-canvas px-3 text-[13px] text-muted",
                "hover:border-line-strong",
              )}
            >
              <Search className="h-4 w-4 text-faint" aria-hidden />
              <span className="flex-1 text-left">Search or jump to…</span>
              <kbd className="hidden rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] sm:block">
                Ctrl K
              </kbd>
            </button>

            <div className="ml-auto flex items-center gap-1">
              <ProcessIndicator />
              <NotificationsMenu />
              <UserMenu role={user.role} onSignOut={signOut} />
            </div>
          </header>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
        </div>
      </div>

      <CommandPalette role={user.role} open={palette} onOpenChange={setPalette} onSignOut={signOut} />
    </SessionProvider>
  );
}
