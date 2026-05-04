// src/config/industries/manufacturing.ts - v4.0.2
// ShopFloor Resource Planner - Manufacturing industry configuration

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

  pickers: {
    skills: [
      'CNC Operation',
      'Welding',
      'Assembly',
      'Quality Check',
      'Helper',
    ],
    machineTypes: [
      'CNC Lathe',
      'Welding Station',
      'Assembly Line',
      'Milling Machine',
      'Drilling Machine',
    ],
  },
}

export default manufacturing
