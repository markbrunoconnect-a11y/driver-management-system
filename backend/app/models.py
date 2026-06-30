"""
Driver Management System — database models.
All tables prefixed dms_ to avoid conflicts with other apps on the same database.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date, Time,
    ForeignKey, Enum as SAEnum, Numeric
)
from sqlalchemy.orm import relationship
from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin      = "admin"
    dispatcher = "dispatcher"
    driver     = "driver"

class ActionType(str, enum.Enum):
    delivery   = "delivery"
    collection = "collection"
    task       = "task"
    other      = "other"

class TicketStatus(str, enum.Enum):
    unassigned  = "unassigned"
    assigned    = "assigned"
    completed   = "completed"
    overdue     = "overdue"

class MaintenanceType(str, enum.Enum):
    oil        = "oil_change"
    tyres      = "tyres"
    roadworthy = "roadworthy"
    service    = "full_service"
    other      = "other"

class FineStatus(str, enum.Enum):
    outstanding = "outstanding"
    paid        = "paid"
    disputed    = "disputed"

class VehicleStatus(str, enum.Enum):
    active      = "active"
    maintenance = "in_maintenance"
    retired     = "retired"


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "dms_users"
    id                = Column(Integer, primary_key=True)
    name              = Column(String(120), nullable=False)
    email             = Column(String(200), unique=True, nullable=False)
    password_hash     = Column(String(200), nullable=False)
    role              = Column(SAEnum(UserRole), nullable=False, default=UserRole.driver)
    is_vehicle_manager = Column(Boolean, default=False)
    is_active         = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=datetime.utcnow)

    assignments = relationship("TicketAssignment", back_populates="driver", foreign_keys="TicketAssignment.driver_id")


# ── Action Tickets ─────────────────────────────────────────────────────────────

class ActionTicket(Base):
    __tablename__ = "dms_action_tickets"
    id             = Column(Integer, primary_key=True)
    ticket_number  = Column(String(20), unique=True, nullable=False)
    action_type    = Column(SAEnum(ActionType), nullable=False)
    description    = Column(Text, nullable=False)
    location       = Column(String(300), nullable=False)
    due_date       = Column(Date, nullable=False)
    due_time       = Column(Time, nullable=True)
    notes          = Column(Text, nullable=True)
    status         = Column(SAEnum(TicketStatus), default=TicketStatus.unassigned, nullable=False)
    created_by_id  = Column(Integer, ForeignKey("dms_users.id"), nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)

    created_by  = relationship("User", foreign_keys=[created_by_id])
    assignment  = relationship("TicketAssignment", back_populates="ticket", uselist=False, cascade="all, delete-orphan")


class TicketAssignment(Base):
    __tablename__ = "dms_ticket_assignments"
    id               = Column(Integer, primary_key=True)
    ticket_id        = Column(Integer, ForeignKey("dms_action_tickets.id"), nullable=False)
    driver_id        = Column(Integer, ForeignKey("dms_users.id"), nullable=False)
    assigned_date    = Column(Date, nullable=False)
    assigned_time    = Column(Time, nullable=True)
    assigned_by_id   = Column(Integer, ForeignKey("dms_users.id"), nullable=False)
    assigned_at      = Column(DateTime, default=datetime.utcnow)
    completed_at     = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    completion_notes = Column(Text, nullable=True)

    ticket      = relationship("ActionTicket", back_populates="assignment")
    driver      = relationship("User", back_populates="assignments", foreign_keys=[driver_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


# ── Vehicles ──────────────────────────────────────────────────────────────────

class Vehicle(Base):
    __tablename__ = "dms_vehicles"
    id               = Column(Integer, primary_key=True)
    registration     = Column(String(20), unique=True, nullable=False)
    make             = Column(String(100), nullable=False)
    model            = Column(String(100), nullable=False)
    year             = Column(Integer, nullable=True)
    colour           = Column(String(60), nullable=True)
    status           = Column(SAEnum(VehicleStatus), default=VehicleStatus.active)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    service_records  = relationship("VehicleService",      back_populates="vehicle", cascade="all, delete-orphan")
    maintenance      = relationship("ScheduledMaintenance", back_populates="vehicle", cascade="all, delete-orphan")
    fuel_logs        = relationship("FuelLog",             back_populates="vehicle", cascade="all, delete-orphan")
    incidents        = relationship("VehicleIncident",     back_populates="vehicle", cascade="all, delete-orphan")
    fines            = relationship("TrafficFine",         back_populates="vehicle", cascade="all, delete-orphan")


class VehicleService(Base):
    __tablename__ = "dms_vehicle_service"
    id               = Column(Integer, primary_key=True)
    vehicle_id       = Column(Integer, ForeignKey("dms_vehicles.id"), nullable=False)
    service_date     = Column(Date, nullable=False)
    odometer         = Column(Integer, nullable=True)
    description      = Column(Text, nullable=False)
    cost             = Column(Numeric(10, 2), nullable=True)
    next_service_date = Column(Date, nullable=True)
    next_service_km  = Column(Integer, nullable=True)
    workshop         = Column(String(200), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="service_records")


class ScheduledMaintenance(Base):
    __tablename__ = "dms_scheduled_maintenance"
    id                 = Column(Integer, primary_key=True)
    vehicle_id         = Column(Integer, ForeignKey("dms_vehicles.id"), nullable=False)
    maintenance_type   = Column(SAEnum(MaintenanceType), nullable=False)
    description        = Column(String(200), nullable=True)
    due_date           = Column(Date, nullable=True)
    due_odometer       = Column(Integer, nullable=True)
    is_completed       = Column(Boolean, default=False)
    completed_date     = Column(Date, nullable=True)
    completed_odometer = Column(Integer, nullable=True)
    notes              = Column(Text, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="maintenance")


class FuelLog(Base):
    __tablename__ = "dms_fuel_logs"
    id            = Column(Integer, primary_key=True)
    vehicle_id    = Column(Integer, ForeignKey("dms_vehicles.id"), nullable=False)
    date          = Column(Date, nullable=False)
    litres        = Column(Float, nullable=False)
    cost_per_litre = Column(Numeric(8, 3), nullable=True)
    total_cost    = Column(Numeric(10, 2), nullable=True)
    odometer      = Column(Integer, nullable=True)
    filled_by     = Column(String(120), nullable=True)
    notes         = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="fuel_logs")


class VehicleIncident(Base):
    __tablename__ = "dms_vehicle_incidents"
    id           = Column(Integer, primary_key=True)
    vehicle_id   = Column(Integer, ForeignKey("dms_vehicles.id"), nullable=False)
    date         = Column(Date, nullable=False)
    description  = Column(Text, nullable=False)
    reported_by  = Column(String(120), nullable=True)
    action_taken = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="incidents")


class TrafficFine(Base):
    __tablename__ = "dms_traffic_fines"
    id            = Column(Integer, primary_key=True)
    vehicle_id    = Column(Integer, ForeignKey("dms_vehicles.id"), nullable=False)
    driver_id     = Column(Integer, ForeignKey("dms_users.id"), nullable=True)
    date          = Column(Date, nullable=False)
    amount        = Column(Numeric(10, 2), nullable=False)
    infringement  = Column(String(300), nullable=False)
    location      = Column(String(200), nullable=True)
    reference     = Column(String(100), nullable=True)
    status        = Column(SAEnum(FineStatus), default=FineStatus.outstanding)
    notes         = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="fines")
    driver  = relationship("User", foreign_keys=[driver_id])
