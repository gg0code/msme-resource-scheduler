/**
```typescript
/**
 * FILE PURPOSE
 * This file defines the frontend API client for all Employee-related HTTP operations in the ZetaOps Copilot
 * workforce scheduling application. It exists as a typed abstraction layer between React components and the
 * FastAPI backend's employee endpoints, providing CRUD operations, assignment lookups, and CSV import/export
 * functionality. This file was introduced in early v4 development and sits in the frontend API layer,
 * bridging React components with backend employee data operations while maintaining TypeScript type safety.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared apiClient (Axios instance) from './client' for authenticated HTTP requests
 * 2. Imports TypeScript types (Employee, ImportResult) from the centralized types system
 * 3. Exports a single employeesApi object containing all employee-related API functions
 * 4. Defines list() function to fetch all employees for the current tenant
 * 5. Defines get() function to fetch a single employee by ID
 * 6. Defines create() function to add a new employee with payload validation
 * 7. Defines update() function to modify existing employee data via PATCH
 * 8. Defines delete() function to remove an employee from the system
 * 9. Defines assignments() function to fetch all job assignments for a specific employee
 * 10. Defines importCsv() function to upload and process employee data from CSV files
 * 11. Defines downloadTemplate() function to get a CSV template for bulk employee imports
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * Name         : employeesApi.list
 * Type         : function
 * Purpose      : Fetches all employees belonging to the authenticated user's tenant from the backend.
 *                This function automatically applies tenant scoping on the backend side, so frontend
 *                components receive only employees they have permission to see. Used by employee
 *                listing pages and resource assignment dropdowns throughout the application.
 * Parameters   : none
 * Returns      : Promise<Employee[]> - array of Employee objects with full employee data including
 *                id, tenant_id, full_name, base_availability_pct, hourly_rate, and other fields
 * Calls        : apiClient.get() which uses the Axios instance from './client' with JWT authentication
 * DB/API       : GET /api/employees/ endpoint on FastAPI backend, queries Employee table with tenant_id filter
 * Side effects : none - pure read operation
 *
 * Name         : employeesApi.get
 * Type         : function
 * Purpose      : Retrieves a single employee record by their unique ID. The backend automatically
 *                verifies the employee belongs to the authenticated user's tenant for security.
 *                Used by employee detail pages, edit forms, and anywhere specific employee data is needed.
 * Parameters   : id (number) - the unique database ID of the employee to fetch
 * Returns      : Promise<Employee> - single Employee object with complete employee information
 * Calls        : apiClient.get() with parameterized URL including the employee ID
 * DB/API       : GET /api/employees/{id} endpoint, queries Employee table with id and tenant_id filters
 * Side effects : none - pure read operation
 *
 * Name         : employeesApi.create
 * Type         : function
 * Purpose      : Creates a new employee record in the database with the provided data. The backend
 *                automatically assigns the employee to the authenticated user's tenant and validates
 *                all required fields. Used by "Add Employee" forms and bulk import operations.
 * Parameters   : payload (object) - employee data matching backend schema, typically includes
 *                full_name, base_availability_pct, hourly_rate, and other employee attributes
 * Returns      : Promise<Employee> - the newly created Employee object with assigned ID and tenant_id
 * Calls        : apiClient.post() with employee data payload
 * DB/API       : POST /api/employees/ endpoint, inserts new record into Employee table
 * Side effects : creates new employee record in database, affects employee listings and resource pools
 *
 * Name         : employeesApi.update
 * Type         : function
 * Purpose      : Updates an existing employee's data using HTTP PATCH semantics, allowing partial
 *                updates of employee fields. The backend verifies tenant ownership and validates
 *                changed fields. Used by employee edit forms and bulk update operations.
 * Parameters   : id (number) - unique database ID of employee to update
 *                p (object) - partial employee data with only fields to be changed
 * Returns      : Promise<Employee> - the updated Employee object with all current field values
 * Calls        : apiClient.patch() with employee ID and update payload
 * DB/API       : PATCH /api/employees/{id} endpoint, updates Employee table record
 * Side effects : modifies employee record in database, affects scheduling and resource calculations
 *
 * Name         : employeesApi.delete
 * Type         : function
 * Purpose      : Removes an employee record from the database permanently. The backend handles
 *                cascading deletes or prevents deletion if employee has active job assignments.
 *                Used by employee management interfaces with proper confirmation dialogs.
 * Parameters   : id (number) - unique database ID of employee to delete
 * Returns      : Promise<void> - no data returned, success indicated by resolved promise
 * Calls        : apiClient.delete() with employee ID in URL path
 * DB/API       : DELETE /api/employees/{id} endpoint, removes Employee table record
 * Side effects : permanently deletes employee record, may affect job assignments and scheduling
 *
 * Name         : employeesApi.assignments
 * Type         : function
 * Purpose      : Fetches all job assignments currently allocated to a specific employee, showing
 *                which jobs they're working on, allocation percentages, and assignment status.
 *                Used by employee detail pages and resource utilization reports.
 * Parameters   : id (number) - unique database ID of employee to get assignments for
 * Returns      : Promise<any[]> - array of assignment objects (type not strictly defined)
 * Calls        : apiClient.get() with employee ID in URL path
 * DB/API       : GET /api/assignments/employee/{id} endpoint, queries JobAssignment table
 * Side effects : none - pure read operation
 *
 * Name         : employeesApi.importCsv
 * Type         : function
 * Purpose      : Uploads a CSV file containing bulk employee data to the backend for processing
 *                and import. The backend validates CSV format, checks for duplicates, and creates
 *                employee records in batch. Used by bulk import features for onboarding multiple employees.
 * Parameters   : file (File) - CSV file object from HTML file input containing employee data
 * Returns      : Promise<ImportResult> - import summary with success count, error count, and details
 * Calls        : apiClient.post() with multipart/form-data containing the CSV file
 * DB/API       : POST /api/import/employees endpoint, processes CSV and creates Employee records
 * Side effects : creates multiple employee records in database, generates import log entries
 *
 * Name         : employeesApi.downloadTemplate
 * Type         : function
 * Purpose      : Downloads a CSV template file showing the correct format and column headers
 *                for bulk employee imports. Template includes example data and field descriptions.
 *                Used by import interfaces to help users format their employee data correctly.
 * Parameters   : none
 * Returns      : Promise<Blob> - binary file data
 */

import apiClient from './client'
import type { Employee, ImportResult } from '../types'

export const employeesApi = {
  list: ()                        => apiClient.get<Employee[]>('/employees/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Employee>(`/employees/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Employee>('/employees/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Employee>(`/employees/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/employees/${id}`),
  assignments: (id: number)       => apiClient.get(`/assignments/employee/${id}`).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/import/employees', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/import/template/employees', { responseType: 'blob' }),
}
