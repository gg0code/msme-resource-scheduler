/**
 * frontend/src/config/industries/chemical.ts — v4.0.2
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Industry configuration for the chemical vertical. Defines all branding, colour
 * tokens, and UI label strings used when a tenant registers with industry_type='chemical'.
 * Introduced in v4.0.2 as part of the multi-industry support feature. Loaded by
 * getIndustryConfig() in index.ts and applied by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES
 * Exports a single chemical IndustryConfig object with three sections:
 *   branding — product name (Process Batch Scheduler), icon (🧪), tagline
 *   colours  — hex values backing the CSS theme class 'theme-chemical' in index.css
 *   labels   — job=Batch Order, employee=Operator, machine=Reactor, step=Phase
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/index.ts — imported into INDUSTRY_CONFIGS map
 *
 * INTERN NOTES
 * - Colours are NOT applied inline. They back the theme-chemical CSS class in index.css
 *   which sets CSS variables. Components use var(--brand-primary) etc.
 * - All IndustryLabels fields are required. If types.ts adds a new field,
 *   this file must be updated or TypeScript will error at build time.
 * - Design Principle 11: this file must satisfy tsc --noEmit. The IndustryConfig
 *   type is strict — all fields are required with no Optional<>.
 * - To change labels for this industry: edit the labels block below.
 *   Changes take effect immediately for all tenants with industry_type='chemical'.
 */
// src/config/industries/chemical.ts — v4.0.2
// Process Batch Scheduler — Chemical / Process Industry configuration

import type { IndustryConfig } from './types'

const chemical: IndustryConfig = {
  id: 'chemical',

  branding: {
    productName:  'Process Batch Scheduler',
    shortName:    'BatchFlow',
    primaryColor: 'green',
    icon:         '🧪',
    tagline:      'Batch scheduling for chemical & process industries',
  },

  colours: {
    sidebarBg:        '#052e16',
    sidebarBorder:    '#14532d',
    sidebarText:      '#86efac',
    sidebarHover:     '#14532d',
    sidebarActive:    '#16a34a',
    sidebarActiveTxt: '#ffffff',
    primary:          '#16a34a',
    primaryHover:     '#15803d',
    primaryLight:     '#f0fdf4',
    primaryText:      '#15803d',
    headerBg:         '#ffffff',
    headerBorder:     '#bbf7d0',
  },

  labels: {
    job:        'Batch Order',
    jobs:       'Batch Orders',
    employee:   'Operator',
    employees:  'Operators',
    machine:    'Reactor',
    machines:   'Reactors',
    material:   'Batch Input',
    materials:  'Batch Inputs',
    skill:      'Qualification',
    skills:     'Qualifications',
    step:       'Phase',
    steps:      'Phases',

    jobsPageTitle:      'Batch Orders',
    jobsPageSubtitle:   'Process batch scheduling board',
    employeesPageTitle: 'Operators',
    machinesPageTitle:  'Reactors',

    jobNamePlaceholder:  'e.g. Batch Mix A, Reactor Run 12…',
    jobTypePlaceholder:  'e.g. Mixing, Reaction, Filling…',
    newJobButton:        'New Batch',

    kpiJobs:      'Active Batches',
    kpiOrderBook: 'Batch Value',
    kpiProfit:    'Est. Margin',
  },
}

export default chemical
