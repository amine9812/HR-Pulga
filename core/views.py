from datetime import timedelta

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt

from accounts.models import AccountCreationRequest, AdminSetting, Role, UtilisateurProfile
from .ai_assistant import assistant_response
from hr.models import (
    Actualite,
    AffectationFormation,
    CommandeProduit,
    ComptePoints,
    ConversationRH,
    DemandeAdministrative,
    DemandeConge,
    Document,
    Employe,
    HistoriqueAction,
    MessageRH,
    PlanningShift,
    Pointage,
    Remuneration,
    ReclamationRH,
    SoldeConge,
    StatutDemande,
    TacheEquipe,
)


def admin_only(request):
    user_profile = getattr(request.user, "profile", None)
    return bool(request.user.is_authenticated and user_profile and user_profile.role == Role.ADMIN and user_profile.actif)


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


def percent(value, total):
    if not total:
        return 0
    return max(0, min(100, round((value * 100) / total)))


def stat(label, value, detail=""):
    return {"label": label, "value": value, "detail": detail}


def shortcut(label, detail, icon, url_name):
    return {"label": label, "detail": detail, "icon": icon, "url": reverse(url_name)}


def kpi(label, value, detail, icon, tone="primary"):
    return {"label": label, "value": value, "detail": detail, "icon": icon, "tone": tone}


def alert_item(title, detail, icon, url_name, tone="info"):
    return {"title": title, "detail": detail, "icon": icon, "url": reverse(url_name), "tone": tone}


def dashboard_chart(title, subtitle, icon, url_name, chart_svg, metrics=None, color="#2563eb"):
    return {
        "title": title,
        "subtitle": subtitle,
        "icon": icon,
        "url": reverse(url_name),
        "chart_svg": chart_svg,
        "metrics": (metrics or [])[:3],
        "color": color,
    }


def normalize_series(values):
    numeric = [max(0, float(v or 0)) for v in values]
    return numeric, max(numeric) if numeric else 0


def short_label(label, limit=12):
    text = str(label or "Non défini")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def svg_text(value):
    return escape(str(value))


def format_chart_value(value):
    number = float(value or 0)
    return str(int(number)) if number.is_integer() else str(round(number, 1))


def svg_wrap(inner):
    return mark_safe(
        f'<svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid meet" class="dashboard-chart-svg" aria-hidden="true" focusable="false">{inner}</svg>'
    )


def bar_svg(labels, values, colors):
    """
    Compact bar chart. ViewBox 320×180.
    - Bars occupy y=[18, 116] (98px tall area).
    - Value labels sit above each bar.
    - X-axis labels sit below the baseline at y=132.
    - All text uses explicit inline font-size (10px) so the
      8px CSS class default cannot affect readability.
    """
    labels = labels[:6]
    values = values[:6]
    values_f, max_v = normalize_series(values)
    if not any(values_f):
        return ""

    count     = max(len(values_f), 1)
    C_LEFT    = 12
    C_RIGHT   = 308
    C_TOP     = 18    # top of bar area (value labels live above this)
    C_BASE    = 116   # baseline
    C_H       = C_BASE - C_TOP   # 98px  — full bar-area height
    C_W       = C_RIGHT - C_LEFT # 296px

    # Gap between bars: shrinks as count grows
    gap = max(6, min(24, C_W // max(count * 3, 1)))
    raw_bw = (C_W - gap * (count - 1)) / count
    bar_w  = min(52.0, max(22.0, raw_bw))
    drawn  = bar_w * count + gap * (count - 1)
    x0     = C_LEFT + (C_W - drawn) / 2.0

    parts = []

    # Subtle horizontal gridlines at 50 % and 100 % height
    for pct in (0.5, 1.0):
        gy = C_BASE - C_H * pct
        parts.append(
            f'<line x1="{C_LEFT}" y1="{gy:.0f}" x2="{C_RIGHT}" y2="{gy:.0f}" '
            f'stroke="rgba(148,163,184,.15)" stroke-width="1"/>'
        )
    # Baseline
    parts.append(
        f'<line x1="{C_LEFT}" y1="{C_BASE}" x2="{C_RIGHT}" y2="{C_BASE}" '
        f'stroke="rgba(148,163,184,.35)" stroke-width="1.5"/>'
    )

    x = x0
    for idx, v in enumerate(values_f):
        # Bar height: cap at 92 % of area so bars never look wall-to-wall
        bh = 0 if max_v == 0 else round((v / max_v) * C_H * 0.92)
        if v > 0 and bh < 5:
            bh = 5
        by    = C_BASE - bh
        cx    = x + bar_w / 2
        color = colors[idx % len(colors)]
        title = svg_text(f"{labels[idx]}: {format_chart_value(v)}")
        lbl   = svg_text(short_label(labels[idx], 9))
        val   = format_chart_value(v)

        # Bar + tooltip
        parts.append(
            f'<g><title>{title}</title>'
            f'<rect x="{x:.1f}" y="{by}" width="{bar_w:.1f}" height="{bh}" rx="5" fill="{color}"/>'
            f'</g>'
        )
        # Value label above bar (only when bar is visible)
        if v > 0:
            vy = max(8, by - 5)
            parts.append(
                f'<text x="{cx:.1f}" y="{vy:.0f}" text-anchor="middle" '
                f'fill="#1e293b" font-size="10" font-weight="700">{val}</text>'
            )
        # X-axis label
        parts.append(
            f'<text x="{cx:.1f}" y="132" text-anchor="middle" '
            f'fill="#64748b" font-size="10" font-weight="500">{lbl}</text>'
        )
        x += bar_w + gap

    return svg_wrap("".join(parts))


def donut_svg(labels, values, colors):
    """
    Donut chart. ViewBox 320×180.
    - Donut centred at (74, 90), radius 40, stroke 14.
    - Legend starts at x=155, y=36, row-height 26px.
    - All text uses explicit inline font-size (10px).
    """
    labels     = labels[:5]
    values_raw = values[:5]
    values_f, total = normalize_series(values_raw)
    if total == 0:
        return ""

    radius = 40
    sw     = 14
    circ   = 2 * 3.14159 * radius
    dcx, dcy = 74, 90
    current  = 0

    parts = []
    # Background track
    parts.append(
        f'<circle cx="{dcx}" cy="{dcy}" r="{radius}" '
        f'fill="none" stroke="rgba(226,232,240,.9)" stroke-width="{sw}"/>'
    )

    for idx, v in enumerate(values_f):
        if not v:
            continue
        dash    = circ * (v / total)
        gap_d   = circ - dash
        offset  = -circ * (current / total)
        title   = svg_text(f"{labels[idx]}: {format_chart_value(v)}")
        col     = colors[idx % len(colors)]
        parts.append(
            f'<g><title>{title}</title>'
            f'<circle cx="{dcx}" cy="{dcy}" r="{radius}" fill="none" stroke="{col}" '
            f'stroke-width="{sw}" stroke-linecap="butt" '
            f'stroke-dasharray="{dash:.2f} {gap_d:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" '
            f'transform="rotate(-90 {dcx} {dcy})"/>'
            f'</g>'
        )
        current += v

    # Centre text
    total_str = format_chart_value(total)
    parts.append(
        f'<text x="{dcx}" y="{dcy - 5}" text-anchor="middle" '
        f'fill="#111827" font-size="17" font-weight="900">{total_str}</text>'
    )
    parts.append(
        f'<text x="{dcx}" y="{dcy + 11}" text-anchor="middle" '
        f'fill="#9ca3af" font-size="8" font-weight="700" letter-spacing="0.5">TOTAL</text>'
    )

    # Legend
    lx  = 155
    ly  = 40
    row = 26
    visible = [
        (labels[i], values_f[i], colors[i % len(colors)])
        for i in range(len(labels)) if values_f[i] > 0
    ]
    for lbl, val, col in visible[:5]:
        legend_lbl = svg_text(short_label(lbl, 14))
        disp_val   = int(val) if float(val).is_integer() else round(float(val), 1)
        # Coloured circle dot
        parts.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{col}"/>')
        # Label text
        parts.append(
            f'<text x="{lx + 15}" y="{ly}" '
            f'fill="#374151" font-size="10" font-weight="600">{legend_lbl}</text>'
        )
        # Numeric value
        parts.append(
            f'<text x="314" y="{ly}" text-anchor="end" '
            f'fill="#111827" font-size="10" font-weight="700">{disp_val}</text>'
        )
        ly += row

    return svg_wrap("".join(parts))


def line_svg(labels, values, color):
    """
    Area line chart. ViewBox 320×180.
    - Chart area y=[16, 122] (106px). Baseline at y=122.
    - X-axis labels at y=140.
    - All text uses explicit inline font-size (10px).
    """
    values_f, max_v = normalize_series(values)
    if not any(values_f):
        return ""

    C_LEFT  = 14
    C_RIGHT = 306
    C_TOP   = 16
    C_BASE  = 122
    C_H     = C_BASE - C_TOP   # 106px
    C_W     = C_RIGHT - C_LEFT # 292px
    count   = max(len(values_f) - 1, 1)

    # Compute (x, y) for each data point
    pts = []
    for idx, v in enumerate(values_f):
        px = C_LEFT + C_W * idx / count
        py = C_BASE - (0 if max_v == 0 else (v / max_v) * C_H)
        pts.append((px, py, v, labels[idx]))

    pt_str   = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
    fill_pts = pt_str + f" {C_RIGHT:.1f},{C_BASE} {C_LEFT:.1f},{C_BASE}"

    parts = []

    # Horizontal gridlines at 25 %, 50 %, 75 %, 100 %
    for pct in (0.25, 0.5, 0.75, 1.0):
        gy = C_BASE - C_H * pct
        parts.append(
            f'<line x1="{C_LEFT}" y1="{gy:.0f}" x2="{C_RIGHT}" y2="{gy:.0f}" '
            f'stroke="rgba(148,163,184,.12)" stroke-width="1"/>'
        )
    # Baseline
    parts.append(
        f'<line x1="{C_LEFT}" y1="{C_BASE}" x2="{C_RIGHT}" y2="{C_BASE}" '
        f'stroke="rgba(148,163,184,.30)" stroke-width="1"/>'
    )

    # Area fill
    parts.append(f'<polygon fill="rgba(91,92,226,.07)" points="{fill_pts}"/>')
    # Line
    parts.append(
        f'<polyline fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{pt_str}"/>'
    )

    # Dots + tooltips
    for px, py, v, lbl in pts:
        title = svg_text(f"{lbl}: {format_chart_value(v)}")
        parts.append(
            f'<g><title>{title}</title>'
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" '
            f'fill="{color}" stroke="#fff" stroke-width="2"/>'
            f'</g>'
        )

    # X-axis labels (skip alternate when crowded)
    for idx, (px, py, v, lbl) in enumerate(pts):
        if len(pts) > 5 and idx % 2 != 0:
            continue
        parts.append(
            f'<text x="{px:.1f}" y="140" text-anchor="middle" '
            f'fill="#64748b" font-size="10" font-weight="500">{svg_text(lbl)}</text>'
        )

    return svg_wrap("".join(parts))


def status_counts(queryset):
    return dict(queryset.values_list("statut").annotate(total=Count("id")))


def values_for_statuses(counts, statuses):
    return [counts.get(status, 0) for status in statuses]


def recent_employee_hours(employee, today):
    labels = [(today - timedelta(days=6 - idx)).strftime("%d/%m") for idx in range(7)]
    if not employee:
        return labels, [0] * 7
    start_date = today - timedelta(days=6)
    hours_by_date = {
        item["date"]: float(item["hours"] or 0)
        for item in Pointage.objects.filter(employe=employee, date__gte=start_date, date__lte=today)
        .values("date")
        .annotate(hours=Sum("total_heures"))
    }
    values = [hours_by_date.get(today - timedelta(days=6 - idx), 0) for idx in range(7)]
    return labels, values


@login_required
def dashboard(request):
    profile = getattr(request.user, "profile", None)
    today = timezone.localdate()
    is_admin = profile and profile.role == Role.ADMIN
    is_hr = profile and profile.role == Role.RESPONSABLE_RH
    is_rh = bool(profile and profile.role in {Role.ADMIN, Role.RESPONSABLE_RH})
    is_manager = bool(profile and profile.role == Role.RESPONSABLE_HIERARCHIQUE)
    employee = profile.employe if profile else None
    employes_actifs = Employe.objects.filter(actif=True)
    team = Employe.objects.filter(responsable=employee, actif=True) if employee else Employe.objects.none()

    all_conges = DemandeConge.objects.select_related("employe", "traitee_par")
    all_demandes_admin = DemandeAdministrative.objects.select_related("employe", "traitee_par")
    all_pointages_today = Pointage.objects.filter(date=today).select_related("employe")
    all_upcoming_shifts = PlanningShift.objects.filter(date_fin__date__gte=today).exclude(statut__in=["annule", "termine"])
    all_open_tasks = TacheEquipe.objects.exclude(statut__in=["terminee", "annulee"])
    all_reclamations = ReclamationRH.objects.filter(statut__in=["ouverte", "en_cours"])
    all_documents = Document.objects.filter(archive=False)

    if is_rh:
        visible_employes = employes_actifs
        conges = all_conges
        demandes_admin = all_demandes_admin
        pointages_today = all_pointages_today.filter(employe__in=visible_employes)
        upcoming_shifts = all_upcoming_shifts
        open_tasks = all_open_tasks
        reclamations_ouvertes = all_reclamations
        documents_visibles = all_documents
    elif is_manager and employee:
        visible_employes = Employe.objects.filter(Q(pk=employee.pk) | Q(responsable=employee), actif=True)
        conges = all_conges.filter(employe__in=team)
        demandes_admin = all_demandes_admin.filter(employe=employee)
        pointages_today = all_pointages_today.filter(employe__in=visible_employes)
        upcoming_shifts = all_upcoming_shifts.filter(Q(employe__in=visible_employes) | Q(employe__isnull=True, departement=employee.departement))
        open_tasks = all_open_tasks.filter(Q(employe__in=visible_employes) | Q(departement=employee.departement, employe__isnull=True))
        reclamations_ouvertes = all_reclamations.filter(employe=employee)
        documents_visibles = all_documents.filter(employe=employee)
    elif employee:
        visible_employes = Employe.objects.filter(pk=employee.pk)
        conges = all_conges.filter(employe=employee)
        demandes_admin = all_demandes_admin.filter(employe=employee)
        pointages_today = all_pointages_today.filter(employe=employee)
        upcoming_shifts = all_upcoming_shifts.filter(employe=employee)
        open_tasks = all_open_tasks.filter(employe=employee)
        reclamations_ouvertes = all_reclamations.filter(employe=employee)
        documents_visibles = all_documents.filter(employe=employee)
    else:
        visible_employes = Employe.objects.none()
        conges = all_conges.none()
        demandes_admin = all_demandes_admin.none()
        pointages_today = all_pointages_today.none()
        upcoming_shifts = all_upcoming_shifts.none()
        open_tasks = all_open_tasks.none()
        reclamations_ouvertes = all_reclamations.none()
        documents_visibles = all_documents.none()

    conges_en_attente = conges.filter(statut=StatutDemande.EN_ATTENTE).count()
    demandes_admin_en_attente = demandes_admin.filter(statut=StatutDemande.EN_ATTENTE).count()
    conges_valides = conges.filter(statut=StatutDemande.VALIDEE).count()
    demandes_traitees = demandes_admin.exclude(statut=StatutDemande.EN_ATTENTE).count()
    total_demandes = conges.count() + demandes_admin.count()
    demandes_resolues = conges.exclude(statut=StatutDemande.EN_ATTENTE).count() + demandes_traitees
    taux_traitement = 100 if total_demandes == 0 else round((demandes_resolues * 100) / total_demandes)
    notifications = profile.notifications.filter(lue=False).count() if profile else 0
    if is_rh:
        messages_non_lus = MessageRH.objects.filter(lu=False).exclude(expediteur=profile).filter(Q(destinataire=profile) | Q(destinataire__isnull=True)).count()
    else:
        messages_non_lus = MessageRH.objects.filter(destinataire=profile, lu=False).count() if profile else 0
    employee_pending_conges = DemandeConge.objects.filter(employe=employee, statut=StatutDemande.EN_ATTENTE).count() if employee else 0
    employee_pending_admin = DemandeAdministrative.objects.filter(employe=employee, statut=StatutDemande.EN_ATTENTE).count() if employee else 0
    employee_pointage = pointages_today.filter(employe=employee).first() if employee else None
    compte = ComptePoints.objects.get_or_create(employe=employee)[0] if employee else None
    solde = SoldeConge.objects.get_or_create(employe=employee)[0] if employee else None
    score_rh = taux_traitement
    visible_count = visible_employes.count()
    total_employes_actifs = employes_actifs.count()
    departements_count = employes_actifs.exclude(departement__isnull=True).values("departement").distinct().count()
    presences_count = pointages_today.count()
    retards_count = pointages_today.filter(statut="retard").count()
    absences_count = max(visible_count - presences_count, 0)
    open_tasks_count = open_tasks.count()
    reclamations_count = reclamations_ouvertes.count()
    upcoming_shifts_count = upcoming_shifts.count()
    salary_count = Remuneration.objects.filter(actif=True).count() if is_rh else 0
    formations_qs = AffectationFormation.objects.exclude(statut__in=["terminee", "annulee"])
    if is_rh:
        formations_actives = formations_qs.count()
    elif visible_count:
        formations_actives = formations_qs.filter(employe__in=visible_employes).count()
    else:
        formations_actives = 0
    commandes_pending = CommandeProduit.objects.filter(statut="en_attente").count() if is_rh else CommandeProduit.objects.filter(employe=employee, statut="en_attente").count() if employee else 0
    materiel_livre = CommandeProduit.objects.filter(employe=employee, statut="livree").count() if employee else 0
    employee_pending_total = employee_pending_conges + employee_pending_admin
    leave_available = float(solde.jours_disponibles) if solde else 0
    leave_used = float(solde.jours_utilises) if solde else 0
    leave_total = leave_available + leave_used
    shift_today = upcoming_shifts.filter(employe=employee, date_debut__date__lte=today, date_fin__date__gte=today).order_by("date_debut").first() if employee else None
    documents_count = documents_visibles.count()
    conversations_ouvertes = ConversationRH.objects.filter(statut__in=["ouverte", "en_attente"]).count() if is_rh else ConversationRH.objects.filter(employe=employee, statut__in=["ouverte", "en_attente"]).count() if employee else 0
    workflow_total = conges_en_attente + demandes_admin_en_attente + reclamations_count + commandes_pending + messages_non_lus
    request_statuses = [StatutDemande.EN_ATTENTE, StatutDemande.VALIDEE, StatutDemande.REFUSEE, StatutDemande.CLOTUREE]
    request_labels = ["En attente", "Validées", "Refusées", "Clôturées"]
    conge_status_counts = status_counts(conges)
    admin_status_counts = status_counts(demandes_admin)
    combined_request_values = [
        conge_status_counts.get(status, 0) + admin_status_counts.get(status, 0)
        for status in request_statuses
    ]
    department_counts = list(
        employes_actifs.values("departement__libelle")
        .annotate(total=Count("id"))
        .order_by("-total", "departement__libelle")[:4]
    )
    document_counts = list(
        documents_visibles.values("categorie")
        .annotate(total=Count("id"))
        .order_by("-total", "categorie")[:4]
    )

    dashboard_actions = []
    dashboard_charts = []
    dashboard_kpis = []
    dashboard_alerts = []
    dashboard_variant = "employee"

    if is_admin:
        dashboard_variant = "admin"
        dashboard_kpis = [
            kpi("Employés actifs", total_employes_actifs, f"{departements_count} département(s)", "bi-people", "primary"),
            kpi("Présence", f"{percent(presences_count, visible_count)}%", f"{retards_count} retard(s)", "bi-clock-history", "success"),
            kpi("Demandes ouvertes", conges_en_attente + demandes_admin_en_attente, "Congés + administratif", "bi-inboxes", "warning"),
            kpi("Planning", upcoming_shifts_count, "Shifts à venir", "bi-calendar-week", "info"),
            kpi("Documents", documents_count, "Archives actives", "bi-folder2-open", "primary"),
            kpi("Paie couverte", salary_count, "Rémunérations actives", "bi-cash-stack", "success"),
        ]
        dashboard_charts = [
            dashboard_chart("Effectif actif", "Répartition par département", "bi-people", "employes_list", bar_svg([item["departement__libelle"] or "Sans département" for item in department_counts], [item["total"] for item in department_counts], ["#2563eb", "#0ea5e9", "#16a34a", "#f59e0b"]), [stat("Actifs", total_employes_actifs), stat("Départements", departements_count), stat("Paie", salary_count)], "#2563eb"),
            dashboard_chart("Demandes globales", "Congés + administratif par statut", "bi-inboxes", "demandes_list", bar_svg(request_labels, combined_request_values, ["#f59e0b", "#16a34a", "#ef4444", "#64748b"]), [stat("À traiter", conges_en_attente + demandes_admin_en_attente), stat("Traitement", f"{taux_traitement}%"), stat("Validées", conges_valides)], "#f59e0b"),
            dashboard_chart("Présence du jour", "Population active visible", "bi-clock-history", "attendance", donut_svg(["Présents", "Retards", "Non pointés"], [presences_count, retards_count, absences_count], ["#16a34a", "#f59e0b", "#ef4444"]), [stat("Couverture", f"{percent(presences_count, visible_count)}%"), stat("Présents", presences_count), stat("Population", visible_count)], "#16a34a"),
            dashboard_chart("Planning & activité", "Charge opérationnelle", "bi-calendar-week", "planning", bar_svg(["Shifts", "Tâches", "Formations"], [upcoming_shifts_count, open_tasks_count, formations_actives], ["#2563eb", "#7c3aed", "#0ea5e9"]), [stat("Shifts", upcoming_shifts_count), stat("Tâches", open_tasks_count), stat("Formations", formations_actives)], "#7c3aed"),
        ]
        dashboard_actions = [
            shortcut("Ajouter un employe", "Nouveau dossier RH", "bi-person-plus", "employe_create"),
            shortcut("Valider les conges", f"{conges_en_attente} en attente", "bi-check2-circle", "conges_list"),
            shortcut("Traiter demandes", f"{demandes_admin_en_attente} dossier(s)", "bi-inbox", "demandes_list"),
            shortcut("Planning", f"{upcoming_shifts_count} shift(s)", "bi-calendar-week", "planning"),
            shortcut("Documents", f"{documents_count} actif(s)", "bi-folder2-open", "documents_list"),
            shortcut("Audit", "Historique global", "bi-activity", "audit_history"),
        ]
        if workflow_total:
            dashboard_alerts.append(alert_item("Flux RH à superviser", f"{workflow_total} élément(s) ouverts", "bi-inboxes", "demandes_list", "warning"))
        if retards_count:
            dashboard_alerts.append(alert_item("Retards aujourd'hui", f"{retards_count} pointage(s) en retard", "bi-clock-history", "attendance", "danger"))

    elif is_hr:
        dashboard_variant = "rh"
        dashboard_kpis = [
            kpi("Validations", conges_en_attente + demandes_admin_en_attente, "Congés + demandes", "bi-check2-circle", "warning"),
            kpi("Réclamations", reclamations_count, "Ouvertes / en cours", "bi-exclamation-circle", "danger"),
            kpi("Documents", documents_count, "Non archivés", "bi-folder2-open", "primary"),
            kpi("Messages RH", messages_non_lus, "Non lus", "bi-chat-dots", "info"),
            kpi("Formations", formations_actives, "Affectations actives", "bi-mortarboard", "success"),
            kpi("Commandes", commandes_pending, "Matériel à traiter", "bi-bag-check", "warning"),
        ]
        dashboard_charts = [
            dashboard_chart("File RH", "Éléments à traiter", "bi-inboxes", "demandes_list", donut_svg(["Congés", "Demandes", "Réclamations", "Commandes", "Messages"], [conges_en_attente, demandes_admin_en_attente, reclamations_count, commandes_pending, messages_non_lus], ["#f59e0b", "#0ea5e9", "#ef4444", "#7c3aed", "#2563eb"]), [stat("Ouverts", workflow_total), stat("Traitement", f"{taux_traitement}%"), stat("Conversations", conversations_ouvertes)], "#f59e0b"),
            dashboard_chart("Statuts demandes", "Congés + administratif", "bi-kanban", "demandes_list", bar_svg(request_labels, combined_request_values, ["#f59e0b", "#16a34a", "#ef4444", "#64748b"]), [stat("Congés", conges.count()), stat("Admin", demandes_admin.count()), stat("En attente", conges_en_attente + demandes_admin_en_attente)], "#0ea5e9"),
            dashboard_chart("Documents RH", "Répartition par catégorie", "bi-folder2-open", "documents_list", bar_svg([item["categorie"] or "Général" for item in document_counts], [item["total"] for item in document_counts], ["#2563eb", "#0ea5e9", "#16a34a", "#f59e0b"]), [stat("Actifs", documents_count), stat("Catégories", len(document_counts)), stat("Archivés", Document.objects.filter(archive=True).count())], "#2563eb"),
            dashboard_chart("Présence du jour", "Pointages visibles", "bi-clock-history", "attendance", donut_svg(["Présents", "Retards", "Non pointés"], [presences_count, retards_count, absences_count], ["#16a34a", "#f59e0b", "#ef4444"]), [stat("Couverture", f"{percent(presences_count, visible_count)}%"), stat("Retards", retards_count), stat("Population", visible_count)], "#16a34a"),
        ]
        dashboard_actions = [
            shortcut("Valider les conges", f"{conges_en_attente} en attente", "bi-check2-circle", "conges_list"),
            shortcut("Traiter demandes", f"{demandes_admin_en_attente} dossier(s)", "bi-inbox", "demandes_list"),
            shortcut("Documents", "Classer et archiver", "bi-folder2-open", "documents_list"),
            shortcut("Messages RH", f"{messages_non_lus} non lu(s)", "bi-chat-dots", "rh_messages"),
            shortcut("Assigner formation", "Suivi competences", "bi-mortarboard", "formations_admin"),
            shortcut("Gerer postes", "Organisation", "bi-briefcase", "position_management"),
        ]
        if conges_en_attente:
            dashboard_alerts.append(alert_item("Congés à valider", f"{conges_en_attente} demande(s) en attente", "bi-calendar2-check", "conges_list", "warning"))
        if demandes_admin_en_attente:
            dashboard_alerts.append(alert_item("Demandes administratives", f"{demandes_admin_en_attente} dossier(s) à traiter", "bi-file-earmark-text", "demandes_list", "info"))
        if reclamations_count:
            dashboard_alerts.append(alert_item("Réclamations ouvertes", f"{reclamations_count} réclamation(s)", "bi-exclamation-circle", "reclamations", "danger"))

    elif is_manager:
        team_total = team.count()
        team_present = pointages_today.filter(employe__in=team).count()
        team_late = pointages_today.filter(employe__in=team, statut="retard").count()
        team_absent = max(team_total - team_present, 0)
        manager_workload = conges_en_attente + open_tasks_count + messages_non_lus
        dashboard_variant = "manager"
        dashboard_kpis = [
            kpi("Équipe", team_total, "Collaborateurs directs", "bi-diagram-3", "primary"),
            kpi("Présence équipe", f"{percent(team_present, team_total)}%", f"{team_late} retard(s)", "bi-clock-history", "success"),
            kpi("Congés équipe", conges_en_attente, "À valider", "bi-calendar2-check", "warning"),
            kpi("Tâches ouvertes", open_tasks_count, "Charge active", "bi-list-check", "info"),
            kpi("Planning", upcoming_shifts_count, "Shifts à venir", "bi-calendar-week", "primary"),
            kpi("Messages", messages_non_lus, "Non lus", "bi-chat-dots", "info"),
        ]
        dashboard_charts = [
            dashboard_chart("Couverture équipe", "Présence des collaborateurs", "bi-diagram-3", "attendance", donut_svg(["Présents", "Retards", "Non pointés"], [team_present, team_late, team_absent], ["#16a34a", "#f59e0b", "#ef4444"]), [stat("Équipe", team_total), stat("Retards", team_late), stat("Couverture", f"{percent(team_present, team_total)}%")], "#16a34a"),
            dashboard_chart("Charge de suivi", "Validations et tâches", "bi-list-check", "team_tasks", bar_svg(["Congés", "Tâches", "Messages"], [conges_en_attente, open_tasks_count, messages_non_lus], ["#f59e0b", "#7c3aed", "#0ea5e9"]), [stat("À suivre", manager_workload), stat("Congés", conges_en_attente), stat("Tâches", open_tasks_count)], "#7c3aed"),
            dashboard_chart("Planning équipe", "Shifts et formation", "bi-calendar-week", "planning", bar_svg(["Shifts", "Formations"], [upcoming_shifts_count, formations_actives], ["#2563eb", "#16a34a"]), [stat("Collaborateurs", team_total), stat("À venir", upcoming_shifts_count), stat("Formations", formations_actives)], "#2563eb"),
            dashboard_chart("Mes demandes", "Flux personnel manager", "bi-person-check", "demandes_list", donut_svg(["Congés", "Admin", "Messages"], [employee_pending_conges, employee_pending_admin, messages_non_lus], ["#f59e0b", "#0ea5e9", "#2563eb"]), [stat("Solde congés", leave_available), stat("Points", compte.solde_points if compte else 0), stat("Pointage", employee_pointage.statut if employee_pointage else "-")], "#0ea5e9"),
        ]
        dashboard_actions = [
            shortcut("Planning equipe", "Voir la semaine", "bi-calendar-week", "planning"),
            shortcut("Valider conges", f"{conges_en_attente} en attente", "bi-check2-circle", "conges_list"),
            shortcut("Taches equipe", f"{open_tasks_count} ouvertes", "bi-list-check", "team_tasks"),
            shortcut("Presence", "Pointage equipe", "bi-clock-history", "attendance"),
            shortcut("Messages RH", f"{messages_non_lus} non lu(s)", "bi-chat-dots", "rh_messages"),
        ]
        if conges_en_attente:
            dashboard_alerts.append(alert_item("Congés équipe", f"{conges_en_attente} demande(s) à valider", "bi-check2-circle", "conges_list", "warning"))
        if open_tasks_count:
            dashboard_alerts.append(alert_item("Tâches à suivre", f"{open_tasks_count} tâche(s) ouverte(s)", "bi-list-check", "team_tasks", "info"))
        if team_late:
            dashboard_alerts.append(alert_item("Retards équipe", f"{team_late} retard(s) aujourd'hui", "bi-clock-history", "attendance", "danger"))

    else:
        request_total = employee_pending_total + messages_non_lus + reclamations_count
        hours_labels, hours_values = recent_employee_hours(employee, today)
        dashboard_kpis = [
            kpi("Solde congés", leave_available, f"{leave_used} jour(s) utilisés", "bi-wallet2", "success"),
            kpi("Demandes", employee_pending_total, "En attente", "bi-inbox", "warning"),
            kpi("Pointage", employee_pointage.statut if employee_pointage else "Non pointé", today.strftime("%d/%m"), "bi-clock-history", "info"),
            kpi("Planning", upcoming_shifts_count, "Shifts à venir", "bi-calendar-week", "primary"),
            kpi("Notifications", notifications, "Non lues", "bi-bell", "warning"),
            kpi("Points", compte.solde_points if compte else 0, "Solde boutique", "bi-stars", "success"),
        ]
        dashboard_charts = [
            dashboard_chart("Solde & points", "Vos droits personnels", "bi-wallet2", "conges_list", donut_svg(["Congés dispo", "Congés utilisés", "Points"], [leave_available, leave_used, compte.solde_points if compte else 0], ["#16a34a", "#f59e0b", "#2563eb"]), [stat("Points", compte.solde_points if compte else 0), stat("Utilisés", leave_used), stat("Disponibles", leave_available)], "#16a34a"),
            dashboard_chart("Pointage", "Heures sur 7 jours", "bi-clock-history", "attendance", line_svg(hours_labels, hours_values, "#2563eb"), [stat("Shift", shift_today.titre if shift_today else "Aucun"), stat("Date", today.strftime("%d/%m")), stat("Lieu", shift_today.lieu if shift_today else "-")], "#2563eb"),
            dashboard_chart("Mes demandes", "Congés, admin et messages", "bi-inbox", "demandes_list", donut_svg(["Congés", "Admin", "Messages", "Réclamations"], [employee_pending_conges, employee_pending_admin, messages_non_lus, reclamations_count], ["#f59e0b", "#0ea5e9", "#2563eb", "#ef4444"]), [stat("Congés", employee_pending_conges), stat("Admin", employee_pending_admin), stat("Messages", messages_non_lus)], "#f59e0b"),
            dashboard_chart("Planning personnel", "Semaine et parcours", "bi-stars", "planning", bar_svg(["Shifts", "Formations", "Matériel"], [upcoming_shifts_count, formations_actives, materiel_livre], ["#2563eb", "#16a34a", "#7c3aed"]), [stat("Formations", formations_actives), stat("Matériel", materiel_livre), stat("À venir", upcoming_shifts_count)], "#7c3aed"),
        ]
        dashboard_actions = [
            shortcut("Pointer", "Entree ou sortie", "bi-clock-history", "attendance"),
            shortcut("Demander conge", "Selon votre solde", "bi-calendar-plus", "conge_create"),
            shortcut("Message RH", "Contact confidentiel", "bi-chat-dots", "rh_messages"),
            shortcut("Boutique", "Materiel et points", "bi-bag-check", "shop"),
            shortcut("Planning", "Vos prochains shifts", "bi-calendar-week", "planning"),
            shortcut("Formations", "Modules a suivre", "bi-mortarboard", "my_trainings"),
        ]
        if employee_pending_total:
            dashboard_alerts.append(alert_item("Demandes en attente", f"{employee_pending_total} demande(s) en cours", "bi-inbox", "demandes_list", "warning"))
        if shift_today:
            dashboard_alerts.append(alert_item("Shift aujourd'hui", shift_today.titre, "bi-calendar-week", "planning", "info"))
        if notifications:
            dashboard_alerts.append(alert_item("Notifications non lues", f"{notifications} notification(s)", "bi-bell", "notifications_list", "info"))

    return render(
        request,
        "dashboard/index.html",
        {
            "page_title": "Tableau de bord",
            "role_actuel": profile.role if profile else "",
            "role_label": profile.role.replace("_", " ") if profile else "Session",
            "dashboard_variant": dashboard_variant,
            "dashboard_kpis": dashboard_kpis,
            "dashboard_charts": dashboard_charts,
            "dashboard_actions": dashboard_actions,
            "dashboard_alerts": dashboard_alerts[:4],
            "total_employes_actifs": total_employes_actifs,
            "conges_en_attente": conges_en_attente,
            "demandes_admin_en_attente": demandes_admin_en_attente,
            "conges_valides": conges_valides,
            "demandes_traitees": demandes_traitees,
            "taux_traitement": taux_traitement,
            "score_rh": score_rh,
            "notifications_dashboard": notifications,
            "recent_conges": conges.order_by("-date_creation")[:5],
            "recent_demandes_admin": demandes_admin.order_by("-date_creation")[:5],
            "employes_preview": visible_employes[:8],
            "is_rh_dashboard": is_rh,
            "is_manager_dashboard": is_manager,
            "solde_conge": solde,
            "compte_points": compte,
            "dernier_pointage": employee_pointage or (Pointage.objects.filter(employe=employee).first() if employee else None),
            "presences_aujourdhui": presences_count,
            "retards_aujourdhui": retards_count,
            "formations_assignees": formations_actives,
            "commandes_en_attente": commandes_pending,
            "messages_non_lus": messages_non_lus,
            "actualites_recentes": Actualite.objects.filter(statut="publiee")[:3],
            "team_count": team.count(),
            "team_presences": pointages_today.filter(employe__in=team).count(),
            "team_retards": pointages_today.filter(employe__in=team, statut="retard").count(),
            "salary_summary": salary_count,
            "shifts_a_venir": upcoming_shifts_count,
            "taches_ouvertes": open_tasks_count,
            "reclamations_a_traiter": reclamations_count,
            "mes_demandes_en_attente": employee_pending_conges + employee_pending_admin,
            "materiel_employe": materiel_livre,
        },
    )


@login_required
def admin_dashboard(request):
    if not admin_only(request):
        messages.error(request, "Acces administration reserve aux administrateurs.")
        return redirect("dashboard")
    active_tab = request.GET.get("tab", "overview")
    allowed_tabs = {"overview", "account_requests", "users", "permissions", "edit_requests", "audit", "settings", "security", "notifications", "data", "reports"}
    if active_tab not in allowed_tabs:
        messages.warning(request, "Section Administration introuvable. Retour a l'Overview.")
        return redirect(f"{reverse('admin_dashboard')}?tab=overview")
    users = User.objects.select_related("profile", "profile__employe").order_by("username")
    account_requests = AccountCreationRequest.objects.select_related("employee", "user", "decided_by").order_by("-submitted_at")
    audit_actions = HistoriqueAction.objects.select_related("utilisateur", "utilisateur__user").order_by("-date_action")
    settings_map = {setting.key: setting.value for setting in AdminSetting.objects.all()}
    stats = {
        "pending_accounts": account_requests.filter(status=AccountCreationRequest.STATUS_PENDING).count(),
        "active_users": users.filter(profile__actif=True, is_active=True).count(),
        "inactive_users": users.filter(Q(profile__actif=False) | Q(is_active=False)).count(),
        "audit_events": audit_actions.count(),
        "admin_users": users.filter(profile__role=Role.ADMIN).count(),
        "security_alerts": users.filter(is_active=False).count(),
    }
    return render(
        request,
        "admin/index.html",
        {
            "page_title": "Administration",
            "active_tab": active_tab,
            "stats": stats,
            "account_requests": account_requests[:100],
            "users": users[:200],
            "roles": Role.choices,
            "audit_actions": audit_actions[:200],
            "settings_map": settings_map,
            "company_email_domain": settings_map.get("company_email_domain", ""),
        },
    )


@login_required
def admin_account_request_decision(request, pk):
    if not admin_only(request):
        messages.error(request, "Action reservee aux administrateurs.")
        return redirect("dashboard")
    account_request = get_object_or_404(AccountCreationRequest.objects.select_related("employee"), pk=pk)
    if request.method != "POST":
        return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")
    if account_request.status != AccountCreationRequest.STATUS_PENDING:
        messages.info(request, "Cette demande a deja ete traitee.")
        return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")
    action = request.POST.get("action")
    note = (request.POST.get("admin_note") or "").strip()
    admin_profile = request.user.profile
    if action == "approve":
        if User.objects.filter(Q(username__iexact=account_request.email) | Q(email__iexact=account_request.email), is_active=True).exists():
            messages.error(request, "Un compte actif existe deja pour cet email.")
            return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")
        if account_request.employee and UtilisateurProfile.objects.filter(employe=account_request.employee, actif=True).exists():
            messages.error(request, "Cet employe est deja lie a un compte actif.")
            return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")
        user = User(username=account_request.email, email=account_request.email, first_name=account_request.first_name, last_name=account_request.last_name, is_active=True)
        user.password = account_request.password_hash
        user.save()
        UtilisateurProfile.objects.create(user=user, role=Role.EMPLOYE, employe=account_request.employee, actif=True)
        account_request.user = user
        account_request.status = AccountCreationRequest.STATUS_APPROVED
        messages.success(request, "Demande approuvee et compte active.")
    elif action == "deny":
        account_request.status = AccountCreationRequest.STATUS_DENIED
        messages.success(request, "Demande refusee.")
    else:
        messages.error(request, "Decision invalide.")
        return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")
    account_request.admin_note = note
    account_request.decided_at = timezone.now()
    account_request.decided_by = admin_profile
    account_request.save(update_fields=["user", "status", "admin_note", "decided_at", "decided_by"])
    HistoriqueAction.objects.create(action=f"ACCOUNT_REQUEST_{account_request.status.upper()}", details=account_request.email, utilisateur=admin_profile, entite_concernee="AccountCreationRequest", entite_id=account_request.pk)
    return redirect(f"{reverse('admin_dashboard')}?tab=account_requests")


@login_required
def admin_user_update(request, pk):
    if not admin_only(request):
        messages.error(request, "Action reservee aux administrateurs.")
        return redirect("dashboard")
    user = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    if request.method != "POST":
        return redirect(f"{reverse('admin_dashboard')}?tab=users")
    role = request.POST.get("role")
    active = request.POST.get("active") == "on"
    if role not in dict(Role.choices):
        messages.error(request, "Role invalide.")
        return redirect(f"{reverse('admin_dashboard')}?tab=users")
    if user.pk == request.user.pk and role != Role.ADMIN:
        messages.error(request, "Vous ne pouvez pas retirer votre propre role admin.")
        return redirect(f"{reverse('admin_dashboard')}?tab=users")
    user.is_active = active
    user.save(update_fields=["is_active"])
    user.profile.role = role
    user.profile.actif = active
    user.profile.save(update_fields=["role", "actif"])
    HistoriqueAction.objects.create(action="ADMIN_USER_UPDATE", details=f"{user.username} -> {role} / actif={active}", utilisateur=request.user.profile, entite_concernee="UtilisateurProfile", entite_id=user.profile.pk)
    messages.success(request, "Utilisateur mis a jour.")
    return redirect(f"{reverse('admin_dashboard')}?tab=users")


@login_required
def admin_settings_save(request):
    if not admin_only(request):
        messages.error(request, "Action reservee aux administrateurs.")
        return redirect("dashboard")
    if request.method == "POST":
        domain = (request.POST.get("company_email_domain") or "").strip().lower().lstrip("@")
        AdminSetting.objects.update_or_create(key="company_email_domain", defaults={"value": domain})
        HistoriqueAction.objects.create(action="ADMIN_SETTING_UPDATE", details=f"company_email_domain={domain or 'non defini'}", utilisateur=request.user.profile, entite_concernee="AdminSetting")
        messages.success(request, "Parametres enregistres.")
    return redirect(f"{reverse('admin_dashboard')}?tab=settings")


@csrf_exempt
def chatbot_api(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "message": "Method not allowed."}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "session_expired", "message": "Your session has expired. Please log in again."}, status=401)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        result = assistant_response(request.user, payload.get("message", ""))
        return JsonResponse({"ok": True, "data": result})
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "Invalid JSON payload."}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=403)
    except ValidationError as exc:
        message = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "message": message}, status=400)
    except Exception:
        return JsonResponse({"ok": False, "message": "I could not reach the assistant service right now. Please try again."}, status=500)
