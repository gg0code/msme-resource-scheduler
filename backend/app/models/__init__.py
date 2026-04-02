"""
```python
"""
FILE PURPOSE
This file serves as the central import hub for all SQLAlchemy ORM models in the ZetaOps Copilot
backend application. It exists to provide a single point of import for all database models,
making it easier for other parts of the application to access model classes without needing
to know their specific file locations. This file was introduced in the early architecture of
v4-dev and sits at the foundation of the data layer, ensuring all models are properly exposed
to the rest of the application including routers, services, and CRUD operations.

WHAT THIS FILE DOES — step by step
1. Imports the Skill model from the skills module for defining employee and machine capabilities
2. Imports Employee and EmployeeSkill models for workforce management and skill associations
3. Imports Machine and MachineSkillRequirement models for equipment management and capability tracking
4. Imports Job, JobSkillRequirement, and JobAssignment models for work order and resource allocation
5. Imports AvailabilityOverride model for handling custom availability schedules
6. Imports authentication-related models: Tenant, User, and RefreshToken for multi-tenant security
7. Imports WhatsApp-specific models: PhoneTenantMap and WhatsAppConversation for v5 Copilot features
8. Makes all these models available as a single import point for the rest of the application

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : Skill
Type         : SQLAlchemy ORM model class
Purpose      : Represents a capability or competency that employees can possess and machines can require.
              Used by the scheduling engine to match workers and equipment to appropriate jobs.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes and column definitions
DB/API       : Maps to 'skills' table with tenant_id scoping
Side effects : None directly, but instances affect scheduling decisions

Name         : Employee
Type         : SQLAlchemy ORM model class
Purpose      : Represents workforce members who can be assigned to jobs. Contains availability percentages,
              hourly rates, and relationships to skills. Core to resource allocation and cost calculations.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes, relationships to EmployeeSkill and JobAssignment
DB/API       : Maps to 'employees' table with mandatory tenant_id filtering
Side effects : Changes affect scheduling engine calculations and availability checks

Name         : EmployeeSkill
Type         : SQLAlchemy ORM model class
Purpose      : Junction table linking employees to their skills with proficiency levels. Enables the
              scheduler to match qualified workers to jobs requiring specific capabilities.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy relationship definitions to Employee and Skill models
DB/API       : Maps to 'employee_skills' association table with tenant_id scoping
Side effects : Modifications impact skill-based job assignment decisions

Name         : Machine
Type         : SQLAlchemy ORM model class
Purpose      : Represents manufacturing equipment that can be allocated to jobs. Tracks machine types,
              operational status, hourly rates, and capability requirements for scheduling decisions.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes and relationships to MachineSkillRequirement
DB/API       : Maps to 'machines' table with tenant_id filtering for multi-tenant isolation
Side effects : Status changes affect availability calculations and job assignment possibilities

Name         : MachineSkillRequirement
Type         : SQLAlchemy ORM model class
Purpose      : Defines what skills are needed to operate specific machines. Used by the scheduling
              engine to ensure only qualified employees are assigned to machine-dependent jobs.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy relationships to Machine and Skill models
DB/API       : Maps to 'machine_skill_requirements' table with tenant_id scoping
Side effects : Changes affect which employees can be assigned to machine-based job steps

Name         : Job
Type         : SQLAlchemy ORM model class
Purpose      : Core work order model representing manufacturing jobs with priorities, schedules, materials,
              and status tracking. Central to the entire scheduling system and timeline calculations.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy relationships to JobStep, JobAssignment, JobSkillRequirement
DB/API       : Maps to 'jobs' table with tenant_id mandatory for security (principle #2)
Side effects : Status changes trigger auto_advance background tasks and affect scheduling engine

Name         : JobSkillRequirement
Type         : SQLAlchemy ORM model class
Purpose      : Specifies what skills are required to complete a job. Enables skill-based filtering
              during resource allocation to prevent unqualified assignments (amber skill gaps).
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy relationships to Job and Skill models
DB/API       : Maps to 'job_skill_requirements' table with tenant_id filtering
Side effects : Changes affect employee eligibility for job assignments and scheduling conflicts

Name         : JobAssignment
Type         : SQLAlchemy ORM model class
Purpose      : Links jobs to specific employees and machines with allocation percentages. Represents
              the actual resource assignments made by the scheduling engine after optimization.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy relationships to Job, Employee, and Machine models
DB/API       : Maps to 'job_assignments' table with tenant_id scoping for security
Side effects : Creates/updates affect resource utilization calculations and schedule displays

Name         : AvailabilityOverride
Type         : SQLAlchemy ORM model class
Purpose      : Handles custom availability schedules for employees and machines that deviate from
              base availability percentages. Used by availability_engine.py for accurate scheduling.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes and date/time field definitions
DB/API       : Maps to 'availability_overrides' table with tenant_id mandatory filtering
Side effects : Active overrides modify resource availability calculations in real-time

Name         : Tenant
Type         : SQLAlchemy ORM model class
Purpose      : Multi-tenant isolation model containing organization details, subscription plans,
              industry types, and AI usage quotas. Root of all tenant_id scoping throughout the system.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes and enum field definitions
DB/API       : Maps to 'tenants' table, referenced by ALL other models via tenant_id foreign keys
Side effects : Plan changes affect feature availability and AI query limits

Name         : User
Type         : SQLAlchemy ORM model class
Purpose      : Authentication and authorization model for system users with role-based permissions.
              Contains hashed passwords and tenant associations for secure multi-tenant access.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : SQLAlchemy base classes, relationship to Tenant model
DB/API       : Maps to 'users' table with tenant_id for user isolation
Side effects : Role changes affect permission checks in dependencies.py and route access

Name         : RefreshToken
Type
"""

# app/models/__init__.py — V1.1
from app.models.skill import Skill
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.models.availability import AvailabilityOverride
from app.models.auth import Tenant, User, RefreshToken
# v5-whatsapp — WhatsApp Copilot models (migration 017)
from app.models.whatsapp import PhoneTenantMap, WhatsAppConversation