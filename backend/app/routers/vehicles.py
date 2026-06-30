from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from decimal import Decimal
from app.database import get_db
from app.core.security import require_vehicle_access
from app import models

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class VehicleCreate(BaseModel):
    registration: str
    make: str
    model: str
    year: Optional[int] = None
    colour: Optional[str] = None
    notes: Optional[str] = None

class ServiceCreate(BaseModel):
    service_date: date
    odometer: Optional[int] = None
    description: str
    cost: Optional[float] = None
    next_service_date: Optional[date] = None
    next_service_km: Optional[int] = None
    workshop: Optional[str] = None

class MaintenanceCreate(BaseModel):
    maintenance_type: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    due_odometer: Optional[int] = None
    notes: Optional[str] = None

class MaintenanceComplete(BaseModel):
    completed_date: date
    completed_odometer: Optional[int] = None

class FuelCreate(BaseModel):
    date: date
    litres: float
    cost_per_litre: Optional[float] = None
    total_cost: Optional[float] = None
    odometer: Optional[int] = None
    filled_by: Optional[str] = None
    notes: Optional[str] = None

class IncidentCreate(BaseModel):
    date: date
    description: str
    reported_by: Optional[str] = None
    action_taken: Optional[str] = None

class FineCreate(BaseModel):
    date: date
    amount: float
    infringement: str
    location: Optional[str] = None
    reference: Optional[str] = None
    driver_id: Optional[int] = None
    notes: Optional[str] = None

class FineStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ── Vehicle CRUD ──────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def create_vehicle(req: VehicleCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_vehicle_access)):
    if db.query(models.Vehicle).filter(models.Vehicle.registration == req.registration.upper()).first():
        raise HTTPException(status_code=409, detail="Registration already exists")
    v = models.Vehicle(
        registration=req.registration.upper(),
        make=req.make, model=req.model, year=req.year,
        colour=req.colour, notes=req.notes,
    )
    db.add(v); db.commit(); db.refresh(v)
    return _vehicle_out(v)

@router.get("/")
def list_vehicles(db: Session = Depends(get_db), current_user=Depends(require_vehicle_access)):
    vehicles = db.query(models.Vehicle).order_by(models.Vehicle.registration).all()
    return [_vehicle_out(v, summary=True) for v in vehicles]

@router.get("/{vehicle_id}")
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db),
                current_user=Depends(require_vehicle_access)):
    v = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not v: raise HTTPException(status_code=404, detail="Vehicle not found")
    return _vehicle_out(v)

@router.patch("/{vehicle_id}")
def update_vehicle(vehicle_id: int, req: VehicleCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_vehicle_access)):
    v = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not v: raise HTTPException(status_code=404, detail="Vehicle not found")
    v.registration = req.registration.upper()
    v.make = req.make; v.model = req.model; v.year = req.year
    v.colour = req.colour; v.notes = req.notes
    db.commit()
    return _vehicle_out(v)

@router.patch("/{vehicle_id}/status")
def update_status(vehicle_id: int, status: str, db: Session = Depends(get_db),
                  current_user=Depends(require_vehicle_access)):
    v = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not v: raise HTTPException(status_code=404, detail="Vehicle not found")
    v.status = models.VehicleStatus(status)
    db.commit()
    return _vehicle_out(v)


# ── Service Records ───────────────────────────────────────────────────────────

@router.post("/{vehicle_id}/service", status_code=201)
def add_service(vehicle_id: int, req: ServiceCreate, db: Session = Depends(get_db),
                current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    s = models.VehicleService(vehicle_id=vehicle_id, **req.dict())
    db.add(s); db.commit(); db.refresh(s)
    return _service_out(s)

@router.get("/{vehicle_id}/service")
def list_service(vehicle_id: int, db: Session = Depends(get_db),
                 current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    records = db.query(models.VehicleService).filter(
        models.VehicleService.vehicle_id == vehicle_id
    ).order_by(models.VehicleService.service_date.desc()).all()
    return [_service_out(s) for s in records]

@router.delete("/{vehicle_id}/service/{record_id}", status_code=204)
def delete_service(vehicle_id: int, record_id: int, db: Session = Depends(get_db),
                   current_user=Depends(require_vehicle_access)):
    s = db.query(models.VehicleService).filter(
        models.VehicleService.id == record_id,
        models.VehicleService.vehicle_id == vehicle_id
    ).first()
    if not s: raise HTTPException(status_code=404, detail="Record not found")
    db.delete(s); db.commit()


# ── Scheduled Maintenance ─────────────────────────────────────────────────────

@router.post("/{vehicle_id}/maintenance", status_code=201)
def add_maintenance(vehicle_id: int, req: MaintenanceCreate, db: Session = Depends(get_db),
                    current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    if req.maintenance_type not in ("oil_change", "tyres", "roadworthy", "full_service", "other"):
        raise HTTPException(status_code=400, detail="Invalid maintenance type")
    m = models.ScheduledMaintenance(
        vehicle_id=vehicle_id,
        maintenance_type=models.MaintenanceType(req.maintenance_type),
        description=req.description, due_date=req.due_date,
        due_odometer=req.due_odometer, notes=req.notes,
    )
    db.add(m); db.commit(); db.refresh(m)
    return _maintenance_out(m)

@router.get("/{vehicle_id}/maintenance")
def list_maintenance(vehicle_id: int, db: Session = Depends(get_db),
                     current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    items = db.query(models.ScheduledMaintenance).filter(
        models.ScheduledMaintenance.vehicle_id == vehicle_id
    ).order_by(models.ScheduledMaintenance.due_date).all()
    return [_maintenance_out(m) for m in items]

@router.patch("/{vehicle_id}/maintenance/{item_id}/complete")
def complete_maintenance(vehicle_id: int, item_id: int, req: MaintenanceComplete,
                         db: Session = Depends(get_db), current_user=Depends(require_vehicle_access)):
    m = db.query(models.ScheduledMaintenance).filter(
        models.ScheduledMaintenance.id == item_id,
        models.ScheduledMaintenance.vehicle_id == vehicle_id
    ).first()
    if not m: raise HTTPException(status_code=404, detail="Item not found")
    m.is_completed = True
    m.completed_date = req.completed_date
    m.completed_odometer = req.completed_odometer
    db.commit()
    return _maintenance_out(m)

@router.delete("/{vehicle_id}/maintenance/{item_id}", status_code=204)
def delete_maintenance(vehicle_id: int, item_id: int, db: Session = Depends(get_db),
                       current_user=Depends(require_vehicle_access)):
    m = db.query(models.ScheduledMaintenance).filter(
        models.ScheduledMaintenance.id == item_id,
        models.ScheduledMaintenance.vehicle_id == vehicle_id
    ).first()
    if not m: raise HTTPException(status_code=404, detail="Item not found")
    db.delete(m); db.commit()


# ── Fuel Logs ─────────────────────────────────────────────────────────────────

@router.post("/{vehicle_id}/fuel", status_code=201)
def add_fuel(vehicle_id: int, req: FuelCreate, db: Session = Depends(get_db),
             current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    f = models.FuelLog(vehicle_id=vehicle_id, **req.dict())
    db.add(f); db.commit(); db.refresh(f)
    return _fuel_out(f)

@router.get("/{vehicle_id}/fuel")
def list_fuel(vehicle_id: int, db: Session = Depends(get_db),
              current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    logs = db.query(models.FuelLog).filter(
        models.FuelLog.vehicle_id == vehicle_id
    ).order_by(models.FuelLog.date.desc()).all()
    return [_fuel_out(f) for f in logs]

@router.delete("/{vehicle_id}/fuel/{log_id}", status_code=204)
def delete_fuel(vehicle_id: int, log_id: int, db: Session = Depends(get_db),
                current_user=Depends(require_vehicle_access)):
    f = db.query(models.FuelLog).filter(
        models.FuelLog.id == log_id, models.FuelLog.vehicle_id == vehicle_id
    ).first()
    if not f: raise HTTPException(status_code=404, detail="Log not found")
    db.delete(f); db.commit()


# ── Incidents ─────────────────────────────────────────────────────────────────

@router.post("/{vehicle_id}/incidents", status_code=201)
def add_incident(vehicle_id: int, req: IncidentCreate, db: Session = Depends(get_db),
                 current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    i = models.VehicleIncident(vehicle_id=vehicle_id, **req.dict())
    db.add(i); db.commit(); db.refresh(i)
    return _incident_out(i)

@router.get("/{vehicle_id}/incidents")
def list_incidents(vehicle_id: int, db: Session = Depends(get_db),
                   current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    items = db.query(models.VehicleIncident).filter(
        models.VehicleIncident.vehicle_id == vehicle_id
    ).order_by(models.VehicleIncident.date.desc()).all()
    return [_incident_out(i) for i in items]

@router.delete("/{vehicle_id}/incidents/{item_id}", status_code=204)
def delete_incident(vehicle_id: int, item_id: int, db: Session = Depends(get_db),
                    current_user=Depends(require_vehicle_access)):
    i = db.query(models.VehicleIncident).filter(
        models.VehicleIncident.id == item_id,
        models.VehicleIncident.vehicle_id == vehicle_id
    ).first()
    if not i: raise HTTPException(status_code=404, detail="Incident not found")
    db.delete(i); db.commit()


# ── Traffic Fines ─────────────────────────────────────────────────────────────

@router.post("/{vehicle_id}/fines", status_code=201)
def add_fine(vehicle_id: int, req: FineCreate, db: Session = Depends(get_db),
             current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    f = models.TrafficFine(vehicle_id=vehicle_id, **req.dict())
    db.add(f); db.commit(); db.refresh(f)
    return _fine_out(f)

@router.get("/{vehicle_id}/fines")
def list_fines(vehicle_id: int, db: Session = Depends(get_db),
               current_user=Depends(require_vehicle_access)):
    _check_vehicle(vehicle_id, db)
    fines = db.query(models.TrafficFine).filter(
        models.TrafficFine.vehicle_id == vehicle_id
    ).order_by(models.TrafficFine.date.desc()).all()
    return [_fine_out(f) for f in fines]

@router.patch("/{vehicle_id}/fines/{fine_id}")
def update_fine_status(vehicle_id: int, fine_id: int, req: FineStatusUpdate,
                       db: Session = Depends(get_db), current_user=Depends(require_vehicle_access)):
    f = db.query(models.TrafficFine).filter(
        models.TrafficFine.id == fine_id,
        models.TrafficFine.vehicle_id == vehicle_id
    ).first()
    if not f: raise HTTPException(status_code=404, detail="Fine not found")
    f.status = models.FineStatus(req.status)
    if req.notes: f.notes = req.notes
    db.commit()
    return _fine_out(f)

@router.delete("/{vehicle_id}/fines/{fine_id}", status_code=204)
def delete_fine(vehicle_id: int, fine_id: int, db: Session = Depends(get_db),
                current_user=Depends(require_vehicle_access)):
    f = db.query(models.TrafficFine).filter(
        models.TrafficFine.id == fine_id,
        models.TrafficFine.vehicle_id == vehicle_id
    ).first()
    if not f: raise HTTPException(status_code=404, detail="Fine not found")
    db.delete(f); db.commit()


# ── Fleet alerts (overdue maintenance) ───────────────────────────────────────

@router.get("/alerts/overdue")
def fleet_alerts(db: Session = Depends(get_db), current_user=Depends(require_vehicle_access)):
    today = date.today()
    overdue = db.query(models.ScheduledMaintenance).filter(
        models.ScheduledMaintenance.is_completed == False,
        models.ScheduledMaintenance.due_date < today,
        models.ScheduledMaintenance.due_date != None,
    ).all()
    return [{"vehicle_id": m.vehicle_id, "maintenance_type": m.maintenance_type,
             "due_date": str(m.due_date), "description": m.description} for m in overdue]


# ── Output helpers ────────────────────────────────────────────────────────────

def _check_vehicle(vehicle_id, db):
    if not db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first():
        raise HTTPException(status_code=404, detail="Vehicle not found")

def _vehicle_out(v, summary=False):
    out = {
        "id": v.id, "registration": v.registration, "make": v.make,
        "model": v.model, "year": v.year, "colour": v.colour,
        "status": v.status, "notes": v.notes,
    }
    if not summary:
        today = date.today()
        overdue_maintenance = [m for m in v.maintenance
                               if not m.is_completed and m.due_date and m.due_date < today]
        out["overdue_maintenance_count"] = len(overdue_maintenance)
        outstanding_fines = [f for f in v.fines if f.status == models.FineStatus.outstanding]
        out["outstanding_fines_count"] = len(outstanding_fines)
        out["outstanding_fines_total"] = float(sum(f.amount for f in outstanding_fines))
    return out

def _service_out(s):
    return {"id": s.id, "service_date": str(s.service_date), "odometer": s.odometer,
            "description": s.description, "cost": float(s.cost) if s.cost else None,
            "next_service_date": str(s.next_service_date) if s.next_service_date else None,
            "next_service_km": s.next_service_km, "workshop": s.workshop}

def _maintenance_out(m):
    return {"id": m.id, "maintenance_type": m.maintenance_type, "description": m.description,
            "due_date": str(m.due_date) if m.due_date else None, "due_odometer": m.due_odometer,
            "is_completed": m.is_completed,
            "completed_date": str(m.completed_date) if m.completed_date else None,
            "completed_odometer": m.completed_odometer, "notes": m.notes}

def _fuel_out(f):
    return {"id": f.id, "date": str(f.date), "litres": f.litres,
            "cost_per_litre": float(f.cost_per_litre) if f.cost_per_litre else None,
            "total_cost": float(f.total_cost) if f.total_cost else None,
            "odometer": f.odometer, "filled_by": f.filled_by, "notes": f.notes}

def _incident_out(i):
    return {"id": i.id, "date": str(i.date), "description": i.description,
            "reported_by": i.reported_by, "action_taken": i.action_taken}

def _fine_out(f):
    return {"id": f.id, "date": str(f.date), "amount": float(f.amount),
            "infringement": f.infringement, "location": f.location,
            "reference": f.reference, "status": f.status,
            "driver_id": f.driver_id,
            "driver_name": f.driver.name if f.driver else None,
            "notes": f.notes}
