from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import Role, UtilisateurProfile

from .models import (
    AffectationMateriel,
    CommandeProduit,
    ComptePoints,
    Employe,
    HistoriqueAction,
    MouvementSoldeConge,
    Notification,
    ParametrePointage,
    PlanningShift,
    Pointage,
    SoldeConge,
    TransactionPoints,
    TypeConge,
)


def current_profile(request):
    return getattr(request.user, "profile", None) if request.user.is_authenticated else None


def audit(request, action, details="", entite="", entite_id=None):
    # TRAITEMENT AUDIT — enregistre l'action importante avec utilisateur, module et objet concerne.
    HistoriqueAction.objects.create(
        action=action,
        details=details,
        utilisateur=current_profile(request),
        entite_concernee=entite,
        entite_id=entite_id,
        date_action=timezone.now(),
    )


def notify(profile, message, lien=""):
    # TRAITEMENT NOTIFICATION — cree une notification individuelle non lue par defaut.
    if profile:
        Notification.objects.create(destinataire=profile, message=message, lien=lien, date_envoi=timezone.now())


def profiles_for_employee(employe):
    if not employe:
        return UtilisateurProfile.objects.none()
    return UtilisateurProfile.objects.filter(employe=employe, actif=True)


def notify_employee(employe, message, lien=""):
    for profile in profiles_for_employee(employe):
        notify(profile, message, lien)


def notify_role(role, message, lien=""):
    for profile in UtilisateurProfile.objects.filter(role=role, actif=True):
        notify(profile, message, lien)


def notify_rh_and_admin(message, lien=""):
    for role in (Role.RESPONSABLE_RH, Role.ADMIN):
        notify_role(role, message, lien)


def audit_profile(profile, action, details="", entite="", entite_id=None):
    HistoriqueAction.objects.create(
        action=action,
        details=details,
        utilisateur=profile,
        entite_concernee=entite,
        entite_id=entite_id,
        date_action=timezone.now(),
    )


@transaction.atomic
def appliquer_transaction_points(employe, type_transaction, points, source, description, cree_par=None, objet_lie=""):
    # TRAITEMENT POINTS — applique une transaction atomique sans permettre un solde negatif.
    if not employe:
        raise ValidationError("Employe obligatoire pour la transaction de points.")
    if points == 0:
        raise ValidationError("Le mouvement de points ne peut pas etre nul.")
    compte, _ = ComptePoints.objects.select_for_update().get_or_create(employe=employe, defaults={"solde_points": 0})
    signed_points = abs(points)
    if type_transaction in {"deduction", "achat"}:
        signed_points = -signed_points
    solde_avant = compte.solde_points
    solde_apres = solde_avant + signed_points
    if solde_apres < 0:
        raise ValidationError("Le solde de points ne peut pas devenir negatif.")
    compte.solde_points = solde_apres
    compte.full_clean()
    compte.save(update_fields=["solde_points"])
    tx = TransactionPoints.objects.create(
        employe=employe,
        type_transaction=type_transaction,
        source=source,
        points=signed_points,
        solde_avant=solde_avant,
        solde_apres=solde_apres,
        description=description,
        cree_par=cree_par,
        objet_lie=objet_lie,
    )
    audit_profile(cree_par, "TRANSACTION_POINTS", description, "TransactionPoints", tx.pk)
    return tx


def parametre_pointage_actif():
    return ParametrePointage.objects.filter(actif=True).order_by("-id").first() or ParametrePointage.objects.create()


def shift_planifie_actuel(employe, now=None):
    now = now or timezone.now()
    window_start = now - timezone.timedelta(hours=2)
    window_end = now + timezone.timedelta(hours=12)
    shift = (
        PlanningShift.objects.filter(
            employe=employe,
            statut="publie",
            plan_type="normal",
            date_debut__lte=window_end,
            date_fin__gte=window_start,
        )
        .order_by("date_debut")
        .first()
    )
    if shift:
        return shift
    today = timezone.localdate(now)
    return shift_permanent_for_day(employe, today)


def shift_permanent_for_day(employe, day):
    if not employe:
        return None
    weekday = day.weekday()
    candidates = PlanningShift.objects.filter(
        employe=employe,
        plan_type="permanent",
        statut="publie",
        date_debut__date__lte=day,
    ).order_by("-date_debut")
    for shift in candidates:
        delta_days = (day - shift.date_debut.date()).days
        if shift.recurrence_rule == "daily":
            return shift
        if shift.recurrence_rule == "weekdays" and weekday >= 5:
            continue
        if shift.recurrence_rule == "weekly" and shift.date_debut.weekday() != weekday:
            continue
        if shift.recurrence_rule == "biweekly" and (shift.date_debut.weekday() != weekday or delta_days % 14 != 0):
            continue
        if shift.recurrence_rule == "monthly" and shift.date_debut.day != day.day:
            continue
        return shift
    return None


def planned_window_for_pointage(pointage, param):
    if pointage.shift:
        local_shift_start = timezone.localtime(pointage.shift.date_debut)
        start = timezone.make_aware(timezone.datetime.combine(pointage.date, local_shift_start.time()))
        end_time = pointage.shift.effective_end_time
        if end_time:
            end = timezone.make_aware(timezone.datetime.combine(pointage.date, end_time))
            if end <= start:
                end += timezone.timedelta(days=1)
            return start, end
    start = timezone.make_aware(timezone.datetime.combine(pointage.date, param.heure_debut_officielle))
    end = timezone.make_aware(timezone.datetime.combine(pointage.date, param.heure_fin_officielle))
    if end <= start:
        end += timezone.timedelta(days=1)
    return start, end


@transaction.atomic
def pointer_entree(employe):
    # TRAITEMENT POINTAGE — empeche un double pointage d'entree dans la meme journee.
    today = timezone.localdate()
    if Pointage.objects.filter(employe=employe, date=today, heure_sortie__isnull=True).exists():
        raise ValidationError("Un pointage ouvert existe deja aujourd'hui.")
    if Pointage.objects.filter(employe=employe, date=today).exists():
        raise ValidationError("Vous avez deja pointe aujourd'hui.")
    now = timezone.now()
    pointage = Pointage(employe=employe, shift=shift_planifie_actuel(employe, now), date=today, heure_entree=now, statut="incomplet")
    pointage.full_clean()
    pointage.save()
    return pointage


@transaction.atomic
def pointer_sortie(employe):
    # TRAITEMENT POINTAGE — calcule heures, retard, sortie anticipee, bonus/penalite de points.
    pointage = Pointage.objects.select_for_update().filter(employe=employe, date=timezone.localdate(), heure_sortie__isnull=True).first()
    if not pointage:
        raise ValidationError("Aucun pointage d'entree ouvert pour aujourd'hui.")
    now = timezone.now()
    if now < pointage.heure_entree:
        raise ValidationError("La sortie ne peut pas etre avant l'entree.")
    param = parametre_pointage_actif()
    pointage.heure_sortie = now
    seconds = (pointage.heure_sortie - pointage.heure_entree).total_seconds()
    pointage.total_heures = round(seconds / 3600, 2)
    planned_start, planned_end = planned_window_for_pointage(pointage, param)
    start_limit = planned_start + timezone.timedelta(minutes=param.tolerance_retard_minutes)
    expected_hours = max(0, (planned_end - planned_start).total_seconds() / 3600 - ((pointage.shift.pause_minutes if pointage.shift else 0) / 60))
    points = param.points_presence_normale
    statut = "present"
    if pointage.heure_entree > start_limit:
        points -= param.penalite_retard
        statut = "retard"
    if pointage.heure_sortie < planned_end:
        points -= param.penalite_sortie_anticipee
        statut = "sortie_anticipee" if statut == "present" else statut
    elif pointage.total_heures > expected_hours:
        points += param.bonus_heures_supplementaires
    missing_hours = max(0, round(expected_hours - float(pointage.total_heures or 0), 2))
    late_minutes = max(0, int((pointage.heure_entree - planned_start).total_seconds() / 60))
    early_minutes = max(0, int((planned_end - pointage.heure_sortie).total_seconds() / 60))
    pointage.statut = statut
    pointage.points_calcules = points
    pointage.commentaire = (
        f"Planning: {planned_start.strftime('%H:%M')}-{planned_end.strftime('%H:%M')}; "
        f"retard {late_minutes} min; sortie anticipee {early_minutes} min; "
        f"heures manquantes {missing_hours:.2f}."
    )
    pointage.full_clean()
    pointage.save()
    if pointage.shift and pointage.shift.plan_type == "normal" and pointage.shift.statut == "publie" and pointage.shift.date_fin and pointage.heure_sortie >= pointage.shift.date_fin:
        pointage.shift.statut = "termine"
        pointage.shift.save(update_fields=["statut", "updated_at"])
    if points:
        appliquer_transaction_points(
            employe,
            "gain" if points >= 0 else "deduction",
            abs(points),
            "pointage",
            f"Pointage du {pointage.date}",
            objet_lie=f"Pointage:{pointage.pk}",
        )
    return pointage


@transaction.atomic
def deduire_solde_conge(demande, cree_par=None):
    # TRAITEMENT SOLDE CONGE — deduit le solde uniquement si les jours disponibles suffisent.
    if demande.type == TypeConge.SANS_SOLDE:
        audit_profile(cree_par, "VALIDATION_CONGE_SANS_SOLDE", "Validation sans deduction du solde", "DemandeConge", demande.pk)
        return
    solde, _ = SoldeConge.objects.select_for_update().get_or_create(employe=demande.employe)
    jours = demande.duree_jours
    if solde.jours_disponibles < jours:
        raise ValidationError("Solde de conges insuffisant.")
    avant = solde.jours_disponibles
    solde.jours_disponibles -= jours
    solde.jours_utilises += jours
    solde.full_clean()
    solde.save()
    MouvementSoldeConge.objects.create(solde=solde, demande=demande, type_mouvement="deduction", jours=jours, solde_avant=avant, solde_apres=solde.jours_disponibles, cree_par=cree_par)
    audit_profile(cree_par, "DEDUCTION_SOLDE_CONGE", f"{jours} jour(s) deduit(s)", "DemandeConge", demande.pk)


@transaction.atomic
def rembourser_solde_conge(demande, cree_par=None):
    # TRAITEMENT SOLDE CONGE — rembourse le solde apres annulation d'un conge valide.
    if demande.type == TypeConge.SANS_SOLDE:
        audit_profile(cree_par, "ANNULATION_CONGE_SANS_SOLDE", "Annulation sans remboursement du solde", "DemandeConge", demande.pk)
        return
    solde, _ = SoldeConge.objects.select_for_update().get_or_create(employe=demande.employe)
    jours = demande.duree_jours
    avant = solde.jours_disponibles
    solde.jours_disponibles += jours
    solde.jours_utilises = max(0, solde.jours_utilises - jours)
    solde.save()
    MouvementSoldeConge.objects.create(solde=solde, demande=demande, type_mouvement="remboursement", jours=jours, solde_avant=avant, solde_apres=solde.jours_disponibles, cree_par=cree_par)
    audit_profile(cree_par, "REMBOURSEMENT_SOLDE_CONGE", f"{jours} jour(s) rembourse(s)", "DemandeConge", demande.pk)


@transaction.atomic
def approuver_commande(commande, valide_par):
    # TRAITEMENT BOUTIQUE — valide stock, deduit les points et diminue le stock une seule fois.
    commande = CommandeProduit.objects.select_for_update().select_related("produit", "employe").get(pk=commande.pk)
    if commande.statut != "en_attente":
        raise ValidationError("Cette commande n'est plus en attente.")
    produit = commande.produit
    if produit.stock_disponible < commande.quantite:
        raise ValidationError("Stock insuffisant.")
    cout = produit.cout_points * commande.quantite
    appliquer_transaction_points(commande.employe, "achat", cout, "boutique", f"Commande {produit.nom}", valide_par, f"CommandeProduit:{commande.pk}")
    produit.stock_disponible -= commande.quantite
    produit.save(update_fields=["stock_disponible"])
    commande.cout_total_points = cout
    commande.statut = "approuvee"
    commande.points_deduits = True
    commande.date_validation = timezone.now()
    commande.valide_par = valide_par
    commande.full_clean()
    commande.save()
    audit_profile(valide_par, "APPROBATION_COMMANDE", f"Commande approuvee: {produit.nom}", "CommandeProduit", commande.pk)
    notify_employee(commande.employe, "Votre commande materiel a ete approuvee.", "/boutique")
    return commande


@transaction.atomic
def refuser_ou_annuler_commande(commande, statut, valide_par=None, motif=""):
    # TRAITEMENT BOUTIQUE — rembourse les points et le stock si une commande deja deduite est annulee/refusee.
    commande = CommandeProduit.objects.select_for_update().select_related("produit", "employe").get(pk=commande.pk)
    if statut not in {"refusee", "annulee"}:
        raise ValidationError("Statut de commande invalide.")
    if commande.statut in {"refusee", "annulee", "livree"}:
        raise ValidationError("Cette commande ne peut plus etre modifiee.")
    if commande.points_deduits:
        appliquer_transaction_points(commande.employe, "remboursement", commande.cout_total_points, "boutique", f"Remboursement commande {commande.produit.nom}", valide_par, f"CommandeProduit:{commande.pk}")
        commande.produit.stock_disponible += commande.quantite
        commande.produit.save(update_fields=["stock_disponible"])
        commande.points_deduits = False
    commande.statut = statut
    commande.motif_refus = motif
    commande.date_validation = timezone.now()
    commande.valide_par = valide_par
    commande.full_clean()
    commande.save()
    audit_profile(valide_par, "MISE_A_JOUR_COMMANDE", f"Commande {commande.produit.nom} -> {statut}", "CommandeProduit", commande.pk)
    notify_employee(commande.employe, "Votre commande materiel a ete mise a jour.", "/boutique")
    return commande


@transaction.atomic
def livrer_commande(commande, valide_par):
    commande = CommandeProduit.objects.select_for_update().select_related("produit", "employe").get(pk=commande.pk)
    # TRAITEMENT BOUTIQUE — seule une commande approuvee peut etre livree et affectee en materiel.
    if commande.statut != "approuvee":
        raise ValidationError("Seule une commande approuvee peut etre livree.")
    commande.statut = "livree"
    commande.date_validation = timezone.now()
    commande.valide_par = valide_par
    commande.full_clean()
    commande.save()
    AffectationMateriel.objects.create(employe=commande.employe, produit=commande.produit, quantite=commande.quantite, attribue_par=valide_par, statut="livre")
    notify_employee(commande.employe, "Votre materiel a ete livre.", "/boutique")
    audit_profile(valide_par, "LIVRAISON_COMMANDE", "Commande livree", "CommandeProduit", commande.pk)
    return commande


def hierarchy_level_for(employe):
    rank = employe.poste.rang_hierarchique if employe.poste else 99
    label = employe.poste.niveau if employe.poste and employe.poste.niveau else "Collaborateur"
    if employe.poste and employe.poste.est_direction or rank <= 5:
        return "direction", "Direction generale"
    if rank <= 30:
        return "directeur", label or "Direction"
    if employe.poste and employe.poste.est_manager or rank <= 55:
        return "manager", label or "Manager"
    if rank <= 70:
        return "lead", label or "Chef d'equipe"
    return "standard", label


def build_hierarchy_tree(departement_id=None, search="", show_all=False, managers_only=True, max_rank=70):
    # TRAITEMENT HIERARCHIE — construit l'arbre visible en evitant les cycles pendant le rendu.
    employees = list(
        Employe.objects.filter(actif=True)
        .select_related("departement", "service", "poste", "responsable")
        .order_by("poste__rang_hierarchique", "nom", "prenom")
    )
    by_id = {employee.pk: employee for employee in employees}
    children_by_parent = {}
    for employee in employees:
        children_by_parent.setdefault(employee.responsable_id, []).append(employee)

    def rank_of(employee):
        return employee.poste.rang_hierarchique if employee.poste else 99

    visible_ids = set()
    search = (search or "").strip().lower()
    for employee in employees:
        child_count = len(children_by_parent.get(employee.pk, []))
        matches_department = not departement_id or str(employee.departement_id or "") == str(departement_id)
        matches_search = (
            not search
            or search in employee.nom_complet.lower()
            or search in (employee.email or "").lower()
            or search in (employee.matricule or "").lower()
            or search in (employee.poste.libelle.lower() if employee.poste else "")
        )
        is_structural = show_all or rank_of(employee) <= max_rank or child_count > 0
        if managers_only and not show_all:
            is_structural = is_structural and (child_count > 0 or rank_of(employee) <= max_rank)
        if matches_department and matches_search and is_structural:
            visible_ids.add(employee.pk)
            manager = employee.responsable
            while manager:
                visible_ids.add(manager.pk)
                manager = manager.responsable

    if not visible_ids and search:
        for employee in employees:
            if search in employee.nom_complet.lower():
                visible_ids.add(employee.pk)

    def sort_key(employee):
        return (rank_of(employee), employee.nom, employee.prenom)

    def make_node(employee, path=None):
        path = path or set()
        if employee.pk in path:
            return None
        level_class, level_label = hierarchy_level_for(employee)
        child_nodes = []
        for child in sorted(children_by_parent.get(employee.pk, []), key=sort_key):
            if child.pk in visible_ids:
                node = make_node(child, path | {employee.pk})
                if node:
                    child_nodes.append(node)
        return {"employee": employee, "children": child_nodes, "level_class": level_class, "level_label": level_label}

    roots = []
    for employee in sorted([employee for employee in employees if employee.pk in visible_ids], key=sort_key):
        if not employee.responsable_id or employee.responsable_id not in visible_ids:
            node = make_node(employee)
            if node:
                roots.append(node)

    non_affectes = [make_node(employee) for employee in sorted(employees, key=sort_key) if employee.pk in visible_ids and employee.responsable_id and employee.responsable_id not in by_id]
    return {
        "roots": roots,
        "visible_count": len(visible_ids),
        "total_count": len(employees),
        "non_affectes": [node for node in non_affectes if node],
    }
