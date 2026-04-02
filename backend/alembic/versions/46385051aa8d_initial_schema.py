"""
```python
"""
FILE PURPOSE
This is the initial database schema migration file for the ZetaOps Copilot project, created by Alembic
(SQLAlchemy's database migration tool) to establish the foundational database structure. This migration
was introduced in the early development of v4.x and creates all the core tables needed for workforce
and job scheduling functionality. It sits at the base of the migration chain (revision 46385051aa8d,
down_revision None) and defines the fundamental data model that supports employees, jobs, machines,
skills, and their relationships in the scheduling engine.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision ID, creation date, no parent revision)
2. Creates the 'employees' table with personal info, employment details, and availability percentage
3. Creates the 'jobs' table with scheduling details, dates, priority, and profit tracking
4. Creates the 'machines' table with equipment info, type, location, and availability percentage
5. Creates the 'skills' table with skill definitions, categories, and premium/active flags
6. Creates the 'availability_overrides' table to handle temporary availability changes for employees/machines
7. Creates the 'employee_skills' junction table linking employees to their skills with proficiency levels
8. Creates the 'job_assignments' table linking jobs to assigned employees and machines
9. Creates the 'job_skill_requirements' table defining what skills each job needs
10. Creates the 'machine_skill_requirements' table defining what skills are needed to operate each machine
11. Adds primary key indexes on all tables for query performance
12. Defines foreign key relationships with CASCADE/SET NULL delete behaviors
13. Provides downgrade() function to completely reverse all table creations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Creates all initial database tables and indexes needed for the scheduling system. This
               establishes the complete foundational schema that allows the application to store and
               manage employees, jobs, machines, skills, and their complex relationships for workforce
               scheduling operations.
Parameters   : None (Alembic migration signature)
Returns      : None (performs database DDL operations)
Calls        : Alembic op.create_table(), op.create_index(), sa.Column(), sa.ForeignKeyConstraint()
DB/API       : Executes CREATE TABLE and CREATE INDEX statements against the PostgreSQL database
Side effects : Creates 8 tables with indexes and foreign key constraints in the database schema

Name         : downgrade
Type         : function
Purpose      : Completely reverses the upgrade() operation by dropping all tables and indexes in reverse
               dependency order. This allows rolling back to a completely empty database state if needed
               during development or emergency rollbacks.
Parameters   : None (Alembic migration signature)
Returns      : None (performs database DDL operations)
Calls        : Alembic op.drop_table(), op.drop_index()
DB/API       : Executes DROP TABLE and DROP INDEX statements against the PostgreSQL database
Side effects : Removes all tables and data created by upgrade(), leaving database in pre-migration state

WHO CALLS THIS FILE
- backend/alembic/env.py (Alembic environment loads and executes this migration)
- Alembic CLI commands like 'alembic upgrade head' or 'alembic downgrade base'
- Database initialization scripts during deployment or local development setup
- Migration chain execution (this is the first migration, so subsequent migrations depend on it)

IMPORTS EXPLAINED
- from alembic import op: Provides Alembic's operation commands (create_table, drop_table, etc.) for database DDL operations
- import sqlalchemy as sa: Imports SQLAlchemy core for column definitions, data types, and constraint objects used in table creation

INTERN NOTES
- Easiest thing to break: Modifying this file after it's been applied to production - NEVER edit applied migrations, always create new ones
- Non-obvious design decision: No tenant_id columns in this initial schema - multi-tenancy was added in later migrations to avoid breaking existing single-tenant deployments
- Most common mistake: Forgetting that this creates tables WITHOUT the modern tenant_id scoping that current models require - data created here would fail current security filters
- Design principle implemented: This predates the current design principles but establishes the foundation for principle #2 (tenant scoping was retrofitted later)
- What to check if unexpected behavior: Verify this migration was actually applied with 'alembic current' - missing base tables cause cascading SQLAlchemy errors
- Migration chain dependency: All subsequent migrations assume these base tables exist - corrupting this migration breaks the entire database evolution path
```
"""

from alembic import op
import sqlalchemy as sa


revision = '46385051aa8d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('employees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('gender', sa.String(length=20), nullable=True),
    sa.Column('date_of_birth', sa.Date(), nullable=True),
    sa.Column('contact_number', sa.String(length=20), nullable=True),
    sa.Column('department', sa.String(length=100), nullable=True),
    sa.Column('employment_type', sa.String(length=20), nullable=False),
    sa.Column('base_availability_pct', sa.Float(), nullable=False),
    sa.Column('join_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_employees_id'), 'employees', ['id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('customer', sa.String(length=150), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('estimated_hours_per_day', sa.Float(), nullable=False),
    sa.Column('tentative_profit', sa.Float(), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)
    op.create_table('machines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('machine_type', sa.String(length=100), nullable=True),
    sa.Column('base_availability_pct', sa.Float(), nullable=False),
    sa.Column('location_bay', sa.String(length=100), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_machines_id'), 'machines', ['id'], unique=False)
    op.create_table('skills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('is_premium', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)
    op.create_table('availability_overrides',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('machine_id', sa.Integer(), nullable=True),
    sa.Column('date_from', sa.Date(), nullable=False),
    sa.Column('date_to', sa.Date(), nullable=False),
    sa.Column('availability_pct', sa.Float(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_availability_overrides_id'), 'availability_overrides', ['id'], unique=False)
    op.create_table('employee_skills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('skill_level', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_employee_skills_id'), 'employee_skills', ['id'], unique=False)
    op.create_table('job_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('machine_id', sa.Integer(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_assignments_id'), 'job_assignments', ['id'], unique=False)
    op.create_table('job_skill_requirements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('min_skill_level', sa.String(length=20), nullable=False),
    sa.Column('employees_required', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_skill_requirements_id'), 'job_skill_requirements', ['id'], unique=False)
    op.create_table('machine_skill_requirements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('machine_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('min_skill_level', sa.String(length=20), nullable=False),
    sa.Column('employees_required', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_machine_skill_requirements_id'), 'machine_skill_requirements', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_machine_skill_requirements_id'), table_name='machine_skill_requirements')
    op.drop_table('machine_skill_requirements')
    op.drop_index(op.f('ix_job_skill_requirements_id'), table_name='job_skill_requirements')
    op.drop_table('job_skill_requirements')
    op.drop_index(op.f('ix_job_assignments_id'), table_name='job_assignments')
    op.drop_table('job_assignments')
    op.drop_index(op.f('ix_employee_skills_id'), table_name='employee_skills')
    op.drop_table('employee_skills')
    op.drop_index(op.f('ix_availability_overrides_id'), table_name='availability_overrides')
    op.drop_table('availability_overrides')
    op.drop_index(op.f('ix_skills_id'), table_name='skills')
    op.drop_table('skills')
    op.drop_index(op.f('ix_machines_id'), table_name='machines')
    op.drop_table('machines')
    op.drop_index(op.f('ix_jobs_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_employees_id'), table_name='employees')
    op.drop_table('employees')
    # ### end Alembic commands ###
