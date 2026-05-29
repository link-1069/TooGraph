import type { PrimaryNavigationSection } from "./layout-mode.ts";

export type NavigationVisibility = "stable" | "developer";

export type NavigationIconKey =
  | "ChatDotRound"
  | "Clock"
  | "Collection"
  | "CollectionTag"
  | "Connection"
  | "DataBoard"
  | "DataLine"
  | "DocumentChecked"
  | "EditPen"
  | "House"
  | "Opportunity"
  | "Reading"
  | "Setting"
  | "Tickets"
  | "Timer"
  | "Tools"
  | "TrendCharts";

export type PrimaryNavigationItem = {
  path: string;
  section: PrimaryNavigationSection;
  labelKey: string;
  icon: NavigationIconKey;
  affordanceId: string;
  affordanceZone?: string;
  pathAfterClick?: string;
  selfSurface?: boolean;
  visibility: NavigationVisibility;
};

export const PRIMARY_NAVIGATION_ITEMS: PrimaryNavigationItem[] = [
  navigationItem("/", "home", "nav.home", "House"),
  navigationItem("/editor", "editor", "nav.editor", "EditPen"),
  navigationItem("/runs", "runs", "nav.runs", "Clock"),
  navigationItem("/library", "graphLibrary", "nav.graphLibrary", "Collection", "library"),
  navigationItem("/scheduler", "scheduler", "nav.scheduler", "Timer"),
  navigationItem("/curator-reports", "curatorReports", "nav.curatorReports", "DataBoard", "curatorReports", "developer"),
  navigationItem("/knowledge", "knowledge", "nav.knowledge", "Reading"),
  {
    ...navigationItem("/buddy", "buddy", "nav.buddy", "ChatDotRound"),
    affordanceZone: "buddy-page",
    pathAfterClick: "",
    selfSurface: true,
  },
  navigationItem("/message-platforms", "messagePlatforms", "nav.messagePlatforms", "Connection", "messagePlatforms"),
  navigationItem("/presets", "presets", "nav.presets", "CollectionTag"),
  navigationItem("/actions", "actions", "nav.actions", "Opportunity"),
  navigationItem("/tools", "tools", "nav.tools", "Tools"),
  navigationItem("/improvements", "improvements", "nav.improvements", "TrendCharts", "improvements", "developer"),
  navigationItem("/models", "models", "nav.models", "DataLine"),
  navigationItem("/model-logs", "modelLogs", "nav.modelLogs", "Tickets", "modelLogs"),
  navigationItem("/evidence", "evidenceSearch", "nav.evidenceSearch", "DocumentChecked", "evidenceSearch", "developer"),
  navigationItem("/settings", "settings", "nav.settings", "Setting"),
];

export function buildVisibleNavigationItems(developerModeEnabled: boolean): PrimaryNavigationItem[] {
  return PRIMARY_NAVIGATION_ITEMS.filter((item) => item.visibility !== "developer" || developerModeEnabled);
}

export function isDeveloperNavigationPath(pathname: string): boolean {
  return PRIMARY_NAVIGATION_ITEMS.some(
    (item) => item.visibility === "developer" && (pathname === item.path || pathname.startsWith(`${item.path}/`)),
  );
}

function navigationItem(
  path: string,
  section: PrimaryNavigationSection,
  labelKey: string,
  icon: NavigationIconKey,
  affordanceName: string = section,
  visibility: NavigationVisibility = "stable",
): PrimaryNavigationItem {
  return {
    path,
    section,
    labelKey,
    icon,
    affordanceId: `app.nav.${affordanceName}`,
    affordanceZone: "app-shell",
    pathAfterClick: path,
    visibility,
  };
}
