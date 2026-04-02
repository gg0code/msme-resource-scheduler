/**
 * frontend/src/config/industries/types.ts — v4.0.9
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Defines the TypeScript interfaces for the industry configuration system.
 * Every industry (printing, manufacturing, fabrication, chemical, field_service)
 * implements these interfaces. Introduced in v4.0.2, updated in v4.0.7 when colours
 * moved to CSS variables. Sits in the config/industries/ folder and is imported by
 * every industry config file and by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines IndustryColours — all CSS variable backing values (hex colours).
 *    Note: as of v4.0.7 these are read by index.css theme classes, not applied
 *    inline. Components use var(--brand-primary) etc, not these values directly.
 * 2. Defines IndustryLabels — all UI strings that vary per industry
 *    (job/jobs, employee/employees, machine/machines etc).
 * 3. Defines IndustryBranding — product name, short name, icon, tagline.
 * 4. Defines IndustryConfig — the root interface combining id, branding,
 *    colours, and labels. Every industry file exports one of these.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/printing.ts
 * - frontend/src/config/industries/manufacturing.ts
 * - frontend/src/config/industries/fabrication.ts
 * - frontend/src/config/industries/chemical.ts
 * - frontend/src/config/industries/field_service.ts
 * - frontend/src/config/industries/index.ts
 * - frontend/src/context/IndustryContext.tsx
 *
 * INTERN NOTES
 * - IndustryColours fields are no longer applied via React inline styles since v4.0.7.
 *   They back the CSS classes in index.css (theme-printing, theme-manufacturing etc).
 *   Do not read these fields directly in components — use CSS variables instead.
 * - IndustryLabels must be complete — every field is required (no Optional<>).
 *   If you add a new label field here, you must add it to ALL 5 industry files.
 * - Design Principle 11: This file is the source of truth for the IndustryConfig
 *   type. Any change here cascades to all 5 industry files and IndustryContext.
 * - If a component shows the wrong label: check that useLabels() is called (not
 *   hardcoded strings) and that the industry file has the correct value.
 */

// src/config/industries/types.ts — v4.0.9
// IndustryColours is retained for backward compatibility but the v4.0.7
// refactor moved colour application to CSS body classes (index.css).
// Components should use CSS variables (var(--brand-primary) etc) not
// IndustryColours fields directly.

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

export interface IndustryLabels {
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

  jobsPageTitle:      string
  jobsPageSubtitle:   string
  employeesPageTitle: string
  machinesPageTitle:  string

  jobNamePlaceholder: string
  jobTypePlaceholder: string

  newJobButton: string

  kpiJobs:      string
  kpiOrderBook: string
  kpiProfit:    string
}

export interface IndustryBranding {
  productName:  string
  shortName:    string
  primaryColor: string
  icon:         string
  tagline:      string
}

export interface IndustryConfig {
  id:       string
  branding: IndustryBranding
  colours:  IndustryColours
  labels:   IndustryLabels
}
