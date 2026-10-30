export type Market = "in" | "us";

/**
 * Options for @semcore Select. `label` renders in the closed trigger, `children` renders as
 * the menu item — both are required or the open menu shows empty rows.
 */
export const MARKET_OPTIONS = [
  { value: "in", label: "India", children: "India" },
  { value: "us", label: "United States", children: "United States" },
];

export const MARKET_LABEL: Record<Market, string> = { in: "India", us: "United States" };
