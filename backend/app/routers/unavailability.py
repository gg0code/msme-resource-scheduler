# app/models/unavailability.py
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class EmployeeLeave(Base):
    __tablename__ = "employee_leaves"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    reason      = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class MachineDowntime(Base):
    __tablename__ = "machine_downtimes"

    id         = Column(Integer, primary_key=True, index=True)
    tenant_id  = Column(Integer, nullable=False, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    reason     = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
