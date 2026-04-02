/**
 * frontend/src/config/industries/printing.ts — v4.0.2
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Industry configuration for the printing vertical. Defines all branding, colour
 * tokens, and UI label strings used when a tenant registers with industry_type='printing'.
 * Introduced in v4.0.2 as part of the multi-industry support feature. Loaded by
 * getIndustryConfig() in index.ts and applied by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES
 * Exports a single printing IndustryConfig object with three sections:
 *   branding — product name (PrintFlow Scheduler), icon (🖨️), tagline
 *   colours  — hex values backing the CSS theme class 'theme-printing' in index.css
 *   labels   — job=Job, employee=Operator, machine=Machine (default industry — fallback for unknown types)
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/index.ts — imported into INDUSTRY_CONFIGS map
 *
 * INTERN NOTES
 * - Colours are NOT applied inline. They back the theme-printing CSS class in index.css
 *   which sets CSS variables. Components use var(--brand-primary) etc.
 * - All IndustryLabels fields are required. If types.ts adds a new field,
 *   this file must be updated or TypeScript will error at build time.
 * - Design Principle 11: this file must satisfy tsc --noEmit. The IndustryConfig
 *   type is strict — all fields are required with no Optional<>.
 * - To change labels for this industry: edit the labels block below.
 *   Changes take effect immediately for all tenants with industry_type='printing'.
 */
// src/config/industries/printing.ts — v4.0.2
// PrintFlow Scheduler — Printing & Packaging industry configuration

import type { IndustryConfig } from './types'

const printing: IndustryConfig = {
  id: 'printing',

  branding: {
    productName:  'PrintFlow Scheduler',
    shortName:    'PrintFlow',
    primaryColor: 'blue',
    icon:         '🖨️',
    tagline:      'Production scheduling for printing & packaging',
  },

  colours: {
    sidebarBg:        '#0f172a',
    sidebarBorder:    '#1e293b',
    sidebarText:      '#94a3b8',
    sidebarHover:     '#1e293b',
    sidebarActive:    '#2563eb',
    sidebarActiveTxt: '#ffffff',
    primary:          '#2563eb',
    primaryHover:     '#1d4ed8',
    primaryLight:     '#eff6ff',
    primaryText:      '#1d4ed8',
    headerBg:         '#ffffff',
    headerBorder:     '#e2e8f0',
  },

  labels: {
    job:        'Job',
    jobs:       'Jobs',
    employee:   'Operator',
    employees:  'Operators',
    machine:    'Machine',
    machines:   'Machines',
    material:   'Raw Material',
    materials:  'Raw Materials',
    skill:      'Skill',
    skills:     'Skills',
    step:       'Step',
    steps:      'Steps',

    jobsPageTitle:      'Jobs',
    jobsPageSubtitle:   'Production job board',
    employeesPageTitle: 'Operators',
    machinesPageTitle:  'Machines',

    jobNamePlaceholder:  'e.g. Corrugated Box Run, Label Print…',
    jobTypePlaceholder:  'e.g. Corrugated Box, Mono Carton…',
    newJobButton:        'New Job',

    kpiJobs:      'Active Jobs',
    kpiOrderBook: 'Order Book',
    kpiProfit:    'Est. Profit',
  },
}

export default printing
