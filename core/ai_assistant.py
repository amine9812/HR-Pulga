import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, AccountCreationRequest
from hr.models import (
    ConversationRH,
    DemandeAdministrative,
    DemandeConge,
    Departement,
    Employe,
    HistoriqueAction,
    PlanningShift,
    Pointage,
    Remuneration,
    Service,
    StatutDemande,
    TacheEquipe,
    TransactionPoints,
    ComptePoints,
    Actualite,
    CommandeProduit,
    Produit,
    ReclamationRH,
)
from hr.planning_services import planning_queryset_for_profile, shift_occurs_on


MAX_MESSAGE_CHARS = 1200
DEFAULT_CONTEXT_ITEMS = 8
DEFAULT_CONTEXT_TOKENS = 6500


@dataclass
class RetrievedItem:
    source: str
    title: str
    content: str
    url: str = ""


TAB_REGISTRY = {
    "dashboard": {"label": "Tableau de bord", "url": "/dashboard", "roles": "all", "description": "Vue d'ensemble des indicateurs RH, de l'activite et des acces rapides."},
    "employees": {"label": "Employes", "url": "/employes", "roles": {Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE}, "description": "Annuaire, hierarchie, fiches employes et dossiers RH accessibles selon votre role."},
    "departments": {"label": "Departements", "url": "/departements", "roles": {Role.ADMIN, Role.RESPONSABLE_RH}, "description": "Gestion des departements, services et structure d'organisation."},
    "leave": {"label": "Demande de conge", "url": "/conges", "roles": "all", "description": "Creation, suivi et validation des demandes de conge selon vos permissions."},
    "requests": {"label": "Demandes administratives", "url": "/demandes", "roles": "all", "description": "Depot et suivi des demandes administratives RH."},
    "planning": {"label": "Planning", "url": "/planning?tab=overview", "roles": "all", "description": "Consultation des shifts, horaires, feuilles de temps, presences et rapports planning."},
    "pointage": {"label": "Presence / Pointage", "url": "/pointage", "roles": "all", "description": "Pointage entree/sortie et suivi du reel par rapport au planning."},
    "tasks": {"label": "Taches equipe", "url": "/taches", "roles": "all", "description": "Suivi des taches assignees, ouvertes, d'equipe et en attente d'approbation."},
    "support": {"label": "Support RH", "url": "/messages-rh", "roles": "all", "description": "Creation de tickets, conversation RH et suivi des statuts."},
    "payroll": {"label": "Analyse paie", "url": "/employes/paie", "roles": {Role.ADMIN, Role.RESPONSABLE_RH}, "description": "Analyses de paie et syntheses salariales pour les utilisateurs autorises."},
    "admin": {"label": "Administration", "url": "/admin", "roles": {Role.ADMIN}, "description": "Gestion administrateur des comptes, permissions, audit et parametres systeme."},
    "audit": {"label": "Audit", "url": "/audit", "roles": {Role.ADMIN}, "description": "Journal administrateur des actions importantes de l'application."},
    "boutique": {"label": "Boutique", "url": "/boutique", "roles": "all", "description": "Consulter les articles de la boutique et suivre vos commandes de materiel."},
    "actualites": {"label": "Actualites", "url": "/actualites", "roles": "all", "description": "Consulter les dernieres actualites et annonces RH."},
    "points": {"label": "Recompenses / Points", "url": "/points", "roles": "all", "description": "Consulter votre solde de points et l'historique des transactions."},
    "reclamations": {"label": "Reclamations", "url": "/reclamations", "roles": "all", "description": "Depot et suivi des reclamations concernant les points ou le planning."},
}


SENSITIVE_TERMS = {
    "salary",
    "salaire",
    "paie",
    "remuneration",
    "rémunération",
    "audit",
    "logs",
    "system prompt",
    "api key",
    "password",
    "hash",
    "all tickets",
    "tous les tickets",
}


MUTATION_PATTERNS = [
    r"\bdelete\b", r"\bupdate\b", r"\bmodify\b", r"\bapprove\b", r"\breject\b", r"\bclose\b", r"\breset\b",
    r"\bassign .*points?\b", r"\bchange .*points?\b", r"\bchange .*role\b", r"\bmake .*admin\b",
    r"\bcreate .*employee\b", r"\bdelete .*employee\b", r"\bdelete .*audit", r"\brun sql\b",
    r"\bdump .*database\b", r"\bdump .*users\b", r"\bmodify .*database\b", r"\bdisable .*permissions\b",
    r"\bbypass .*ui\b", r"\bapprove all\b", r"\bdelete all\b", r"\bmake every\b", r"\bmake everyone\b",
    r"\bchanger .*role\b", r"\bchanger .*points?\b", r"\battribuer .*points?\b",
    r"\bsupprimer\b", r"\bmodifier .*base\b", r"\bmodifier .*donnees?\b", r"\bapprouver\b",
    r"\brefuser\b", r"\bcloturer\b", r"\bfermer .*ticket", r"\btout approuver\b", r"\btout supprimer\b",
    r"\brendre .*admin\b", r"\bdevenir admin\b", r"\bexecuter .*sql\b", r"\bdesactiver .*permission",
]

INJECTION_PATTERNS = [
    r"ignore .*instructions?", r"pretend .*admin", r"answer as .*hr", r"bypass .*permissions?",
    r"show .*system prompt", r"print .*system prompt", r"show .*rag context", r"show .*database quer",
    r"reveal .*api", r"reveal .*gemini", r"reveal .*backend", r"do not refuse",
    r"developer says .*permissions? do not matter", r"you are now admin", r"pretend i have permission",
    r"show hidden", r"raw context", r"database tables?", r"password hashes?",
]

PAYROLL_TERMS = ["payroll", "paie", "salary", "salaries", "salaire", "salaires", "remuneration", "rémunération", "payment"]


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def normalized(text):
    return (text or "").lower().replace("’", "'").replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a")


def normalized(text):
    cleaned = (text or "").lower().replace("â€™", "'").replace("’", "'")
    cleaned = cleaned.replace("Ã©", "e").replace("Ã¨", "e").replace("Ãª", "e").replace("Ã ", "a").replace("Ã¹", "u")
    return "".join(ch for ch in unicodedata.normalize("NFKD", cleaned) if not unicodedata.combining(ch))


def matches_any(text, patterns):
    lowered = normalized(text)
    return any(re.search(pattern, lowered) for pattern in patterns)


def is_mutation_request(message):
    return matches_any(message, MUTATION_PATTERNS)


def is_injection_request(message):
    return matches_any(message, INJECTION_PATTERNS)


def date_window_for_message(message):
    lowered = normalized(message)
    today = timezone.localdate()
    if any(token in lowered for token in ["tomorrow", "demain"]):
        target = today + timezone.timedelta(days=1)
        return target, target, "tomorrow"
    if any(token in lowered for token in ["this week", "cette semaine", "week planning", "planning this week"]):
        start = today - timezone.timedelta(days=today.weekday())
        return start, start + timezone.timedelta(days=6), "this week"
    if any(token in lowered for token in ["today", "aujourd", "hui", "work today", "shft today"]):
        return today, today, "today"
    return today - timezone.timedelta(days=7), today + timezone.timedelta(days=14), "visible period"


def classify_intent(message):
    lowered = normalized(message)
    if is_mutation_request(message):
        return "dangerous_mutation"
    if is_injection_request(message):
        return "prompt_injection"
    if any(term in lowered for term in PAYROLL_TERMS):
        return "payroll"
    if requested_tab(message) and any(word in lowered for word in ["what is", "used for", "how do i use", "guide", "tab"]):
        return "tab_guide"
    if any(word in lowered for word in ["open", "go to", "take me", "ouvrir", "aller", "navigate"]):
        return "navigation"
    if any(word in lowered for word in ["shift", "shft", "planning", "schedule", "start", "tomorrow", "today", "demain", "aujourd", "travaille"]):
        return "planning"
    if any(word in lowered for word in ["pointage", "presence", "worked", "hours", "late", "retard", "missing", "heures"]):
        return "pointage"
    if any(word in lowered for word in ["task", "tache", "tâche"]):
        return "tasks"
    if any(word in lowered for word in ["ticket", "support"]):
        return "support"
    if any(word in lowered for word in ["leave", "conge", "congé", "demande"]):
        return "leave"
    if "audit" in lowered or "logs" in lowered:
        return "audit"
    return "general"


def user_profile(user):
    profile = getattr(user, "profile", None)
    if not user.is_authenticated or not profile or not profile.actif:
        raise PermissionDenied("Votre session n'est pas autorisee a utiliser l'assistant.")
    return profile


def accessible_employees(user_profile):
    if not user_profile or not user_profile.employe:
        return Employe.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return Employe.objects.filter(actif=True).select_related("departement", "service", "poste")
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return Employe.objects.filter(Q(pk=user_profile.employe_id) | Q(responsable=user_profile.employe), actif=True).select_related("departement", "service", "poste")
    return Employe.objects.filter(pk=user_profile.employe_id, actif=True).select_related("departement", "service", "poste")


def can_access_tab(profile, key):
    meta = TAB_REGISTRY.get(key)
    if not meta:
        return False
    roles = meta["roles"]
    return roles == "all" or profile.role in roles


def tab_items(profile, message):
    lowered = normalized(message)
    items = []
    explicit_tab = requested_tab(message)
    if explicit_tab:
        meta = TAB_REGISTRY[explicit_tab]
        if not can_access_tab(profile, explicit_tab):
            raise PermissionDenied(f"Vous n'avez pas la permission d'acceder a {meta['label']}.")
        return [RetrievedItem("tab-guide", meta["label"], meta["description"], meta["url"])]
    for key, meta in TAB_REGISTRY.items():
        if not can_access_tab(profile, key):
            continue
        if "tab" in lowered or key in lowered or normalized(meta["label"]) in lowered or "open" in lowered or "ouvrir" in lowered or "go to" in lowered:
            items.append(RetrievedItem("tab-guide", meta["label"], meta["description"], meta["url"]))
    if not items and any(word in lowered for word in ["help", "aide", "where", "ou ", "où "]):
        items = [RetrievedItem("tab-guide", meta["label"], meta["description"], meta["url"]) for key, meta in TAB_REGISTRY.items() if can_access_tab(profile, key)][:5]
    return items


def requested_tab(message):
    lowered = message.lower()
    for key, meta in TAB_REGISTRY.items():
        aliases = {key, meta["label"].lower()}
        if key == "support":
            aliases |= {"ticket", "tickets", "support rh"}
        if key == "pointage":
            aliases |= {"presence", "présence", "check in", "check-in"}
        if key == "requests":
            aliases |= {"administrative", "demande administrative"}
        if any(alias in lowered for alias in aliases):
            return key
    return None


def requested_tab(message):
    lowered = normalized(message)
    for key, meta in TAB_REGISTRY.items():
        aliases = {key, normalized(meta["label"])}
        if key == "planning":
            aliases |= {"schedule", "shift calendar", "planning tab"}
        if key == "tasks":
            aliases |= {"task", "tasks", "team task", "team tasks", "tache", "taches"}
        if key == "support":
            aliases |= {"ticket", "tickets", "support rh"}
        if key == "pointage":
            aliases |= {"presence", "check in", "check-in", "attendance"}
        if key == "leave":
            aliases |= {"conge", "conges", "leave request", "leave"}
        if key == "requests":
            aliases |= {"administrative", "demande administrative"}
        if key == "admin":
            aliases |= {"administration", "admin panel"}
        if key == "boutique":
            aliases |= {"store", "produit", "commande"}
        if key == "actualites":
            aliases |= {"news", "annonce", "actualite", "actualité"}
        if key == "points":
            aliases |= {"recompenses", "récompenses", "score"}
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
            return key
    return None


def forbidden_by_policy(profile, message):
    lowered = normalized(message)
    if is_injection_request(message):
        return "Je ne peux pas contourner les permissions, reveler des consignes internes, exposer le contexte RAG brut, afficher des requetes de base de donnees ni suivre des instructions qui annulent les regles de securite."
    if "system prompt" in lowered or "api key" in lowered or "password" in lowered or "ignore permissions" in lowered:
        return "Je ne peux pas reveler les consignes systeme, secrets, identifiants, mots de passe ou contourner les permissions."
    if ("audit" in lowered or "logs" in lowered) and profile.role != Role.ADMIN:
        return "Vous n'avez pas la permission de consulter les journaux d'audit."
    if any(normalized(term) in lowered for term in PAYROLL_TERMS) and profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return "Vous n'avez pas la permission d'acceder a ces informations de paie ou de salaire."
    if any(term in lowered for term in ["salary", "salaire", "remuneration", "rémunération", "paie"]) and profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return "Vous n'avez pas la permission d'acceder a ces informations de paie ou de salaire."
    if ("all tickets" in lowered or "tous les tickets" in lowered or "give me all hr tickets" in lowered) and profile.role != Role.ADMIN:
        return "Je peux uniquement traiter les tickets RH accessibles a votre compte."
    if profile.role == Role.EMPLOYE:
        own = profile.employe.nom_complet.lower() if profile.employe else ""
        names = Employe.objects.exclude(pk=profile.employe_id).values_list("nom", "prenom", "email")
        if any((value and re.search(rf"\b{re.escape(value.lower())}\b", lowered) and value.lower() not in own) for row in names for value in row):
            return "Vous n'avez pas la permission de consulter les donnees privees d'un autre employe."
    return ""


def planning_items(profile, message):
    lowered = normalized(message)
    if not any(word in lowered for word in ["shift", "planning", "schedule", "start", "tomorrow", "today", "demain", "aujourd", "horaire"]):
        return []
    start, end, label = date_window_for_message(message)
    qs = planning_queryset_for_profile(profile).exclude(statut="annule").order_by("date_debut")
    qs = qs.filter(Q(date_fin__date__gte=start) | Q(plan_type="permanent", date_debut__date__lte=end), date_debut__date__lte=end)
    items = []
    days = [start + timezone.timedelta(days=offset) for offset in range(min((end - start).days + 1, 14))]
    for shift in qs[:40]:
        visible_days = [day for day in days if shift_occurs_on(shift, day)]
        if not visible_days:
            continue
        day_note = ", ".join(day.isoformat() for day in visible_days)
        items.append(
            RetrievedItem(
                "planning",
                shift.titre,
                f"{day_note}: {shift.employe.nom_complet if shift.employe else 'Shift ouvert'} de {timezone.localtime(shift.date_debut).strftime('%H:%M')} a {shift.effective_end_time or '--'}, statut {shift.get_statut_display()}, type {shift.get_plan_type_display()}.",
                "/planning?tab=calendar",
            )
        )
    if not items:
        items.append(RetrievedItem("planning", f"Aucun shift pour {label}", f"Aucun shift planifie trouve pour {label} ({start} a {end}).", "/planning?tab=calendar"))
    return items


def pointage_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["worked", "hours", "pointage", "presence", "late", "retard", "missing", "heures"]):
        return []
    employees = accessible_employees(profile)
    week_start = timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday())
    qs = Pointage.objects.filter(employe__in=employees, date__gte=week_start).select_related("employe", "shift").order_by("-date", "-heure_entree")[:20]
    total = sum(float(item.total_heures or 0) for item in qs)
    items = [RetrievedItem("pointage", "Synthese de presence hebdomadaire", f"{len(qs)} pointage(s) visible(s) cette semaine, {round(total, 2)} heure(s) travaillees.", "/pointage")]
    for p in qs[:8]:
        items.append(RetrievedItem("pointage", f"Pointage {p.date}", f"{p.employe.nom_complet}: {p.get_statut_display()}, {p.total_heures} h, shift {p.shift.titre if p.shift else 'aucun shift planifie pour cette date'}.", "/pointage"))
    return items


def task_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["task", "tache", "tâche", "pending", "approval", "assigned"]):
        return []
    qs = TacheEquipe.objects.select_related("employe", "accepte_par", "manager", "departement", "service")
    if profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        scoped = qs
    elif profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        scoped = qs.filter(Q(manager=profile.employe) | Q(employe__responsable=profile.employe) | Q(accepte_par__responsable=profile.employe))
    else:
        scoped = qs.filter(Q(employe=profile.employe) | Q(accepte_par=profile.employe) | Q(manager=profile.employe.responsable, mode_affectation="open", statut="ouverte"))
    return [RetrievedItem("tasks", task.titre, f"Statut {task.get_statut_display()}, priorite {task.priorite}, responsable {task.assignee.nom_complet if task.assignee else 'tache ouverte'}, deadline {task.date_limite or 'aucune'}.", "/taches") for task in scoped.order_by("statut", "date_limite")[:10]]


def leave_request_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["leave", "conge", "congé", "approval", "approve", "demande"]):
        return []
    employees = accessible_employees(profile)
    leaves = DemandeConge.objects.filter(employe__in=employees).select_related("employe").order_by("-date_creation")[:10]
    admin_requests = DemandeAdministrative.objects.filter(employe__in=employees).select_related("employe").order_by("-date_creation")[:8]
    items = [
        RetrievedItem("leave", f"Conge {leave.pk}", f"{leave.employe.nom_complet}: {leave.get_type_display()} du {leave.date_debut} au {leave.date_fin}, statut {leave.get_statut_display()}, etape {leave.workflow_waiting_label}.", "/conges")
        for leave in leaves
    ]
    items += [
        RetrievedItem("admin-request", request.type_demande, f"{request.employe.nom_complet}: statut {request.get_statut_display()}, creee le {request.date_creation.date()}.", "/demandes")
        for request in admin_requests
    ]
    return items


def ticket_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["ticket", "support", "message rh", "close", "cloturer", "clôturer"]):
        return []
    qs = ConversationRH.objects.select_related("employe", "responsable_rh").prefetch_related("participants")
    if profile.role == Role.ADMIN:
        scoped = qs
    elif profile.role == Role.RESPONSABLE_RH:
        scoped = qs.filter(Q(responsable_rh__isnull=True) | Q(responsable_rh=profile) | Q(employe=profile.employe) | Q(participants=profile.employe)).distinct()
    else:
        scoped = qs.filter(Q(employe=profile.employe) | Q(participants=profile.employe)).distinct()
    return [RetrievedItem("support", conv.sujet, f"Ticket #{conv.numero_ticket or conv.pk}: categorie {conv.get_categorie_display()}, priorite {conv.priorite}, statut {conv.get_statut_display()}, employe {conv.employe.nom_complet}.", f"/messages-rh/{conv.pk}") for conv in scoped.order_by("-date_derniere_reponse")[:8]]


def employee_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["employee", "employe", "employé", "team", "department", "service", "manager"]):
        return []
    items = []
    for emp in accessible_employees(profile)[:12]:
        items.append(RetrievedItem("employees", emp.nom_complet, f"{emp.nom_complet}: matricule {emp.matricule}, departement {emp.departement or 'aucun'}, service {emp.service or 'aucun'}, poste {emp.poste or 'aucun'}.", "/employes"))
    return items


def payroll_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["payroll", "paie", "salary", "salaire", "remuneration", "rémunération"]):
        return []
    if profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        raise PermissionDenied("Vous n'avez pas la permission d'acceder aux informations de paie.")
    qs = Remuneration.objects.filter(actif=True).select_related("employe", "employe__departement")
    total = qs.aggregate(total=Sum("salaire_base")).get("total") or 0
    return [RetrievedItem("payroll", "Synthese paie", f"{qs.count()} remuneration(s) active(s) visible(s). Masse salariale de base {total} MAD. Les salaires individuels sont reserves aux utilisateurs RH/Admin autorises.", "/employes/paie")]


def audit_items(profile, message):
    lowered = message.lower()
    if "audit" not in lowered and "logs" not in lowered:
        return []
    if profile.role != Role.ADMIN:
        raise PermissionDenied("Vous n'avez pas la permission de consulter les journaux d'audit.")
    return [RetrievedItem("audit", action.action, f"{action.date_action}: {action.action} on {action.entite_concernee}, details {action.details[:180]}.", "/audit") for action in HistoriqueAction.objects.select_related("utilisateur").order_by("-date_action")[:8]]


def organization_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["department", "departement", "département", "service", "job", "poste"]):
        return []
    if profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE}:
        return []
    deps = Departement.objects.all()[:8]
    services = Service.objects.select_related("departement")[:8]
    return [RetrievedItem("organization", "Departements", ", ".join(dep.libelle for dep in deps), "/departements")] + [RetrievedItem("organization", service.libelle, f"Service dans {service.departement or 'aucun departement'}", "/departements?tab=services") for service in services]


def boutique_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["boutique", "store", "produit", "commande", "acheter"]):
        return []
    items = []
    if profile.employe:
        commandes = CommandeProduit.objects.filter(employe=profile.employe).select_related("produit").order_by("-date_commande")[:5]
        for cmd in commandes:
            items.append(RetrievedItem("boutique", f"Commande {cmd.pk}", f"Produit: {cmd.produit.nom}, Quantite: {cmd.quantite}, Total: {cmd.total_points} points, Statut: {cmd.get_statut_display()}", "/boutique?tab=mes_commandes"))
    produits = Produit.objects.filter(actif=True, stock_disponible__gt=0).order_by("prix_points")[:5]
    if produits:
        items.append(RetrievedItem("boutique", "Produits disponibles", ", ".join(f"{p.nom} ({p.prix_points} pts)" for p in produits), "/boutique"))
    return items


def actualites_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["actualite", "actualité", "news", "annonce"]):
        return []
    actualites = Actualite.objects.filter(publiee=True).order_by("-date_publication")[:5]
    return [RetrievedItem("actualites", act.titre, f"Publie le {act.date_publication.date()}: {act.contenu[:150]}...", "/actualites") for act in actualites]


def reclamation_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["reclamation", "réclamation", "claim", "plainte"]):
        return []
    if not profile.employe:
        return []
    reclamations = ReclamationRH.objects.filter(employe=profile.employe).order_by("-date_creation")[:5]
    return [RetrievedItem("reclamations", req.sujet, f"Type: {req.get_type_reclamation_display()}, Statut: {req.get_statut_display()}, Cree le {req.date_creation.date()}", "/reclamations") for req in reclamations]


def points_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["points", "score", "recompense", "récompense"]):
        return []
    if not profile.employe:
        return []
    compte = ComptePoints.objects.filter(employe=profile.employe).first()
    solde = compte.solde_points if compte else 0
    items = [RetrievedItem("points", "Solde de points", f"Votre solde actuel est de {solde} points.", "/points")]
    transactions = TransactionPoints.objects.filter(employe=profile.employe).order_by("-date_transaction")[:5]
    for txn in transactions:
        items.append(RetrievedItem("points", f"Transaction {txn.date_transaction.date()}", f"{'+' if txn.points > 0 else ''}{txn.points} points: {txn.motif}", "/points"))
    return items


def admin_requests_items(profile, message):
    lowered = message.lower()
    if not any(word in lowered for word in ["request", "compte", "account", "validation", "approbation"]):
        return []
    if profile.role != Role.ADMIN:
        return []
    reqs = AccountCreationRequest.objects.filter(statut="en_attente").order_by("-date_demande")[:5]
    return [RetrievedItem("admin_requests", f"Demande {req.email}", f"Statut: {req.get_statut_display()}, Cree le: {req.date_demande.date()}, Departement cible: {req.departement_cible.libelle if req.departement_cible else 'aucun'}", "/admin/comptes-en-attente") for req in reqs]


RETRIEVERS = [
    tab_items,
    planning_items,
    pointage_items,
    task_items,
    leave_request_items,
    ticket_items,
    employee_items,
    payroll_items,
    audit_items,
    organization_items,
    boutique_items,
    actualites_items,
    reclamation_items,
    points_items,
    admin_requests_items,
]


def retrieve_context(profile, message):
    max_items = env_int("RAG_MAX_CONTEXT_ITEMS", DEFAULT_CONTEXT_ITEMS)
    items = []
    errors = []
    intent = classify_intent(message)
    retrievers_by_intent = {
        "tab_guide": [tab_items],
        "navigation": [tab_items],
        "planning": [planning_items],
        "pointage": [pointage_items, planning_items],
        "tasks": [task_items],
        "support": [ticket_items],
        "leave": [leave_request_items],
        "payroll": [payroll_items],
        "audit": [audit_items],
        "general": [employee_items, organization_items, planning_items, pointage_items, task_items, leave_request_items, ticket_items, tab_items, boutique_items, actualites_items, reclamation_items, points_items],
    }
    selected_retrievers = retrievers_by_intent.get(intent, RETRIEVERS)
    for retriever in selected_retrievers:
        try:
            items.extend(retriever(profile, message))
        except PermissionDenied:
            raise
        except Exception as exc:
            errors.append(f"{retriever.__name__}: {exc}")
    if not items:
        items.extend(tab_items(profile, "help tabs")[:max_items])
    text_budget = env_int("RAG_MAX_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS) * 4
    selected = []
    used = 0
    seen = set()
    for item in items:
        key = (item.source, item.title, item.content)
        if key in seen:
            continue
        seen.add(key)
        size = len(item.content) + len(item.title)
        if selected and used + size > text_budget:
            break
        selected.append(item)
        used += size
        if len(selected) >= max_items:
            break
    return selected, errors


def navigation_for(profile, message):
    key = requested_tab(message)
    if not key:
        return []
    meta = TAB_REGISTRY[key]
    if not can_access_tab(profile, key):
        raise PermissionDenied(f"Vous n'avez pas la permission d'acceder a {meta['label']}.")
    if any(word in message.lower() for word in ["open", "go to", "take me", "ouvrir", "aller", "navigate"]):
        return [{"label": f"Ouvrir {meta['label']}", "url": meta["url"]}]
    return [{"label": f"Ouvrir {meta['label']}", "url": meta["url"]}]


def build_prompt(profile, message, context_items):
    context = [
        {"source": item.source, "title": item.title, "content": item.content, "url": item.url}
        for item in context_items
    ]
    mutation_note = ""
    if is_mutation_request(message):
        mutation_note = (
            "\n\n[ACTION DEMANDEE]\n"
            "L'utilisateur vient de demander de créer, modifier, approuver, refuser, supprimer, ou exécuter une action.\n"
            "TU NE DOIS PAS EFFECTUER D'ACTION.\n"
            "Refuse poliment d'effectuer l'action à sa place, et EXPLIQUE-LUI LES ÉTAPES MANUELLES à suivre dans l'application pour le faire lui-même.\n"
            "Exemple: 'Je ne peux pas approuver la demande à votre place. Vous pouvez l’ouvrir dans l’onglet Congés, vérifier les détails, puis cliquer sur Approuver si vous avez les permissions nécessaires.'\n"
        )
    return (
        "Tu es l'assistant IA de cette application RH. Ton rôle est d'aider les employés, managers et administrateurs avec leurs questions RH et l'utilisation de l'application. "
        "Reponds toujours en français de manière polie, claire et utile. \n\n"
        "*** RÈGLES DE SÉCURITÉ ET DE PERMISSIONS STRICTES ***\n"
        "1. Tu es STRICTEMENT EN LECTURE SEULE. Tu ne peux rien créer, modifier, approuver, refuser, assigner, cloturer, valider ou supprimer.\n"
        "2. Si l'utilisateur demande d'effectuer une action, refuse poliment et explique les étapes manuelles à suivre.\n"
        "3. Tu ne dois te baser QUE sur le contexte JSON fourni ci-dessous. Il représente ce que l'utilisateur a le droit de voir.\n"
        "4. Si l'information n'est pas dans le contexte, dis poliment que tu n'as pas accès à cette information avec les permissions actuelles de l'utilisateur.\n"
        "5. Ne révèle jamais de mots de passe, tokens, clés API, requêtes SQL brutes ou structure interne de base de données.\n"
        "6. Tes réponses doivent être propres et orientées utilisateur final, sans exposer de formats JSON ou SQL.\n"
        "*********************************************************\n"
        f"Role utilisateur: {profile.role}. Employe utilisateur: {profile.employe.nom_complet if profile.employe else 'aucun'}.\n"
        f"Contexte autorise JSON:\n{json.dumps(context, ensure_ascii=False, default=str)}\n"
        f"{mutation_note}\n"
        f"Question utilisateur:\n{message}"
    )


def gemini_configured():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def call_gemini(prompt):
    if not gemini_configured():
        raise ValidationError("Gemini n'est pas configure. Ajoutez GEMINI_API_KEY ou GOOGLE_API_KEY.")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        raise ValidationError("The google-genai package is not available.") from exc
    model = os.environ.get("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    timeout_ms = env_int("GEMINI_TIMEOUT_MS", 20000)
    def generate():
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=600)
        return client.models.generate_content(model=model, contents=prompt, config=config)

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(generate)
        response = future.result(timeout=timeout_ms / 1000)
    except FutureTimeout as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise ValidationError("Gemini a depasse le delai. Le service assistant est indisponible pour le moment. Veuillez reessayer.") from exc
    except Exception as exc:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        text = str(exc).lower()
        if "quota" in text or "rate" in text or "429" in text:
            raise ValidationError("Quota ou limite Gemini atteint. Veuillez reessayer plus tard.") from exc
        if "key" in text or "permission" in text or "401" in text or "403" in text:
            raise ValidationError("La cle API Gemini est invalide ou non autorisee.") from exc
        if "timeout" in text or "deadline" in text:
            raise ValidationError(f"Gemini a depasse le delai de {timeout_ms} ms.") from exc
        raise ValidationError("Le service Gemini n'a pas repondu.") from exc
    answer = (getattr(response, "text", "") or "").strip()
    executor.shutdown(wait=False, cancel_futures=True)
    if not answer:
        raise ValidationError("Gemini a renvoye une reponse vide.")
    return answer


def deterministic_answer(message, context_items):
    if not context_items:
        return "Je n'ai pas trouve d'information accessible pour cette demande."
    lowered = normalized(message)
    if "open" in lowered or "go to" in lowered or "ouvrir" in lowered or "take me" in lowered:
        return "I found the relevant section. You can open it using the button below."
    if context_items[0].source == "tab-guide":
        item = context_items[0]
        return f"{item.title}: {item.content}"
    if context_items[0].source == "planning" and context_items[0].title.startswith("Aucun shift"):
        return context_items[0].content
    facts = "; ".join(f"{item.title}: {item.content}" for item in context_items[:3])
    return f"Voici ce que je peux confirmer a partir des informations accessibles a votre compte: {facts}"


def assistant_response(user, message):
    message = (message or "").strip()
    if not message:
        raise ValidationError("Message is required.")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValidationError(f"Message trop long. Merci de rester sous {MAX_MESSAGE_CHARS} caracteres.")
    profile = user_profile(user)
    policy_refusal = forbidden_by_policy(profile, message)
    if policy_refusal:
        return {"answer": policy_refusal, "sources": [], "actions": [], "mode": "refusal"}
    actions = navigation_for(profile, message)
    context_items, retrieval_errors = retrieve_context(profile, message)
    prompt = build_prompt(profile, message, context_items)
    try:
        answer = call_gemini(prompt)
        mode = "gemini"
    except ValidationError:
        answer = deterministic_answer(message, context_items)
        mode = "fallback"
    return {
        "answer": answer,
        "sources": [{"source": item.source, "title": item.title, "url": item.url} for item in context_items[:5]],
        "actions": actions,
        "mode": mode,
        "retrieval_warnings": retrieval_errors[:2],
    }
