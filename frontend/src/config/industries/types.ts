// src/config/industries/types.ts — v4.0.7

export interface IndustryColours {
  sidebarBg:        string
  sidebarBorder:    string
  sidebarText:      string
  sidebarHover:     string
  sidebarActive:    string
  sidebarActiveTxt: string
  primary:          string
  primaryHover:     string
  primaryLight:     string
  primaryText:      string
  headerBg:         string
  headerBorder:     string
}

export interface IndustryLabels {
  job:        string
  jobs:       string
  employee:   string
  employees:  string
  machine:    string
  machines:   string
  material:   string
  materials:  string
  skill:      string
  skills:     string
  step:       string
  steps:      string
  jobsPageTitle:       string
  jobsPageSubtitle:    string
  employeesPageTitle:  string
  machinesPageTitle:   string
  jobNamePlaceholder:  string
  jobTypePlaceholder:  string
  newJobButton:        string
  kpiJobs:       string
  kpiOrderBook:  string
  kpiProfit:     string
}

export interface IndustryBranding {
  productName:   string
  shortName:     string
  primaryColor:  string
  icon:          string
  tagline:       string
}

export interface IndustryConfig {
  id:       string
  branding: IndustryBranding
  colours:  IndustryColours
  labels:   IndustryLabels
}
