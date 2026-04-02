// src/config/industries/printing.ts - v4.0.2
// PrintFlow Scheduler - Printing & Packaging industry configuration

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
