import json
import os
import re

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from accounts.models import Role

from .models import Employe, PlanningShift
from .planning_services import (
    bulk_create_shifts,
    can_manage_planning,
    conflict_list,
    copy_planning,
    create_shift,
    employees_for_profile,
    move_shift,
    parse_day,
    planning_queryset_for_profile,
    planning_summary,
    serialize_employee,
    serialize_shift,
)


ACTION_PROMPT = """
Tu es un assistant RH pour le module Planning. Reponds uniquement en JSON valide.
Types autorises:
- qa: question/reponse sans mutation
- create_shift: creer un shift individuel
- bulk_create: creer des shifts pour departement/service/employes
- move_shift: deplacer un shift existant
- copy_planning: copier une periode
- cancel_shifts: annuler des shifts filtres
- check_conflicts: afficher les conflits

Schema:
{"intent":"qa|create_shift|bulk_create|move_shift|copy_planning|cancel_shifts|check_conflicts","answer":"court texte","payload":{},"clarification":""}

N'invente pas de donnees absentes du contexte. Si la demande est ambigue, remplis clarification.
"""


def gemini_key_configured():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def forbidden_employee_mentioned(user_profile, message):
    if not user_profile or user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE}:
        return False
    own = user_profile.employe.nom_complet.lower() if user_profile.employe else ""
    names = Employe.objects.exclude(pk=user_profile.employe_id).values_list("nom", "prenom")
    lowered = message.lower()
    return any((nom and nom.lower() in lowered) or (prenom and prenom.lower() in lowered) for nom, prenom in names if own not in lowered)


def context_for_user(user_profile, start_date=None, end_date=None):
    shifts = planning_queryset_for_profile(user_profile)
    if start_date:
        shifts = shifts.filter(date_fin__date__gte=start_date)
    if end_date:
        shifts = shifts.filter(date_debut__date__lte=end_date)
    shifts = shifts.order_by("date_debut")[:40]
    employees = employees_for_profile(user_profile)[:40]
    summary = planning_summary(user_profile, start_date, end_date)
    return {
        "role": user_profile.role if user_profile else "",
        "employee": user_profile.employe.nom_complet if user_profile and user_profile.employe else "",
        "summary": summary,
        "employees": [serialize_employee(employee) for employee in employees],
        "shifts": [serialize_shift(shift) for shift in shifts],
    }


def local_answer(user_profile, message, start_date=None, end_date=None):
    lowered = message.lower()
    if "conflit" in lowered or "conflict" in lowered:
        conflicts = conflict_list(user_profile, start_date, end_date)
        if not conflicts:
            return {"intent": "qa", "answer": "Aucun conflit de planning detecte sur la periode visible.", "data": {"conflicts": []}}
        return {"intent": "qa", "answer": f"{len(conflicts)} conflit(s) detecte(s).", "data": {"conflicts": conflicts}}
    if "sans planning" in lowered or "no planning" in lowered or "aucun planning" in lowered:
        shifts = planning_queryset_for_profile(user_profile)
        if start_date:
            shifts = shifts.filter(date_fin__date__gte=start_date)
        if end_date:
            shifts = shifts.filter(date_debut__date__lte=end_date)
        planned = shifts.exclude(employe__isnull=True).values_list("employe_id", flat=True).distinct()
        employees = employees_for_profile(user_profile).exclude(pk__in=planned)
        names = [employee.nom_complet for employee in employees[:20]]
        answer = "Tous les employes visibles ont un planning." if not names else "Employes sans planning: " + ", ".join(names)
        return {"intent": "qa", "answer": answer, "data": {"employees": names}}
    if "resume" in lowered or "résumé" in lowered or "summary" in lowered or "heures" in lowered:
        summary = planning_summary(user_profile, start_date, end_date)
        return {
            "intent": "qa",
            "answer": f"{summary['total_shifts']} shift(s), {summary['employees_planned']} employe(s), {summary['planned_hours']} heure(s), {summary['conflicts']} conflit(s).",
            "data": summary,
        }
    return None


def extract_json(text):
    if not text:
        raise ValidationError("Reponse Gemini vide.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValidationError("Reponse Gemini non structuree.")
        return json.loads(match.group(0))


def ask_gemini_for_action(user_profile, message, context):
    if not gemini_key_configured():
        raise ValidationError("Gemini n'est pas configure. Ajoutez GEMINI_API_KEY ou GOOGLE_API_KEY.")
    try:
        from google import genai
    except Exception as exc:
        raise ValidationError("Le package google-genai n'est pas installe.") from exc
    prompt = ACTION_PROMPT + "\nContexte autorise:\n" + json.dumps(context, ensure_ascii=False, default=str) + "\nDemande utilisateur:\n" + message
    client = genai.Client()
    interaction = client.interactions.create(model=getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash"), input=prompt)
    return extract_json(getattr(interaction, "output_text", ""))


def cancel_matching_shifts(user_profile, payload):
    if not can_manage_planning(user_profile):
        raise PermissionDenied("Seuls les RH/Admin peuvent annuler le planning.")
    shifts = planning_queryset_for_profile(user_profile).exclude(statut="annule")
    if payload.get("department_id"):
        shifts = shifts.filter(departement_id=payload["department_id"])
    if payload.get("service_id"):
        shifts = shifts.filter(service_id=payload["service_id"])
    if payload.get("employee_id"):
        shifts = shifts.filter(employe_id=payload["employee_id"])
    day = parse_day(payload.get("date"), "date") if payload.get("date") else None
    if day:
        shifts = shifts.filter(date_debut__date__lte=day, date_fin__date__gte=day)
    updated = []
    for shift in shifts[:100]:
        shift.statut = "annule"
        shift.full_clean()
        shift.save(update_fields=["statut", "updated_at"])
        updated.append(serialize_shift(shift))
    return {"cancelled": updated}


def execute_action(user_profile, action):
    intent = action.get("intent") or "qa"
    payload = action.get("payload") or {}
    if intent == "qa":
        return {"answer": action.get("answer") or "Je n'ai pas assez d'informations pour repondre.", "data": payload}
    if intent in {"create_shift", "bulk_create", "move_shift", "copy_planning", "cancel_shifts"} and not can_manage_planning(user_profile):
        raise PermissionDenied("Seuls les RH/Admin peuvent modifier le planning via l'assistant.")
    if intent == "create_shift":
        shift = create_shift(user_profile, payload)
        return {"answer": "Shift cree avec succes.", "data": serialize_shift(shift)}
    if intent == "bulk_create":
        return {"answer": "Creation groupee traitee.", "data": bulk_create_shifts(user_profile, payload)}
    if intent == "move_shift":
        shift = PlanningShift.objects.get(pk=payload.get("shift_id"))
        moved = move_shift(user_profile, shift, payload)
        return {"answer": "Shift deplace avec succes.", "data": serialize_shift(moved)}
    if intent == "copy_planning":
        return {"answer": "Copie du planning traitee.", "data": copy_planning(user_profile, payload)}
    if intent == "cancel_shifts":
        return {"answer": "Annulation traitee.", "data": cancel_matching_shifts(user_profile, payload)}
    if intent == "check_conflicts":
        start_date = parse_day(payload.get("start_date"), "start_date") if payload.get("start_date") else None
        end_date = parse_day(payload.get("end_date"), "end_date") if payload.get("end_date") else None
        conflicts = conflict_list(user_profile, start_date, end_date)
        return {"answer": f"{len(conflicts)} conflit(s) detecte(s).", "data": {"conflicts": conflicts}}
    raise ValidationError("Action assistant non prise en charge.")


def handle_planning_assistant(user_profile, message, start_date=None, end_date=None):
    message = (message or "").strip()
    if not message:
        raise ValidationError("Le message est obligatoire.")
    if forbidden_employee_mentioned(user_profile, message):
        return {
            "mode": "qa",
            "answer": "Je ne peux pas afficher les informations privees d'un autre employe.",
            "data": {},
        }
    local = local_answer(user_profile, message, start_date, end_date)
    if local:
        return {"mode": local["intent"], "answer": local["answer"], "data": local.get("data", {})}
    context = context_for_user(user_profile, start_date, end_date)
    try:
        action = ask_gemini_for_action(user_profile, message, context)
    except ValidationError as exc:
        return {
            "mode": "qa",
            "answer": "Gemini n'est pas disponible pour le moment. Je peux tout de meme repondre aux questions simples sur conflits, resumes et employes sans planning.",
            "data": {"error": exc.messages},
        }
    if action.get("clarification"):
        return {"mode": "clarification", "answer": action["clarification"], "data": {}}
    result = execute_action(user_profile, action)
    return {"mode": action.get("intent", "qa"), "answer": result["answer"], "data": result.get("data", {})}
