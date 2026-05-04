// src/config/industries/field_service.ts - v4.0.2
// Field Service Planner - Field Service / Maintenance industry configuration

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

  pickers: {
    skills: [
      'HVAC',
      'Electrical',
      'Plumbing',
      'Civil Works',
      'Helper',
    ],
    machineTypes: [
      'Service Van',
      'Hydraulic Lift',
      'Diagnostic Kit',
      'Pressure Washer',
      'Pipe Threader',
    ],
  },
}

export default field_service
