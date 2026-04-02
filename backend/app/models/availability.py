"""
models/availability.py — V1.1
Added tenant_id to AvailabilityOverride.
"""

from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class AvailabilityOverride(Base):
    __tablename__ = "availability_overrides"

    id               = Column(Integer, primary_key=True, index=True)
    tenant_id        = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)  # V1.1
    employee_id      = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=True)
    machine_id       = Column(Integer, ForeignKey("machines.id", ondelete="CASCADE"), nullable=True)
    date_from        = Column(Date, nullable=False)
    date_to          = Column(Date, nullable=False)
    availability_pct = Column(Float, nullable=False, default=0.0)
    reason           = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="availability_overrides", foreign_keys=[employee_id])
    machine  = relationship("Machine",  back_populates="availability_overrides", foreign_keys=[machine_id])
