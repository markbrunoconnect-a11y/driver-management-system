from datetime import date, datetime, time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.core.security import get_current_user, require_dispatcher_or_admin
from app import models

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    action_type: str
    description: str
    location: str
    due_date: date
    due_time: Optional[str] = None
    notes: Optional[str] = None


class TicketAssignRequest(BaseModel):
    driver_id: int
    assigned_date: date
    assigned_time: Optional[str] = None


class CompleteRequest(BaseModel):
    completion_notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_ticket_number(db: Session) -> str:
    year = datetime.utcnow().year
    count = db.query(models.ActionTicket).filter(
        models.ActionTicket.ticket_number.like(f"DMS-{year}-%")
    ).count()
    return f"DMS-{year}-{count + 1:04d}"


def _ticket_out(t, include_assignment=True):
    out = {
        "id": t.id,
        "ticket_number": t.ticket_number,
        "action_type": t.action_type,
        "description": t.description,
        "location": t.location,
        "due_date": str(t.due_date),
        "due_time": str(t.due_time) if t.due_time else None,
        "notes": t.notes,
        "status": t.status,
        "created_by": t.created_by.name if t.created_by else None,
        "created_at": str(t.created_at),
    }
    if include_assignment and t.assignment:
        a = t.assignment
        out["assignment"] = {
            "driver_id": a.driver_id,
            "driver_name": a.driver.name if a.driver else None,
            "assigned_date": str(a.assigned_date),
            "assigned_time": str(a.assigned_time) if a.assigned_time else None,
            "assigned_by": a.assigned_by.name if a.assigned_by else None,
            "assigned_at": str(a.assigned_at),
            "completed_at": str(a.completed_at) if a.completed_at else None,
            "duration_minutes": a.duration_minutes,
            "completion_notes": a.completion_notes,
        }
    else:
        out["assignment"] = None
    return out


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def create_ticket(req: TicketCreate, db: Session = Depends(get_db),
                  current_user=Depends(require_dispatcher_or_admin)):
    if req.action_type not in ("delivery", "collection", "task", "other"):
        raise HTTPException(status_code=400, detail="Invalid action type")
    due_time = None
    if req.due_time:
        h, m = req.due_time.split(":")[:2]
        due_time = time(int(h), int(m))
    ticket = models.ActionTicket(
        ticket_number=_next_ticket_number(db),
        action_type=models.ActionType(req.action_type),
        description=req.description,
        location=req.location,
        due_date=req.due_date,
        due_time=due_time,
        notes=req.notes,
        created_by_id=current_user.id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return _ticket_out(ticket)


@router.get("/")
def list_tickets(
    status: Optional[str] = Query(None),
    driver_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Drivers only see their own tickets
    if current_user.role == "driver":
        q = db.query(models.ActionTicket).join(
            models.TicketAssignment,
            models.ActionTicket.id == models.TicketAssignment.ticket_id
        ).filter(models.TicketAssignment.driver_id == current_user.id)
    else:
        q = db.query(models.ActionTicket)
        if driver_id:
            q = q.join(models.TicketAssignment).filter(
                models.TicketAssignment.driver_id == driver_id)

    # Auto-flag overdue
    today = date.today()
    tickets = q.order_by(models.ActionTicket.due_date).all()
    for t in tickets:
        if t.status == models.TicketStatus.assigned and t.due_date < today:
            t.status = models.TicketStatus.overdue
    db.commit()

    if status:
        tickets = [t for t in tickets if t.status == status]

    return [_ticket_out(t) for t in tickets]


# ── Calendar endpoint ─────────────────────────────────────────────────────────
# NOTE: must be before /{ticket_id} to avoid FastAPI treating "calendar" as an int

@router.get("/calendar/week")
def calendar_week(week_start: date = Query(...), db: Session = Depends(get_db),
                  current_user=Depends(require_dispatcher_or_admin)):
    """Return all assignments for the week starting week_start (Mon–Sun)."""
    from datetime import timedelta
    week_end = week_start + timedelta(days=6)
    assignments = db.query(models.TicketAssignment).filter(
        models.TicketAssignment.assigned_date >= week_start,
        models.TicketAssignment.assigned_date <= week_end,
    ).all()
    drivers = db.query(models.User).filter(
        models.User.role == models.UserRole.driver,
        models.User.is_active == True
    ).order_by(models.User.name).all()

    result = {}
    for d in drivers:
        result[d.id] = {
            "driver_id": d.id,
            "driver_name": d.name,
            "days": {}
        }
    for a in assignments:
        did = a.driver_id
        if did not in result:
            continue
        day = str(a.assigned_date)
        if day not in result[did]["days"]:
            result[did]["days"][day] = []
        result[did]["days"][day].append({
            "ticket_id": a.ticket_id,
            "ticket_number": a.ticket.ticket_number,
            "action_type": a.ticket.action_type,
            "description": a.ticket.description,
            "location": a.ticket.location,
            "due_date": str(a.ticket.due_date),
            "assigned_time": str(a.assigned_time) if a.assigned_time else None,
            "status": a.ticket.status,
        })
    return list(result.values())


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    t = db.query(models.ActionTicket).filter(models.ActionTicket.id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Drivers can only see their own
    if current_user.role == "driver":
        if not t.assignment or t.assignment.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    return _ticket_out(t)


@router.patch("/{ticket_id}")
def update_ticket(ticket_id: int, req: TicketCreate, db: Session = Depends(get_db),
                  current_user=Depends(require_dispatcher_or_admin)):
    t = db.query(models.ActionTicket).filter(models.ActionTicket.id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if t.status != models.TicketStatus.unassigned:
        raise HTTPException(status_code=400, detail="Can only edit unassigned tickets")
    t.action_type = models.ActionType(req.action_type)
    t.description = req.description
    t.location = req.location
    t.due_date = req.due_date
    t.notes = req.notes
    if req.due_time:
        h, m = req.due_time.split(":")[:2]
        t.due_time = time(int(h), int(m))
    db.commit()
    return _ticket_out(t)


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int, db: Session = Depends(get_db),
                  current_user=Depends(require_dispatcher_or_admin)):
    t = db.query(models.ActionTicket).filter(models.ActionTicket.id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if t.status not in (models.TicketStatus.unassigned,):
        raise HTTPException(status_code=400, detail="Can only delete unassigned tickets")
    db.delete(t)
    db.commit()


@router.post("/{ticket_id}/assign")
def assign_ticket(ticket_id: int, req: TicketAssignRequest,
                  db: Session = Depends(get_db),
                  current_user=Depends(require_dispatcher_or_admin)):
    t = db.query(models.ActionTicket).filter(models.ActionTicket.id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if t.status == models.TicketStatus.completed:
        raise HTTPException(status_code=400, detail="Cannot reassign a completed ticket")
    driver = db.query(models.User).filter(
        models.User.id == req.driver_id,
        models.User.role == models.UserRole.driver,
        models.User.is_active == True
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    assigned_time = None
    if req.assigned_time:
        h, m = req.assigned_time.split(":")[:2]
        assigned_time = time(int(h), int(m))

    # Remove existing assignment if reassigning
    if t.assignment:
        db.delete(t.assignment)

    assignment = models.TicketAssignment(
        ticket_id=ticket_id,
        driver_id=req.driver_id,
        assigned_date=req.assigned_date,
        assigned_time=assigned_time,
        assigned_by_id=current_user.id,
        assigned_at=datetime.utcnow(),
    )
    db.add(assignment)
    t.status = models.TicketStatus.assigned
    db.commit()
    db.refresh(t)
    return _ticket_out(t)


@router.post("/{ticket_id}/complete")
def complete_ticket(ticket_id: int, req: CompleteRequest,
                    db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    t = db.query(models.ActionTicket).filter(models.ActionTicket.id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not t.assignment:
        raise HTTPException(status_code=400, detail="Ticket not assigned")
    # Driver can only complete their own
    if current_user.role == "driver" and t.assignment.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")
    if t.status == models.TicketStatus.completed:
        raise HTTPException(status_code=400, detail="Already completed")

    now = datetime.utcnow()
    duration = int((now - t.assignment.assigned_at).total_seconds() / 60)
    t.assignment.completed_at = now
    t.assignment.duration_minutes = duration
    t.assignment.completion_notes = req.completion_notes
    t.status = models.TicketStatus.completed
    db.commit()
    return _ticket_out(t)

