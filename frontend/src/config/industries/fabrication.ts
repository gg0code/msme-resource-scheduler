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
