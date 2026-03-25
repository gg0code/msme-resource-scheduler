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
