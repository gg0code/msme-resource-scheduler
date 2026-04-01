// src/config/industries/types.ts — v4.0.9
// ─────────────────────────────────────────────────────────────────────────────
// Industry configuration types.
// IndustryColours is retained for backward compatibility but the v4.0.7
// refactor moved colour application to CSS body classes (index.css).
// Components should use CSS variables (var(--brand-primary) etc) not
// IndustryColours fields directly.
// ─────────────────────────────────────────────────────────────────────────────

// ── Colours (CSS variable backing — kept for config files) ────────────────────

export interface IndustryColours {
  sidebarBg:        string
  sidebarBorder:    string
  sidebarText:      string
  sidebarHover:     string
  sidebarActive:    string
  sidebarActiveTxt: string
  primary:          string
  primaryHover:     string
  primaryLight:     string
  primaryText:      string
  headerBg:         string
  headerBorder:     string
}

// ── Labels — all UI strings per industry ─────────────────────────────────────

export interface IndustryLabels {
  // Core entity names (singular + plural)
  job:       string
  jobs:      string
  employee:  string
  employees: string
  machine:   string
  machines:  string
  material:  string
  materials: string
  skill:     string
  skills:    string
  step:      string
  steps:     string

  // Page titles
  jobsPageTitle:      string
  jobsPageSubtitle:   string
  employeesPageTitle: string
  machinesPageTitle:  string

  // Form placeholders
  jobNamePlaceholder: string
  jobTypePlaceholder: string

  // Button labels
  newJobButton: string

  // KPI card labels
  kpiJobs:      string
  kpiOrderBook: string
  kpiProfit:    string
}

// ── Branding ──────────────────────────────────────────────────────────────────

export interface IndustryBranding {
  productName:  string
  shortName:    string
  primaryColor: string
  icon:         string
  tagline:      string
}

// ── Full industry config ──────────────────────────────────────────────────────

export interface IndustryConfig {
  id:       string
  branding: IndustryBranding
  colours:  IndustryColours
  labels:   IndustryLabels
}
