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
