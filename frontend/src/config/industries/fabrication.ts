/**
 * frontend/src/config/industries/fabrication.ts — v4.0.2
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Industry configuration for the fabrication vertical. Defines all branding, colour
 * tokens, and UI label strings used when a tenant registers with industry_type='fabrication'.
 * Introduced in v4.0.2 as part of the multi-industry support feature. Loaded by
 * getIndustryConfig() in index.ts and applied by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES
 * Exports a single fabrication IndustryConfig object with three sections:
 *   branding — product name (Fabrication Capacity Planner), icon (🔧), tagline
 *   colours  — hex values backing the CSS theme class 'theme-fabrication' in index.css
 *   labels   — job=Work Order, employee=Fabricator, machine=Work Center
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/index.ts — imported into INDUSTRY_CONFIGS map
 *
 * INTERN NOTES
 * - Colours are NOT applied inline. They back the theme-fabrication CSS class in index.css
 *   which sets CSS variables. Components use var(--brand-primary) etc.
 * - All IndustryLabels fields are required. If types.ts adds a new field,
 *   this file must be updated or TypeScript will error at build time.
 * - Design Principle 11: this file must satisfy tsc --noEmit. The IndustryConfig
 *   type is strict — all fields are required with no Optional<>.
 * - To change labels for this industry: edit the labels block below.
 *   Changes take effect immediately for all tenants with industry_type='fabrication'.
 */
// src/config/industries/fabrication.ts — v4.0.2
// Fabrication Capacity Planner — Metal Fabrication industry configuration

import type { IndustryConfig } from './types'

const fabrication: IndustryConfig = {
  id: 'fabrication',

  branding: {
    productName:  'Fabrication Capacity Planner',
    shortName:    'FabFlow',
    primaryColor: 'orange',
    icon:         '🔧',
    tagline:      'Capacity planning for metal fabrication shops',
  },

  colours: {
    sidebarBg:        '#1c0a00',
    sidebarBorder:    '#431407',
    sidebarText:      '#fdba74',
    sidebarHover:     '#431407',
    sidebarActive:    '#ea580c',
    sidebarActiveTxt: '#ffffff',
    primary:          '#ea580c',
    primaryHover:     '#c2410c',
    primaryLight:     '#fff7ed',
    primaryText:      '#c2410c',
    headerBg:         '#ffffff',
    headerBorder:     '#fed7aa',
  },

  labels: {
    job:        'Work Order',
    jobs:       'Work Orders',
    employee:   'Fabricator',
    employees:  'Fabricators',
    machine:    'Work Center',
    machines:   'Work Centers',
    material:   'Material',
    materials:  'Materials',
    skill:      'Skill',
    skills:     'Skills',
    step:       'Operation',
    steps:      'Operations',

    jobsPageTitle:      'Work Orders',
    jobsPageSubtitle:   'Fabrication work order board',
    employeesPageTitle: 'Fabricators',
    machinesPageTitle:  'Work Centers',

    jobNamePlaceholder:  'e.g. Steel Frame Fabrication, Pipe Bending…',
    jobTypePlaceholder:  'e.g. Structural, Sheet Metal, Pipe…',
    newJobButton:        'New Work Order',

    kpiJobs:      'Open Work Orders',
    kpiOrderBook: 'Order Value',
    kpiProfit:    'Est. Margin',
  },
}

export default fabrication
