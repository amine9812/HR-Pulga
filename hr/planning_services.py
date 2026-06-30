from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from accounts.models import Role

from .models import DemandeConge, Departement, Employe, PlanningShift, Service, StatutDemande
from .services import audit_profile, notify_employee


STATUS_ALIASES = {
    "planned": "brouillon",
    "draft": "brouillon",
    "confirmed": "publie",
    "published": "publie",
    "open": "ouvert",
    "modified": "publie",
    "cancelled": "annule",
    "canceled": "annule",
    "done": "termine",
}


def can_manage_planning(user_profile):
    return bool(user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH})


def require_planning_manager(user_profile):
    if not can_manage_planning(user_profile):
        raise PermissionDenied("Vous n'etes pas autorise a modifier le planning.")


def planning_queryset_for_profile(user_profile):
    qs = PlanningShift.objects.select_related("employe", "departement", "service")
    if not user_profile or not user_profile.employe:
        return qs.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return qs
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return qs.filter(Q(employe=user_profile.employe) | Q(employe__responsable=user_profile.employe) | Q(employe__isnull=True))
    return qs.filter(Q(employe=user_profile.employe) | Q(employe__isnull=True, statut="ouvert"))


def employees_for_profile(user_profile):
    qs = Employe.objects.filter(actif=True).select_related("departement", "service", "poste")
    if not user_profile or not user_profile.employe:
        return qs.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return qs
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return qs.filter(Q(pk=user_profile.employe_id) | Q(responsable=user_profile.employe))
    return qs.filter(pk=user_profile.employe_id)


def normalize_status(value, fallback="brouillon"):
    value = (value or fallback or "").strip()
    value = STATUS_ALIASES.get(value.lower(), value)
    if value not in dict(PlanningShift.STATUTS):
        raise ValidationError({"statut": "Statut de shift invalide."})
    return value


def parse_dt(value, field_name):
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
    if not parsed:
        raise ValidationError({field_name: "Format date/heure invalide."})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def parse_day(value, field_name):
    if not value:
        return None
    if hasattr(value, "year") and not hasattr(value, "hour"):
        return value
    parsed = parse_date(str(value))
    if not parsed:
        raise ValidationError({field_name: "Format date invalide."})
    return parsed


def serialize_employee(employee):
    return {
        "id": employee.pk,
        "name": employee.nom_complet,
        "department": employee.departement.libelle if employee.departement else "",
        "service": employee.service.libelle if employee.service else "",
        "role": employee.poste.libelle if employee.poste else "",
    }


def serialize_shift(shift):
    pointage = shift.pointages.order_by("-date", "-heure_entree").first() if shift.pk else None
    return {
        "id": shift.pk,
        "title": shift.titre,
        "employee_id": shift.employe_id,
        "employee": shift.employe.nom_complet if shift.employe else "Shift ouvert",
        "department_id": shift.departement_id,
        "department": shift.departement.libelle if shift.departement else "",
        "service_id": shift.service_id,
        "service": shift.service.libelle if shift.service else "",
        "location": shift.lieu,
        "starts_at": shift.date_debut.isoformat(),
        "ends_at": shift.date_fin.isoformat() if shift.date_fin else "",
        "effective_end_time": shift.effective_end_time.isoformat() if shift.effective_end_time else "",
        "plan_type": shift.plan_type,
        "plan_type_label": shift.get_plan_type_display(),
        "recurrence_rule": shift.recurrence_rule,
        "recurrence_label": shift.get_recurrence_rule_display(),
        "permanent_end_time": shift.permanent_end_time.isoformat() if shift.permanent_end_time else "",
        "break_starts_at": shift.pause_debut.isoformat() if shift.pause_debut else "",
        "break_minutes": shift.pause_minutes,
        "duration_hours": shift.duree_heures,
        "status": shift.statut,
        "status_label": shift.get_statut_display(),
        "notes": shift.notes,
        "pointage_status": pointage.get_statut_display() if pointage else "Aucun pointage lie",
        "pointage_hours": float(pointage.total_heures or 0) if pointage else 0,
        "pointage_comment": pointage.commentaire if pointage else "No planned attendance record has been completed for this shift.",
    }


def shift_occurs_on(shift, day):
    if shift.plan_type == "normal":
        return bool(shift.date_fin and shift.date_debut.date() <= day <= shift.date_fin.date())
    if not shift.date_debut or shift.date_debut.date() > day:
        return False
    if shift.date_fin and shift.date_fin.date() < day:
        return False
    delta_days = (day - shift.date_debut.date()).days
    if shift.recurrence_rule == "daily":
        return True
    if shift.recurrence_rule == "weekdays":
        return day.weekday() < 5
    if shift.recurrence_rule == "weekly":
        return shift.date_debut.weekday() == day.weekday()
    if shift.recurrence_rule == "biweekly":
        return shift.date_debut.weekday() == day.weekday() and delta_days % 14 == 0
    if shift.recurrence_rule == "monthly":
        return shift.date_debut.day == day.day
    return False


def pointage_breakdown(pointage):
    shift = pointage.shift
    planned_start = planned_end = None
    expected_hours = 0
    warning = ""
    if shift:
        planned_start = timezone.make_aware(timezone.datetime.combine(pointage.date, timezone.localtime(shift.date_debut).time()))
        end_time = shift.effective_end_time
        if end_time:
            planned_end = timezone.make_aware(timezone.datetime.combine(pointage.date, end_time))
            if planned_end <= planned_start:
                planned_end += timezone.timedelta(days=1)
            expected_hours = max(0, round((planned_end - planned_start).total_seconds() / 3600 - (shift.pause_minutes / 60), 2))
    else:
        warning = "No planned shift found for this date."
    late_minutes = max(0, int((pointage.heure_entree - planned_start).total_seconds() / 60)) if pointage.heure_entree and planned_start else 0
    early_minutes = max(0, int((planned_end - pointage.heure_sortie).total_seconds() / 60)) if pointage.heure_sortie and planned_end else 0
    worked_hours = float(pointage.total_heures or 0)
    missing_hours = max(0, round(expected_hours - worked_hours, 2)) if shift else 0
    overtime_hours = max(0, round(worked_hours - expected_hours, 2)) if shift else 0
    return {
        "pointage": pointage,
        "planned_start": planned_start,
        "planned_end": planned_end,
        "expected_hours": expected_hours,
        "worked_hours": worked_hours,
        "missing_hours": missing_hours,
        "overtime_hours": overtime_hours,
        "late_minutes": late_minutes,
        "early_minutes": early_minutes,
        "warning": warning,
    }


def shift_payload(payload, instance=None):
    data = payload.copy()
    employee_present = any(key in data for key in ("employee_id", "employe_id", "employe"))
    departement_present = any(key in data for key in ("department_id", "departement_id", "departement"))
    service_present = any(key in data for key in ("service_id", "service"))
    pause_debut_present = any(key in data for key in ("break_starts_at", "pause_debut"))
    plan_type = data.get("plan_type") or getattr(instance, "plan_type", "normal")
    recurrence_rule = data.get("recurrence_rule") or getattr(instance, "recurrence_rule", "none")
    permanent_end_time_raw = data.get("permanent_end_time")
    permanent_end_time = getattr(instance, "permanent_end_time", None)
    if permanent_end_time_raw is not None:
        permanent_end_time = parse_time(str(permanent_end_time_raw)) if permanent_end_time_raw else None
        if permanent_end_time_raw and not permanent_end_time:
            raise ValidationError({"permanent_end_time": "Format heure invalide."})
    employee_id = data.get("employee_id") or data.get("employe_id") or data.get("employe")
    departement_id = data.get("department_id") or data.get("departement_id") or data.get("departement")
    service_id = data.get("service_id") or data.get("service")
    employee = getattr(instance, "employe", None)
    departement = getattr(instance, "departement", None)
    service = getattr(instance, "service", None)
    if employee_present:
        employee = Employe.objects.filter(pk=employee_id, actif=True).first() if employee_id else None
        if employee_id and not employee:
            raise ValidationError({"employe": "Employe introuvable ou inactif."})
    if departement_present:
        departement = Departement.objects.filter(pk=departement_id).first() if departement_id else None
        if departement_id and not departement:
            raise ValidationError({"departement": "Departement introuvable."})
    if service_present:
        service = Service.objects.filter(pk=service_id).first() if service_id else None
        if service_id and not service:
            raise ValidationError({"service": "Service introuvable."})
    pause_debut = parse_dt(data.get("break_starts_at") or data.get("pause_debut"), "pause_debut") if pause_debut_present else getattr(instance, "pause_debut", None)
    return {
        "titre": (data.get("title") or data.get("titre") or getattr(instance, "titre", "Shift")).strip(),
        "employe": employee,
        "departement": departement,
        "service": service,
        "lieu": (data.get("location") or data.get("lieu") or getattr(instance, "lieu", "Casablanca")).strip() or "Casablanca",
        "date_debut": parse_dt(data.get("starts_at") or data.get("date_debut"), "date_debut") or getattr(instance, "date_debut", None),
        "date_fin": parse_dt(data.get("ends_at") or data.get("date_fin"), "date_fin") or getattr(instance, "date_fin", None),
        "plan_type": plan_type,
        "recurrence_rule": recurrence_rule,
        "permanent_end_time": permanent_end_time,
        "pause_minutes": int(data.get("break_minutes") or data.get("pause_minutes") or getattr(instance, "pause_minutes", 0) or 0),
        "pause_debut": pause_debut,
        "statut": normalize_status(data.get("status") or data.get("statut"), getattr(instance, "statut", "brouillon")),
        "notes": (data.get("notes") if data.get("notes") is not None else getattr(instance, "notes", "")) or "",
    }


def employees_for_scope(payload):
    scope = payload.get("scope") or "employees"
    employees = Employe.objects.filter(actif=True).select_related("departement", "service")
    if scope == "company":
        return employees
    if scope == "departement":
        return employees.filter(departement_id=payload.get("department_id") or payload.get("departement_id") or payload.get("departement"))
    if scope == "service":
        return employees.filter(service_id=payload.get("service_id") or payload.get("service"))
    ids = payload.get("employee_ids") or payload.get("employes") or payload.get("employees") or []
    if isinstance(ids, str):
        ids = [value for value in ids.split(",") if value]
    return employees.filter(pk__in=ids)


@transaction.atomic
def create_shift(user_profile, payload):
    require_planning_manager(user_profile)
    attrs = shift_payload(payload)
    shift = PlanningShift(**attrs, cree_par=user_profile)
    shift.full_clean()
    shift.save()
    audit_profile(user_profile, "CREATION_SHIFT", f"Shift cree: {shift}", "PlanningShift", shift.pk)
    if shift.employe and shift.statut in {"publie", "ouvert"}:
        notify_employee(shift.employe, f"Nouveau shift planifie: {shift.titre}", "/planning")
    return shift


@transaction.atomic
def update_shift(user_profile, shift, payload):
    require_planning_manager(user_profile)
    shift = PlanningShift.objects.select_for_update().get(pk=shift.pk)
    for field, value in shift_payload(payload, instance=shift).items():
        setattr(shift, field, value)
    shift.full_clean()
    shift.save()
    audit_profile(user_profile, "MODIFICATION_SHIFT", f"Shift modifie: {shift}", "PlanningShift", shift.pk)
    return shift


@transaction.atomic
def change_shift_status(user_profile, shift, status):
    require_planning_manager(user_profile)
    shift = PlanningShift.objects.select_for_update().get(pk=shift.pk)
    shift.statut = normalize_status(status, shift.statut)
    shift.full_clean()
    shift.save(update_fields=["statut", "updated_at"])
    audit_profile(user_profile, "STATUT_SHIFT", f"{shift} -> {shift.statut}", "PlanningShift", shift.pk)
    if shift.employe and shift.statut in {"publie", "annule"}:
        notify_employee(shift.employe, f"Votre planning a ete mis a jour: {shift.titre}", "/planning")
    return shift


@transaction.atomic
def move_shift(user_profile, shift, payload):
    require_planning_manager(user_profile)
    shift = PlanningShift.objects.select_for_update().get(pk=shift.pk)
    old_start = shift.date_debut
    old_duration = shift.date_fin - shift.date_debut
    starts_at = parse_dt(payload.get("starts_at") or payload.get("date_debut"), "date_debut")
    if not starts_at:
        raise ValidationError({"date_debut": "Le nouveau debut est obligatoire."})
    employee_id = payload.get("employee_id") or payload.get("employe_id") or payload.get("employe")
    if employee_id:
        employee = Employe.objects.filter(pk=employee_id, actif=True).first()
        if not employee:
            raise ValidationError({"employe": "Employe introuvable ou inactif."})
        shift.employe = employee
        shift.departement = shift.employe.departement or shift.departement
        shift.service = shift.employe.service or shift.service
    shift.date_debut = starts_at
    shift.date_fin = parse_dt(payload.get("ends_at") or payload.get("date_fin"), "date_fin") or starts_at + old_duration
    if shift.pause_debut:
        shift.pause_debut = starts_at + (shift.pause_debut - old_start)
    shift.full_clean()
    shift.save()
    audit_profile(user_profile, "DEPLACEMENT_SHIFT", f"Shift deplace: {shift}", "PlanningShift", shift.pk)
    return shift


@transaction.atomic
def resize_shift(user_profile, shift, payload):
    require_planning_manager(user_profile)
    shift = PlanningShift.objects.select_for_update().get(pk=shift.pk)
    starts_at = parse_dt(payload.get("starts_at") or payload.get("date_debut"), "date_debut")
    ends_at = parse_dt(payload.get("ends_at") or payload.get("date_fin"), "date_fin")
    if starts_at:
        shift.date_debut = starts_at
    if not ends_at:
        raise ValidationError({"date_fin": "La nouvelle fin est obligatoire."})
    shift.date_fin = ends_at
    shift.full_clean()
    shift.save()
    audit_profile(user_profile, "REDIMENSION_SHIFT", f"Shift redimensionne: {shift}", "PlanningShift", shift.pk)
    return shift


def bulk_create_shifts(user_profile, payload):
    require_planning_manager(user_profile)
    created = []
    skipped = []
    for employee in employees_for_scope(payload):
        item = payload.copy()
        item["employee_id"] = employee.pk
        item.setdefault("department_id", employee.departement_id)
        item.setdefault("service_id", employee.service_id)
        try:
            created.append(create_shift(user_profile, item))
        except ValidationError as exc:
            skipped.append({"employee": employee.nom_complet, "errors": exc.message_dict if hasattr(exc, "message_dict") else exc.messages})
    return {"created": [serialize_shift(shift) for shift in created], "skipped": skipped}


def copy_planning(user_profile, payload):
    require_planning_manager(user_profile)
    source_start = parse_day(payload.get("source_start"), "source_start")
    source_end = parse_day(payload.get("source_end"), "source_end")
    target_start = parse_day(payload.get("target_start"), "target_start")
    if not (source_start and source_end and target_start):
        raise ValidationError("Les dates source et cible sont obligatoires.")
    delta = target_start - source_start
    shifts = planning_queryset_for_profile(user_profile).filter(plan_type="normal", date_debut__date__gte=source_start, date_debut__date__lte=source_end).exclude(statut="annule")
    created = []
    skipped = []
    for shift in shifts:
        item = serialize_shift(shift)
        item.update(
            {
                "starts_at": (shift.date_debut + delta).isoformat(),
                "ends_at": (shift.date_fin + delta).isoformat(),
                "break_starts_at": (shift.pause_debut + delta).isoformat() if shift.pause_debut else "",
                "status": "brouillon" if payload.get("as_draft", True) else shift.statut,
            }
        )
        try:
            created.append(create_shift(user_profile, item))
        except ValidationError as exc:
            skipped.append({"shift": shift.pk, "errors": exc.message_dict if hasattr(exc, "message_dict") else exc.messages})
    return {"created": [serialize_shift(shift) for shift in created], "skipped": skipped}


def conflict_list(user_profile, start_date=None, end_date=None):
    shifts = planning_queryset_for_profile(user_profile).exclude(statut="annule")
    if start_date:
        shifts = shifts.filter(Q(date_fin__date__gte=start_date) | Q(plan_type="permanent"))
    if end_date:
        shifts = shifts.filter(date_debut__date__lte=end_date)
    conflicts = []
    for shift in shifts:
        if not shift.employe:
            continue
        overlaps = PlanningShift.objects.none()
        if shift.plan_type == "normal" and shift.date_fin:
            overlaps = PlanningShift.objects.filter(
                employe=shift.employe,
                date_debut__lt=shift.date_fin,
                date_fin__gt=shift.date_debut,
                plan_type="normal",
            ).exclude(pk=shift.pk).exclude(statut="annule")
        if overlaps.exists():
            conflicts.append({"shift": serialize_shift(shift), "type": "overlap", "message": "Chevauchement avec un autre shift."})
        leave_check_end = shift.date_fin.date() if shift.date_fin else (end_date or shift.date_debut.date())
        leave = DemandeConge.objects.filter(
            employe=shift.employe,
            statut=StatutDemande.VALIDEE,
            date_debut__lte=leave_check_end,
            date_fin__gte=shift.date_debut.date(),
        )
        if leave.exists():
            conflicts.append({"shift": serialize_shift(shift), "type": "leave", "message": "Employe en conge sur cette periode."})
    return conflicts


def planning_summary(user_profile, start_date=None, end_date=None):
    shifts = planning_queryset_for_profile(user_profile).exclude(statut="annule")
    if start_date:
        shifts = shifts.filter(Q(date_fin__date__gte=start_date) | Q(plan_type="permanent"))
    if end_date:
        shifts = shifts.filter(date_debut__date__lte=end_date)
    employees = employees_for_profile(user_profile)
    planned_employee_ids = shifts.exclude(employe__isnull=True).values_list("employe_id", flat=True).distinct()
    total_hours = sum(float(shift.duree_heures or 0) for shift in shifts)
    return {
        "total_shifts": shifts.count(),
        "permanent_plans": shifts.filter(plan_type="permanent").count(),
        "employees_planned": len(set(planned_employee_ids)),
        "planned_hours": round(total_hours, 2),
        "conflicts": len(conflict_list(user_profile, start_date, end_date)),
        "employees_without_planning": employees.exclude(pk__in=planned_employee_ids).count(),
    }


def available_employees(user_profile, payload):
    starts_at = parse_dt(payload.get("starts_at") or payload.get("date_debut"), "date_debut")
    ends_at = parse_dt(payload.get("ends_at") or payload.get("date_fin"), "date_fin")
    if not starts_at or not ends_at:
        raise ValidationError("Le debut et la fin sont obligatoires.")
    employees = employees_for_profile(user_profile)
    busy_ids = PlanningShift.objects.filter(date_debut__lt=ends_at, date_fin__gt=starts_at).exclude(statut="annule").values_list("employe_id", flat=True)
    leave_ids = DemandeConge.objects.filter(
        statut=StatutDemande.VALIDEE,
        date_debut__lte=ends_at.date(),
        date_fin__gte=starts_at.date(),
    ).values_list("employe_id", flat=True)
    return [serialize_employee(employee) for employee in employees.exclude(pk__in=busy_ids).exclude(pk__in=leave_ids)]


def grid_context(user_profile, start_date, end_date):
    shifts = planning_queryset_for_profile(user_profile).filter(date_fin__date__gte=start_date, date_debut__date__lte=end_date).order_by("employe__nom", "date_debut")
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timezone.timedelta(days=1)
    employees = employees_for_profile(user_profile)
    rows = []
    for employee in employees:
        employee_shifts = list(shifts.filter(employe=employee))
        cells = []
        for day in days:
            cells.append({"day": day, "shifts": [shift for shift in employee_shifts if shift.date_debut.date() <= day <= shift.date_fin.date()]})
        rows.append({"employee": employee, "cells": cells, "total_hours": round(sum(float(shift.duree_heures or 0) for shift in employee_shifts), 2)})
    open_shifts = shifts.filter(employe__isnull=True)
    return {"days": days, "rows": rows, "open_shifts": open_shifts}
