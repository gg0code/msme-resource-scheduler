/**
 * frontend/src/config/industries/field_service.ts — v4.0.2
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Industry configuration for the field_service vertical. Defines all branding, colour
 * tokens, and UI label strings used when a tenant registers with industry_type='field_service'.
 * Introduced in v4.0.2 as part of the multi-industry support feature. Loaded by
 * getIndustryConfig() in index.ts and applied by IndustryContext.tsx.
 *
 * WHAT THIS FILE DOES
 * Exports a single field_service IndustryConfig object with three sections:
 *   branding — product name (Field Service Planner), icon (🚗), tagline
 *   colours  — hex values backing the CSS theme class 'theme-field_service' in index.css
 *   labels   — job=Service Job, employee=Technician, machine=Vehicle/Tool, skill=Certification
 *
 * WHO CALLS THIS FILE
 * - frontend/src/config/industries/index.ts — imported into INDUSTRY_CONFIGS map
 *
 * INTERN NOTES
 * - Colours are NOT applied inline. They back the theme-field_service CSS class in index.css
 *   which sets CSS variables. Components use var(--brand-primary) etc.
 * - All IndustryLabels fields are required. If types.ts adds a new field,
 *   this file must be updated or TypeScript will error at build time.
 * - Design Principle 11: this file must satisfy tsc --noEmit. The IndustryConfig
 *   type is strict — all fields are required with no Optional<>.
 * - To change labels for this industry: edit the labels block below.
 *   Changes take effect immediately for all tenants with industry_type='field_service'.
 */
// src/config/industries/field_service.ts — v4.0.2
// Field Service Planner — Field Service / Maintenance industry configuration

import type { IndustryConfig } from './types'

const field_service: IndustryConfig = {
  id: 'field_service',

  branding: {
    productName:  'Field Service Planner',
    shortName:    'ServiceFlow',
    primaryColor: 'purple',
    icon:         '🚗',
    tagline:      'Job scheduling for field service & maintenance teams',
  },

  colours: {
    sidebarBg:        '#1e1b4b',
    sidebarBorder:    '#312e81',
    sidebarText:      '#c4b5fd',
    sidebarHover:     '#312e81',
    sidebarActive:    '#7c3aed',
    sidebarActiveTxt: '#ffffff',
    primary:          '#7c3aed',
    primaryHover:     '#6d28d9',
    primaryLight:     '#f5f3ff',
    primaryText:      '#6d28d9',
    headerBg:         '#ffffff',
    headerBorder:     '#ddd6fe',
  },

  labels: {
    job:        'Service Job',
    jobs:       'Service Jobs',
    employee:   'Technician',
    employees:  'Technicians',
    machine:    'Vehicle/Tool',
    machines:   'Vehicles & Tools',
    material:   'Part/Consumable',
    materials:  'Parts & Consumables',
    skill:      'Certification',
    skills:     'Certifications',
    step:       'Task',
    steps:      'Tasks',

    jobsPageTitle:      'Service Jobs',
    jobsPageSubtitle:   'Field service job board',
    employeesPageTitle: 'Technicians',
    machinesPageTitle:  'Vehicles & Tools',

    jobNamePlaceholder:  'e.g. AC Maintenance, Generator Service…',
    jobTypePlaceholder:  'e.g. HVAC, Electrical, Plumbing…',
    newJobButton:        'New Service Job',

    kpiJobs:      'Active Jobs',
    kpiOrderBook: 'Job Value',
    kpiProfit:    'Est. Margin',
  },
}

export default field_service
