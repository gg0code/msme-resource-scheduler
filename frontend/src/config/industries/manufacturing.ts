/**
 * frontend/src/config/industries/manufacturing.ts — v4.0.2
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Industry configuration for the manufacturing vertical. Defines all branding, colour
 * tokens, and UI label strings used when a tenant registers with industry_type='manufacturing'.
 * Introduced in v4.0.2 as part of the multi-industry support feature. Loaded by
 * getIndustryConfig() in index.ts and applied by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES
 * Exports a single manufacturing IndustryConfig object with three sections:
 *   branding — product name (ShopFloor Resource Planner), icon (⚙️), tagline
 *   colours  — hex values backing the CSS theme class 'theme-manufacturing' in index.css
 *   labels   — job=Production Order, employee=Operator, machine=Work Center
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/index.ts — imported into INDUSTRY_CONFIGS map
 *
 * INTERN NOTES
 * - Colours are NOT applied inline. They back the theme-manufacturing CSS class in index.css
 *   which sets CSS variables. Components use var(--brand-primary) etc.
 * - All IndustryLabels fields are required. If types.ts adds a new field,
 *   this file must be updated or TypeScript will error at build time.
 * - Design Principle 11: this file must satisfy tsc --noEmit. The IndustryConfig
 *   type is strict — all fields are required with no Optional<>.
 * - To change labels for this industry: edit the labels block below.
 *   Changes take effect immediately for all tenants with industry_type='manufacturing'.
 */
// src/config/industries/manufacturing.ts — v4.0.2
// ShopFloor Resource Planner — Manufacturing industry configuration

import type { IndustryConfig } from './types'

const manufacturing: IndustryConfig = {
  id: 'manufacturing',

  branding: {
    productName:  'ShopFloor Resource Planner',
    shortName:    'ShopFloor',
    primaryColor: 'slate',
    icon:         '⚙️',
    tagline:      'Production order scheduling for manufacturers',
  },

  colours: {
    sidebarBg:        '#0f172a',
    sidebarBorder:    '#1e293b',
    sidebarText:      '#94a3b8',
    sidebarHover:     '#1e293b',
    sidebarActive:    '#475569',
    sidebarActiveTxt: '#ffffff',
    primary:          '#475569',
    primaryHover:     '#334155',
    primaryLight:     '#f8fafc',
    primaryText:      '#334155',
    headerBg:         '#ffffff',
    headerBorder:     '#e2e8f0',
  },

  labels: {
    job:        'Production Order',
    jobs:       'Production Orders',
    employee:   'Operator',
    employees:  'Operators',
    machine:    'Work Center',
    machines:   'Work Centers',
    material:   'BOM Item',
    materials:  'Bill of Materials',
    skill:      'Skill',
    skills:     'Skills',
    step:       'Operation',
    steps:      'Operations',

    jobsPageTitle:      'Production Orders',
    jobsPageSubtitle:   'Shop floor order board',
    employeesPageTitle: 'Operators',
    machinesPageTitle:  'Work Centers',

    jobNamePlaceholder:  'e.g. Shaft Machining, Gear Assembly…',
    jobTypePlaceholder:  'e.g. CNC Part, Assembly, Fabrication…',
    newJobButton:        'New Order',

    kpiJobs:      'Open Orders',
    kpiOrderBook: 'Order Value',
    kpiProfit:    'Est. Margin',
  },
}

export default manufacturing
