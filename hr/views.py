import csv
import json
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Q
from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import Concat
from django.db.models import Value
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Role

from .forms import (
    DemandeAdministrativeForm,
    DemandeCongeForm,
    DepartementForm,
    EmployeForm,
    ActualiteForm,
    AffectationFormationForm,
    AjustementPointsManuelForm,
    CommandeProduitForm,
    ConversationRHForm,
    ConversationRHCloseForm,
    ConversationRHParticipantForm,
    ConversationRHRatingForm,
    ConversationRHRenameForm,
    FormationForm,
    GestionPosteForm,
    MessageRHForm,
    PlanningBulkForm,
    PlanningShiftForm,
    ProduitForm,
    ReclamationRHForm,
    RemunerationForm,
    TacheEquipeForm,
    TacheEquipeMessageForm,
    TraitementReclamationForm,
    PosteForm,
    ServiceForm,
)
from .models import (
    Actualite,
    ActualitePieceJointe,
    AffectationFormation,
    AffectationMateriel,
    CategorieProduit,
    CommandeProduit,
    ComptePoints,
    ConversationRH,
    DemandeAdministrative,
    DemandeConge,
    Departement,
    Document,
    Employe,
    Formation,
    HistoriqueAction,
    MessageRH,
    Notification,
    PlanningShift,
    Poste,
    Produit,
    ReclamationRH,
    Remuneration,
    SoldeConge,
    TacheEquipe,
    TacheEquipeMessage,
    TransactionPoints,
    SupportRHReward,
    Pointage,
    Service,
    StatutDemande,
    TypeConge,
)
from .permissions import can_manage_hr, can_view_employees, has_any_role, role_required
from .planning_assistant import handle_planning_assistant
from .planning_services import (
    available_employees,
    bulk_create_shifts,
    change_shift_status,
    conflict_list,
    copy_planning,
    create_shift as create_planning_shift,
    grid_context,
    move_shift,
    parse_day,
    pointage_breakdown,
    planning_queryset_for_profile,
    planning_summary,
    resize_shift,
    serialize_employee,
    serialize_shift,
    shift_occurs_on,
    update_shift as update_planning_shift,
)
from .services import (
    appliquer_transaction_points,
    approuver_commande,
    audit,
    audit_profile,
    build_hierarchy_tree,
    deduire_solde_conge,
    livrer_commande,
    notify,
    notify_employee,
    notify_rh_and_admin,
    pointer_entree,
    pointer_sortie,
    refuser_ou_annuler_commande,
    shift_planifie_actuel,
)


DOCUMENT_EXTENSION_VALIDATOR = FileExtensionValidator(
    allowed_extensions=["pdf", "doc", "docx", "jpg", "jpeg", "png"]
)
PHOTO_EXTENSION_VALIDATOR = FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])
MAX_UPLOAD_SIZE = 5 * 1024 * 1024


def profile(request):
    return getattr(request.user, "profile", None)


def direct_report_filter(manager):
    return Q(pk=manager.pk) | Q(responsable=manager)


def validate_uploaded_file(uploaded_file, validator):
    # TRAITEMENT DOCUMENT — controle taille maximale et extension autorisee.
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValidationError("La taille du fichier ne doit pas depasser 5 Mo.")
    validator(uploaded_file)


def employee_name_search_q(search):
    terms = [term for term in search.split() if term]
    query = Q(nom__icontains=search) | Q(prenom__icontains=search)
    for term in terms:
        query |= Q(nom__icontains=term) | Q(prenom__icontains=term)
    return query


def attach_message_file(message, uploaded_file):
    if not uploaded_file:
        return message
    validate_uploaded_file(uploaded_file, DOCUMENT_EXTENSION_VALIDATOR)
    message.piece_jointe = uploaded_file
    message.nom_piece_jointe = Path(uploaded_file.name).name[:255]
    return message


def attach_task_file(obj, uploaded_file):
    if not uploaded_file:
        return obj
    validate_uploaded_file(uploaded_file, DOCUMENT_EXTENSION_VALIDATOR)
    obj.piece_jointe = uploaded_file
    obj.nom_piece_jointe = Path(uploaded_file.name).name[:255]
    return obj


@login_required
def employes_list(request):
    if not can_view_employees(request.user):
        messages.error(request, "Vous n'etes pas autorise a acceder aux employes.")
        return redirect("dashboard")
    search = request.GET.get("search", "").strip()
    employes = accessible_employees(profile(request)).select_related("departement", "service", "poste", "responsable")
    if search:
        employes = employes.annotate(
            full_name=Concat("prenom", Value(" "), "nom"),
            display_name=Concat("nom", Value(" "), "prenom"),
        ).filter(
            employee_name_search_q(search)
            | Q(full_name__icontains=search)
            | Q(display_name__icontains=search)
            | Q(email__icontains=search)
            | Q(matricule__icontains=search)
            | Q(departement__libelle__icontains=search)
            | Q(poste__libelle__icontains=search)
        )
    return render(request, "employes/list.html", {"page_title": "Employes", "employes": employes, "search": search})


@login_required
def hierarchy_tree(request):
    departement_id = request.GET.get("departement") or None
    search = request.GET.get("search", "").strip()
    show_all = request.GET.get("afficher") == "tous"
    tree = build_hierarchy_tree(departement_id=departement_id, search=search, show_all=show_all)
    return render(
        request,
        "employes/hierarchy.html",
        {
            "page_title": "Arbre hierarchique",
            "tree": tree,
            "departements": Departement.objects.all(),
            "departement_filtre": departement_id,
            "search": search,
            "show_all": show_all,
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def position_management(request):
    # TRAITEMENT PERMISSION — seuls ADMIN et RESPONSABLE_RH gerent les postes.
    employes = Employe.objects.filter(actif=True).select_related("departement", "service", "poste", "responsable")
    search = request.GET.get("search", "").strip()
    if search:
        employes = employes.filter(Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(matricule__icontains=search) | Q(email__icontains=search))
    if request.GET.get("departement"):
        employes = employes.filter(departement_id=request.GET["departement"])
    if request.GET.get("poste"):
        employes = employes.filter(poste_id=request.GET["poste"])
    if request.GET.get("manager"):
        employes = employes.filter(responsable_id=request.GET["manager"])
    return render(request, "employes/positions.html", {"page_title": "Gestion des postes", "employes": employes[:80], "departements": Departement.objects.all(), "postes": Poste.objects.all(), "search": search})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def position_edit(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    user_profile = profile(request)
    if user_profile and employe.pk == user_profile.employe_id and user_profile.role != Role.ADMIN:
        messages.error(request, "Un responsable RH ne peut pas modifier sa propre affectation.")
        return redirect("position_management")
    if request.method == "POST":
        form = GestionPosteForm(request.POST, instance=employe)
        if form.is_valid():
            before = f"{employe.poste} / {employe.departement} / {employe.responsable}"
            saved = form.save()
            audit(request, "CHANGEMENT_POSTE", f"{saved.nom_complet}: {before} -> {saved.poste} / {saved.departement} / {saved.responsable}", "Employe", saved.pk)
            notify_employee(saved, "Votre affectation de poste a ete mise a jour.", "/employes/arbre")
            messages.success(request, "Affectation mise a jour.")
            return redirect("position_management")
    else:
        form = GestionPosteForm(instance=employe)
    return render(request, "employes/position_form.html", {"page_title": "Modifier l'affectation", "form": form, "employe": employe})


@login_required
def employe_detail(request, pk):
    if not can_view_employees(request.user):
        messages.error(request, "Vous n'etes pas autorise a acceder aux employes.")
        return redirect("dashboard")
    employe = get_object_or_404(
        accessible_employees(profile(request)).select_related("departement", "service", "poste", "responsable"),
        pk=pk,
    )
    return render(
        request,
        "employes/detail.html",
        {
            "page_title": "Detail employe",
            "employe": employe,
            "conges": employe.conges.all(),
            "documents": employe.documents.all(),
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def employe_create(request):
    return render(request, "employes/form.html", {"page_title": "Nouvel employe", "form": EmployeForm(), "employe": None})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def employe_update(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    return render(request, "employes/form.html", {"page_title": "Modifier employe", "form": EmployeForm(instance=employe), "employe": employe})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def employe_save(request):
    pk = request.POST.get("id")
    employe = get_object_or_404(Employe, pk=pk) if pk else None
    form = EmployeForm(request.POST, request.FILES, instance=employe)
    if form.is_valid():
        if employe and "date_naissance" not in form.changed_data:
            form.instance.date_naissance = employe.date_naissance
        if employe and "date_embauche" not in form.changed_data:
            form.instance.date_embauche = employe.date_embauche
        saved = form.save(commit=False)
        if not saved.pk:
            saved.actif = True
        saved.save()
        photo = request.FILES.get("photoFile")
        if photo:
            try:
                validate_uploaded_file(photo, PHOTO_EXTENSION_VALIDATOR)
            except ValidationError as exc:
                form.add_error(None, exc)
                return render(request, "employes/form.html", {"page_title": "Employe", "form": form, "employe": employe})
            saved.photo = photo
            saved.save(update_fields=["photo"])
        audit(request, "CREATION_EMPLOYE" if not employe else "MODIFICATION_EMPLOYE", f"Employe {saved.nom_complet}", "Employe", saved.pk)
        messages.success(request, "Employe enregistre avec succes.")
        return redirect("employe_detail", pk=saved.pk)
    return render(request, "employes/form.html", {"page_title": "Employe", "form": form, "employe": employe})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def employe_archive(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    employe.actif = False
    employe.save(update_fields=["actif", "updated_at"])
    audit(request, "ARCHIVAGE_EMPLOYE", f"Archivage de {employe.nom_complet}", "Employe", employe.pk)
    messages.success(request, "Employe archive avec succes.")
    return redirect("employes_list")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def employe_photo(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    photo = request.FILES.get("photoFile")
    if photo:
        try:
            validate_uploaded_file(photo, PHOTO_EXTENSION_VALIDATOR)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("employe_detail", pk=pk)
        employe.photo = photo
        employe.save(update_fields=["photo", "updated_at"])
        audit(request, "UPLOAD_PHOTO", f"Photo ajoutee pour {employe.nom_complet}", "Employe", employe.pk)
        messages.success(request, "Photo mise a jour.")
    return redirect("employe_detail", pk=pk)


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def departements_list(request):
    active_tab = request.GET.get("tab", "departements")
    if active_tab not in {"departements", "services", "postes", "creation"}:
        active_tab = "departements"
    niveaux = [
        niveau.strip()
        for niveau in Poste.objects.exclude(niveau="")
        .values_list("niveau", flat=True)
        .distinct()
        if niveau and niveau.strip()
    ]
    niveaux = sorted({niveau[:1].upper() + niveau[1:] for niveau in niveaux}, key=str.lower)
    return render(
        request,
        "departements/list.html",
        {
            "page_title": "Departements",
            "departements": Departement.objects.all(),
            "services": Service.objects.select_related("departement"),
            "postes": Poste.objects.all(),
            "departement_form": DepartementForm(),
            "service_form": ServiceForm(),
            "poste_form": PosteForm(),
            "niveaux": niveaux,
            "active_tab": active_tab,
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def departement_create(request):
    return render(request, "departements/form.html", {"page_title": "Nouveau departement", "form": DepartementForm(), "departement": None})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def departement_update(request, pk):
    departement = get_object_or_404(Departement, pk=pk)
    return render(request, "departements/form.html", {"page_title": "Modifier departement", "form": DepartementForm(instance=departement), "departement": departement})


def redirect_with_tab(redirect_name, tab):
    return redirect(f"{reverse(redirect_name)}?tab={tab}")


def save_model_form(request, form_class, model_name, success_message, redirect_name, tab="creation"):
    pk = request.POST.get("id")
    try:
        instance = form_class.Meta.model.objects.filter(pk=pk).first() if pk else None
        if pk and not instance:
            messages.error(request, "L'element a modifier est introuvable.")
            return redirect_with_tab(redirect_name, tab)
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            audit(request, f"SAVE_{model_name.upper()}", f"{model_name} {saved}", model_name, saved.pk)
            messages.success(request, success_message)
        else:
            errors = []
            for field_errors in form.errors.values():
                errors.extend(field_errors)
            messages.error(request, " ".join(errors) or "Veuillez corriger les champs obligatoires.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except Exception:
        messages.error(request, "Une erreur inattendue est survenue pendant l'enregistrement.")
    return redirect_with_tab(redirect_name, tab)


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def departement_save(request):
    return save_model_form(request, DepartementForm, "Departement", "Departement enregistre avec succes.", "departements_list", "creation")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def service_save(request):
    return save_model_form(request, ServiceForm, "Service", "Service enregistre avec succes.", "departements_list", "creation")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def poste_save(request):
    return save_model_form(request, PosteForm, "Poste", "Poste enregistre avec succes.", "departements_list", "creation")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def departement_delete(request, pk):
    departement = get_object_or_404(Departement, pk=pk)
    audit(request, "SUPPRESSION_DEPARTEMENT", f"Suppression du departement {departement.libelle}", "Departement", departement.pk)
    departement.delete()
    messages.success(request, "Departement supprime.")
    return redirect_with_tab("departements_list", "departements")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk)
    audit(request, "SUPPRESSION_SERVICE", f"Suppression du service {service.libelle}", "Service", service.pk)
    service.delete()
    messages.success(request, "Service supprime.")
    return redirect_with_tab("departements_list", "services")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def poste_delete(request, pk):
    poste = get_object_or_404(Poste, pk=pk)
    audit(request, "SUPPRESSION_POSTE", f"Suppression du poste {poste.libelle}", "Poste", poste.pk)
    poste.delete()
    messages.success(request, "Poste supprime.")
    return redirect_with_tab("departements_list", "postes")


def conges_for_profile(user_profile):
    # TRAITEMENT PERMISSION CONGE — RH voit tout, manager voit son equipe, employe voit ses demandes.
    if not user_profile or not user_profile.employe:
        return DemandeConge.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return DemandeConge.objects.select_related("employe", "employe__responsable", "traitee_par", "manager_approved_by", "hr_approved_by")
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return DemandeConge.objects.filter(employe__responsable=user_profile.employe).select_related("employe", "employe__responsable", "traitee_par", "manager_approved_by", "hr_approved_by")
    return DemandeConge.objects.filter(employe=user_profile.employe).select_related("employe", "employe__responsable", "traitee_par", "manager_approved_by", "hr_approved_by")


@login_required
def conges_list(request):
    demandes = conges_for_profile(profile(request))
    statut = request.GET.get("statut")
    type_conge = request.GET.get("type")
    if statut:
        demandes = demandes.filter(statut=statut)
    if type_conge:
        demandes = demandes.filter(type=type_conge)
    return render(
        request,
        "conges/list.html",
        {"page_title": "Conges & Absences", "demandes": demandes, "statuts": StatutDemande.choices, "types": TypeConge.choices, "statut_filtre": statut, "type_filtre": type_conge},
    )


@login_required
def conge_create(request):
    user_profile = profile(request)
    employee = user_profile.employe if user_profile else None
    solde = SoldeConge.objects.get_or_create(employe=employee)[0] if employee else None
    return render(request, "conges/form.html", {"page_title": "Nouvelle demande de conge", "form": DemandeCongeForm(employee=employee), "solde_conge": solde})


@login_required
@require_POST
def conge_submit(request):
    user_profile = profile(request)
    if not user_profile or not user_profile.employe:
        messages.error(request, "Aucun employe n'est lie a votre compte.")
        return redirect("conges_list")
    form = DemandeCongeForm(request.POST, request.FILES, employee=user_profile.employe)
    if form.is_valid():
        justificatif = request.FILES.get("justificatif")
        if form.cleaned_data.get("type") in {TypeConge.MALADIE, TypeConge.MATERNITE} and not justificatif:
            form.add_error(None, "Un justificatif est obligatoire pour un conge maladie ou maternite.")
            solde = SoldeConge.objects.get_or_create(employe=user_profile.employe)[0]
            return render(request, "conges/form.html", {"page_title": "Nouvelle demande de conge", "form": form, "solde_conge": solde})
        demande = form.save(commit=False)
        demande.employe = user_profile.employe
        demande.statut = StatutDemande.EN_ATTENTE
        demande.date_creation = timezone.now()
        demande.save()
        if justificatif:
            try:
                validate_uploaded_file(justificatif, DOCUMENT_EXTENSION_VALIDATOR)
            except ValidationError as exc:
                form.add_error(None, exc)
                demande.delete()
                solde = SoldeConge.objects.get_or_create(employe=user_profile.employe)[0]
                return render(request, "conges/form.html", {"page_title": "Nouvelle demande de conge", "form": form, "solde_conge": solde})
            create_document(request, justificatif, "Justificatif conge", user_profile.employe, None)
        if user_profile.employe.responsable:
            manager_profile = getattr(user_profile.employe.responsable, "utilisateur_profile", None)
            notify(manager_profile, f"Nouvelle demande de conge de {user_profile.employe.nom_complet}", "/conges")
        audit(request, "SOUMISSION_CONGE", f"Demande de conge soumise par {user_profile.employe.nom_complet}", "DemandeConge", demande.pk)
        messages.success(request, "Demande de conge envoyee avec succes.")
        return redirect("conges_list")
    solde = SoldeConge.objects.get_or_create(employe=user_profile.employe)[0]
    return render(request, "conges/form.html", {"page_title": "Nouvelle demande de conge", "form": form, "solde_conge": solde})


def can_process_conge(user_profile, demande):
    if not user_profile or not user_profile.employe:
        return False
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return demande.employe_id != user_profile.employe_id or user_profile.role == Role.ADMIN
    return (
        user_profile.role == Role.RESPONSABLE_HIERARCHIQUE
        and demande.employe.responsable_id == user_profile.employe_id
        and demande.employe_id != user_profile.employe_id
    )


def conge_decision_scope(user_profile, demande):
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return "hr"
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE and demande.employe.responsable_id == user_profile.employe_id:
        return "manager"
    return ""


def apply_conge_decision(request, demande, decision):
    user_profile = profile(request)
    if not can_process_conge(user_profile, demande):
        raise PermissionDenied("Vous n'etes pas autorise a traiter cette demande.")
    if demande.statut in {StatutDemande.VALIDEE, StatutDemande.REFUSEE, StatutDemande.CLOTUREE}:
        raise ValidationError("Cette demande a deja ete finalisee.")
    scope = conge_decision_scope(user_profile, demande)
    if not scope:
        raise PermissionDenied("Role non autorise pour cette decision.")
    status_field = f"{scope}_approval_status"
    approved_by_field = f"{scope}_approved_by"
    approved_at_field = f"{scope}_approved_at"
    refusal_field = f"{scope}_refusal_reason"
    if getattr(demande, status_field) != DemandeConge.APPROVAL_PENDING:
        raise ValidationError("Une decision a deja ete enregistree pour ce niveau d'approbation.")
    old_status = demande.statut
    if decision == "approve":
        setattr(demande, status_field, DemandeConge.APPROVAL_APPROVED)
        setattr(demande, approved_by_field, user_profile.employe)
        setattr(demande, approved_at_field, timezone.now())
        setattr(demande, refusal_field, "")
    elif decision == "refuse":
        reason = (request.POST.get("commentaire") or "").strip()
        setattr(demande, status_field, DemandeConge.APPROVAL_REFUSED)
        setattr(demande, approved_by_field, user_profile.employe)
        setattr(demande, approved_at_field, timezone.now())
        setattr(demande, refusal_field, reason)
        demande.commentaire_reponse = reason
    else:
        raise ValidationError("Decision de conge invalide.")
    demande.recompute_final_status()
    demande.traitee_par = user_profile.employe
    demande.date_traitement = timezone.now()
    if demande.statut == StatutDemande.VALIDEE and old_status != StatutDemande.VALIDEE:
        deduire_solde_conge(demande, user_profile)
    demande.full_clean()
    demande.save()
    return scope


@role_required(Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE)
@require_POST
def conge_validate(request, pk):
    demande = get_object_or_404(DemandeConge, pk=pk)
    try:
        scope = apply_conge_decision(request, demande, "approve")
        notify_employee(demande.employe, f"Votre demande de conge a recu une approbation {'RH' if scope == 'hr' else 'manager'}.", "/conges")
        audit(request, "APPROBATION_CONGE", f"Approbation {scope}", "DemandeConge", demande.pk)
        messages.success(request, "Approbation enregistree.")
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except Exception:
        messages.error(request, "Une erreur inattendue est survenue pendant l'approbation.")
    return redirect("conges_list")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE)
@require_POST
def conge_refuse(request, pk):
    demande = get_object_or_404(DemandeConge, pk=pk)
    try:
        scope = apply_conge_decision(request, demande, "refuse")
        notify_employee(demande.employe, f"Votre demande de conge a ete refusee par {'les RH' if scope == 'hr' else 'votre manager'}.", "/conges")
        audit(request, "REFUS_CONGE", f"Refus {scope}", "DemandeConge", demande.pk)
        messages.success(request, "Refus enregistre.")
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except Exception:
        messages.error(request, "Une erreur inattendue est survenue pendant le refus.")
    return redirect("conges_list")

@login_required
@require_POST
def conge_cancel(request, pk):
    user_profile = profile(request)
    demande = get_object_or_404(DemandeConge, pk=pk)
    if not user_profile or demande.employe_id != user_profile.employe_id or demande.statut not in {StatutDemande.EN_ATTENTE, StatutDemande.EN_COURS, StatutDemande.VALIDEE}:
        messages.error(request, "Cette demande ne peut pas etre annulee.")
        return redirect("conges_list")
    was_validated = demande.statut == StatutDemande.VALIDEE
    demande.statut = StatutDemande.CLOTUREE
    demande.traitee_par = user_profile.employe
    demande.date_traitement = timezone.now()
    demande.full_clean()
    demande.save(update_fields=["statut", "traitee_par", "date_traitement", "updated_at"])
    if was_validated:
        # TRAITEMENT SOLDE CONGE — remboursement si le conge annule etait deja valide.
        from .services import rembourser_solde_conge
        rembourser_solde_conge(demande, user_profile)
    audit(request, "ANNULATION_CONGE", "Annulation de la demande de conge", "DemandeConge", demande.pk)
    messages.success(request, "Demande annulee.")
    return redirect("conges_list")


def demandes_for_profile(user_profile):
    if not user_profile or not user_profile.employe:
        return DemandeAdministrative.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return DemandeAdministrative.objects.select_related("employe", "traitee_par").prefetch_related("documents")
    return DemandeAdministrative.objects.filter(employe=user_profile.employe).select_related("employe", "traitee_par").prefetch_related("documents")


def demande_tab_for_status(statut):
    if statut == StatutDemande.VALIDEE:
        return "validees"
    if statut == StatutDemande.REFUSEE:
        return "refusees"
    return "attente"


@login_required
def demandes_list(request):
    active_tab = request.GET.get("tab", "attente")
    if active_tab not in {"attente", "validees", "refusees"}:
        active_tab = "attente"
    demandes = demandes_for_profile(profile(request))
    statut = request.GET.get("statut")
    if statut:
        demandes = demandes.filter(statut=statut)
    elif active_tab == "validees":
        demandes = demandes.filter(statut=StatutDemande.VALIDEE)
    elif active_tab == "refusees":
        demandes = demandes.filter(statut=StatutDemande.REFUSEE)
    else:
        demandes = demandes.filter(statut__in=[StatutDemande.EN_ATTENTE, StatutDemande.EN_COURS])
    base_qs = demandes_for_profile(profile(request))
    return render(
        request,
        "demandes/list.html",
        {
            "page_title": "Demandes Admin",
            "demandes": demandes,
            "statuts": StatutDemande.choices,
            "statut_filtre": statut,
            "active_tab": active_tab,
            "pending_count": base_qs.filter(statut__in=[StatutDemande.EN_ATTENTE, StatutDemande.EN_COURS]).count(),
            "accepted_count": base_qs.filter(statut=StatutDemande.VALIDEE).count(),
            "rejected_count": base_qs.filter(statut=StatutDemande.REFUSEE).count(),
        },
    )


@login_required
def demande_detail(request, pk):
    demande = get_object_or_404(demandes_for_profile(profile(request)), pk=pk)
    documents = list(demande.documents.all())
    request_documents = [doc for doc in documents if doc.categorie != "Reponse RH"]
    reply_documents = [doc for doc in documents if doc.categorie == "Reponse RH"]
    return render(
        request,
        "demandes/detail.html",
        {
            "page_title": "Detail demande administrative",
            "demande": demande,
            "request_documents": request_documents,
            "reply_documents": reply_documents,
            "list_tab": demande_tab_for_status(demande.statut),
        },
    )


@login_required
def demande_create(request):
    return render(request, "demandes/form.html", {"page_title": "Nouvelle demande administrative", "form": DemandeAdministrativeForm()})


@login_required
@require_POST
def demande_submit(request):
    user_profile = profile(request)
    if not user_profile or not user_profile.employe:
        messages.error(request, "Aucun employe n'est lie a votre compte.")
        return redirect("demandes_list")
    form = DemandeAdministrativeForm(request.POST, request.FILES)
    if form.is_valid():
        demande = form.save(commit=False)
        demande.employe = user_profile.employe
        demande.statut = StatutDemande.EN_ATTENTE
        demande.date_creation = timezone.now()
        demande.save()
        piece_jointe = request.FILES.get("pieceJointe")
        if piece_jointe:
            try:
                validate_uploaded_file(piece_jointe, DOCUMENT_EXTENSION_VALIDATOR)
            except ValidationError as exc:
                form.add_error(None, exc)
                demande.delete()
                return render(request, "demandes/form.html", {"page_title": "Nouvelle demande administrative", "form": form})
            create_document(request, piece_jointe, "Demande administrative", user_profile.employe, demande)
        notify_rh_and_admin(f"Nouvelle demande administrative de {user_profile.employe.nom_complet}", "/demandes")
        audit(request, "SOUMISSION_DEMANDE_ADMIN", "Demande administrative soumise", "DemandeAdministrative", demande.pk)
        messages.success(request, "Demande administrative soumise avec succes.")
        return redirect("demandes_list")
    return render(request, "demandes/form.html", {"page_title": "Nouvelle demande administrative", "form": form})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def demande_process(request, pk):
    demande = get_object_or_404(demandes_for_profile(profile(request)), pk=pk)
    user_profile = profile(request)
    try:
        if demande.statut in {StatutDemande.VALIDEE, StatutDemande.REFUSEE, StatutDemande.CLOTUREE}:
            raise ValidationError("Cette demande a deja ete finalisee.")
        statut = request.POST.get("statut")
        if statut not in {StatutDemande.EN_COURS, StatutDemande.VALIDEE, StatutDemande.REFUSEE}:
            raise ValidationError("Statut invalide.")
        reponse = (request.POST.get("reponse") or "").strip()
        files = request.FILES.getlist("pieces_jointes")
        if statut in {StatutDemande.VALIDEE, StatutDemande.REFUSEE} and not reponse and not files:
            raise ValidationError("Ajoutez une reponse RH ou une piece jointe avant de finaliser.")
        for uploaded_file in files:
            validate_uploaded_file(uploaded_file, DOCUMENT_EXTENSION_VALIDATOR)
        demande.reponse = reponse
        demande.statut = statut
        demande.traitee_par = user_profile.employe
        demande.date_traitement = timezone.now()
        demande.full_clean()
        demande.save()
        for uploaded_file in files:
            create_document(request, uploaded_file, "Reponse RH", demande.employe, demande)
        notify_employee(demande.employe, "Votre demande administrative a ete traitee", f"/demandes/{demande.pk}")
        audit(request, "TRAITEMENT_DEMANDE_ADMIN", "Traitement d'une demande administrative", "DemandeAdministrative", demande.pk)
        messages.success(request, "Demande traitee avec succes.")
        if statut in {StatutDemande.VALIDEE, StatutDemande.REFUSEE}:
            return redirect(f"{reverse('demandes_list')}?tab={demande_tab_for_status(statut)}")
        return redirect("demande_detail", pk=demande.pk)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except Exception:
        messages.error(request, "Une erreur inattendue est survenue pendant le traitement.")
    return redirect("demande_detail", pk=demande.pk)


def create_document(request, uploaded_file, categorie, employe, demande_admin):
    document = Document.objects.create(
        fichier=uploaded_file,
        nom_fichier=Path(uploaded_file.name).name,
        nom_original=Path(uploaded_file.name).name,
        categorie=categorie or "General",
        taille=uploaded_file.size,
        employe=employe,
        demande_admin=demande_admin,
        uploade_par=request.user,
    )
    document.chemin_fichier = document.fichier.path
    document.nom_fichier = Path(document.fichier.name).name
    document.save(update_fields=["chemin_fichier", "nom_fichier"])
    audit(request, "UPLOAD_DOCUMENT", f"Televersement du document {document.nom_original}", "Document", document.pk)
    return document


def accessible_employees(user_profile):
    if not user_profile or not user_profile.employe:
        return Employe.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return Employe.objects.filter(actif=True)
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return Employe.objects.filter(direct_report_filter(user_profile.employe), actif=True)
    return Employe.objects.filter(pk=user_profile.employe_id)


def accessible_documents(user_profile, include_archived=False):
    # TRAITEMENT PERMISSION DOCUMENT — limite les documents selon role et lien employe.
    if not user_profile or not user_profile.employe:
        return Document.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        documents = Document.objects.select_related("employe", "uploade_par", "archive_par")
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        documents = Document.objects.filter(employe__in=accessible_employees(user_profile)).select_related("employe", "uploade_par", "archive_par")
    elif user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        documents = Document.objects.filter(employe=user_profile.employe).select_related("employe", "uploade_par", "archive_par")
    if include_archived and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return documents
    return documents.filter(archive=False)


@login_required
def documents_list(request):
    messages.info(request, "Les documents RH sont maintenant partages dans les tickets Support RH.")
    return redirect(f"{reverse('rh_messages')}?tab=available")
    user_profile = profile(request)
    can_view_archives = user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}
    archive_mode = bool(can_view_archives and request.GET.get("archive") == "1")
    documents = accessible_documents(user_profile, include_archived=archive_mode)
    if archive_mode:
        documents = documents.filter(archive=True)
    categorie = request.GET.get("categorie", "").strip()
    employe_id = request.GET.get("employeId")
    if categorie:
        documents = documents.filter(categorie__iexact=categorie)
    if employe_id:
        documents = documents.filter(employe_id=employe_id)
    return render(
        request,
        "documents/list.html",
        {
            "page_title": "Documents",
            "documents": documents,
            "employes": accessible_employees(user_profile),
            "categorie_filtre": categorie,
            "employe_filtre": employe_id,
            "archive_mode": archive_mode,
            "can_view_archives": can_view_archives,
        },
    )


@login_required
@require_POST
def document_upload(request):
    user_profile = profile(request)
    if not user_profile:
        messages.error(request, "Aucun profil n'est lie a votre compte.")
        return redirect("documents_list")
    uploaded = request.FILES.get("file")
    if not uploaded:
        messages.error(request, "Le fichier est obligatoire.")
        return redirect("documents_list")
    try:
        validate_uploaded_file(uploaded, DOCUMENT_EXTENSION_VALIDATOR)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("documents_list")
    employe = user_profile.employe
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} and request.POST.get("employeId"):
        employe = Employe.objects.filter(pk=request.POST.get("employeId")).first()
    create_document(request, uploaded, request.POST.get("categorie"), employe, None)
    messages.success(request, "Document televerse avec succes.")
    return redirect("documents_list")


@login_required
def document_download(request, pk):
    document = get_object_or_404(Document, pk=pk)
    # TRAITEMENT SECURITE DOCUMENT — protege aussi le telechargement par URL directe.
    user_profile = profile(request)
    include_archived = user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}
    if not accessible_documents(user_profile, include_archived=include_archived).filter(pk=pk).exists():
        return HttpResponseForbidden()
    return FileResponse(document.fichier.open("rb"), as_attachment=True, filename=document.nom_original)


@login_required
@require_POST
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    user_profile = profile(request)
    if not (user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}) and document.uploade_par_id != request.user.id:
        messages.error(request, "Vous n'etes pas autorise a supprimer ce document.")
        return redirect("documents_list")
    if document.archive:
        messages.info(request, "Ce document est deja archive.")
        return redirect("documents_list")
    document.archive = True
    document.date_archivage = timezone.now()
    document.archive_par = user_profile
    document.save(update_fields=["archive", "date_archivage", "archive_par", "updated_at"])
    audit(request, "ARCHIVAGE_DOCUMENT", f"Archivage du document {document.nom_original}", "Document", document.pk)
    messages.success(request, "Document archive.")
    return redirect("documents_list")


@login_required
def notifications_list(request):
    user_profile = profile(request)
    notifications = user_profile.notifications.all() if user_profile else Notification.objects.none()
    return render(request, "notifications/list.html", {"page_title": "Notifications", "notifications": notifications})


@login_required
@require_POST
def notification_read(request, pk):
    user_profile = profile(request)
    notification = get_object_or_404(Notification, pk=pk, destinataire=user_profile)
    notification.lue = True
    notification.save(update_fields=["lue", "updated_at"])
    messages.success(request, "Notification marquee comme lue.")
    return redirect("notifications_list")


@login_required
@require_POST
def notifications_read_all(request):
    user_profile = profile(request)
    if user_profile:
        user_profile.notifications.filter(lue=False).update(lue=True)
        messages.success(request, "Toutes les notifications sont marquees comme lues.")
    return redirect("notifications_list")


@login_required
def attendance_view(request):
    user_profile = profile(request)
    if not user_profile or not user_profile.employe:
        return redirect("dashboard")
    qs = Pointage.objects.select_related("employe", "employe__departement")
    # TRAITEMENT PERMISSION POINTAGE — filtre la presence selon role.
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        pointages = qs.all()
    elif user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        pointages = qs.filter(Q(employe=user_profile.employe) | Q(employe__responsable=user_profile.employe))
    else:
        pointages = qs.filter(employe=user_profile.employe)
    today = timezone.localdate()
    today_pointages = pointages.filter(date=today)
    shift_today = (
        PlanningShift.objects.filter(
            employe=user_profile.employe,
            statut="publie",
            plan_type="normal",
            date_debut__date__lte=today,
            date_fin__date__gte=today,
        )
        .order_by("date_debut")
        .first()
    )
    if not shift_today:
        from .services import shift_permanent_for_day

        shift_today = shift_permanent_for_day(user_profile.employe, today)
    personal_today = pointages.filter(employe=user_profile.employe, date=today).first()
    active_shift_now = shift_planifie_actuel(user_profile.employe)
    has_open_pointage = bool(personal_today and personal_today.heure_entree and not personal_today.heure_sortie)
    total_hours_today = sum(float(pointage.total_heures or 0) for pointage in today_pointages)
    planned_today = PlanningShift.objects.filter(Q(date_debut__date__lte=today, date_fin__date__gte=today) | Q(plan_type="permanent", date_debut__date__lte=today)).exclude(statut="annule")
    if user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        planned_today = planned_today.filter(employe__in=accessible_employees(user_profile))
    pointage_details = [pointage_breakdown(item) for item in pointages[:80]]
    return render(
        request,
        "pointage/index.html",
        {
            "page_title": "Presence / Pointage",
            "pointages": pointages[:80],
            "today": personal_today,
            "shift_today": shift_today,
            "active_shift_now": active_shift_now,
            "has_open_pointage": has_open_pointage,
            "today_pointages_count": today_pointages.count(),
            "today_retards_count": today_pointages.filter(statut="retard").count(),
            "today_open_count": today_pointages.filter(heure_sortie__isnull=True).count(),
            "today_total_hours": total_hours_today,
            "planned_today_count": planned_today.count(),
            "pointage_details": pointage_details,
            "compte": ComptePoints.objects.get_or_create(employe=user_profile.employe)[0],
        },
    )


@login_required
@require_POST
def attendance_checkin(request):
    try:
        pointer_entree(profile(request).employe)
        messages.success(request, "Pointage d'entree enregistre.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("attendance")


@login_required
@require_POST
def attendance_checkout(request):
    try:
        pointer_sortie(profile(request).employe)
        messages.success(request, "Pointage de sortie enregistre.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("attendance")


def planning_payload(request):
    if request.body:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("JSON invalide.") from exc
    return request.POST.dict()


def planning_json_ok(data=None, message=""):
    return JsonResponse({"ok": True, "data": data or {}, "errors": {}, "message": message})


def planning_json_error(exc, status=400):
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"ok": False, "data": {}, "errors": {"permission": [str(exc)]}, "message": str(exc)}, status=403)
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            errors = exc.message_dict
            message = "Veuillez corriger les champs invalides."
        else:
            errors = {"__all__": exc.messages}
            message = " ".join(exc.messages)
        return JsonResponse({"ok": False, "data": {}, "errors": errors, "message": message}, status=status)
    return JsonResponse({"ok": False, "data": {}, "errors": {"__all__": [str(exc)]}, "message": str(exc)}, status=status)


def planning_for_profile(user_profile):
    qs = PlanningShift.objects.select_related("employe", "departement", "service")
    if not user_profile or not user_profile.employe:
        return qs.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return qs
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return qs.filter(Q(employe=user_profile.employe) | Q(employe__responsable=user_profile.employe) | Q(employe__isnull=True))
    return qs.filter(Q(employe=user_profile.employe) | Q(employe__isnull=True, statut="ouvert"))


def employees_for_planning_scope(cleaned):
    scope = cleaned["scope"]
    employees = Employe.objects.filter(actif=True).select_related("departement", "service")
    if scope == "company":
        return employees
    if scope == "departement":
        return employees.filter(departement=cleaned["departement"])
    if scope == "service":
        return employees.filter(service=cleaned["service"])
    return cleaned["employes"]


def planning_board(shifts):
    groups = {}
    for shift in shifts:
        departement = shift.departement or (shift.employe.departement if shift.employe else None)
        service = shift.service or (shift.employe.service if shift.employe else None)
        key = (
            departement.pk if departement else 0,
            service.pk if service else 0,
        )
        if key not in groups:
            groups[key] = {
                "departement": departement.libelle if departement else "Sans departement",
                "service": service.libelle if service else "Sans service",
                "shifts": [],
            }
        groups[key]["shifts"].append(shift)
    return sorted(groups.values(), key=lambda item: (item["departement"], item["service"]))


@login_required
def planning(request):
    user_profile = profile(request)
    today = timezone.localdate()
    week_start = today - timezone.timedelta(days=today.weekday())
    allowed_tabs = {"overview", "calendar", "daily", "weekly", "biweekly", "monthly", "timesheets", "shifts", "attendance", "leave", "tasks", "approvals", "reports", "settings"}
    active_tab = request.GET.get("tab")
    if not active_tab:
        return redirect(f"{reverse('planning')}?tab=overview")
    if active_tab not in allowed_tabs:
        messages.warning(request, "Section Planning introuvable. Retour a l'apercu.")
        return redirect(f"{reverse('planning')}?tab=overview")
    if active_tab == "settings" and (not user_profile or user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}):
        messages.warning(request, "Vous n'avez pas acces aux parametres Planning.")
        return redirect(f"{reverse('planning')}?tab=overview")
    default_start = week_start
    default_end = week_start + timezone.timedelta(days=6)
    if active_tab == "daily":
        default_start = default_end = today
    elif active_tab == "biweekly":
        default_end = week_start + timezone.timedelta(days=13)
    elif active_tab == "monthly":
        default_start = today.replace(day=1)
        next_month = (default_start + timezone.timedelta(days=32)).replace(day=1)
        default_end = next_month - timezone.timedelta(days=1)
    date_debut = request.GET.get("date_debut") or default_start.isoformat()
    date_fin = request.GET.get("date_fin") or default_end.isoformat()
    try:
        start_date = parse_day(date_debut, "date_debut") or week_start
        end_date = parse_day(date_fin, "date_fin") or (week_start + timezone.timedelta(days=6))
    except ValidationError:
        start_date = default_start
        end_date = default_end
        date_debut = start_date.isoformat()
        date_fin = end_date.isoformat()
    shifts = planning_queryset_for_profile(user_profile)
    statut = request.GET.get("statut", "").strip()
    employe_id = request.GET.get("employe", "").strip()
    departement_id = request.GET.get("departement", "").strip()
    service_id = request.GET.get("service", "").strip()
    search = request.GET.get("search", "").strip()
    planning_type = request.GET.get("planning_type", "").strip()
    conflict_level = request.GET.get("conflict_level", "").strip()
    view_mode = request.GET.get("view", "week").strip() or "week"
    if date_debut:
        shifts = shifts.filter(Q(date_fin__date__gte=start_date) | Q(plan_type="permanent"))
    if date_fin:
        shifts = shifts.filter(date_debut__date__lte=end_date)
    if statut:
        shifts = shifts.filter(statut=statut)
    if employe_id:
        shifts = shifts.filter(employe_id=employe_id)
    if departement_id:
        shifts = shifts.filter(Q(departement_id=departement_id) | Q(employe__departement_id=departement_id))
    if service_id:
        shifts = shifts.filter(Q(service_id=service_id) | Q(employe__service_id=service_id))
    if planning_type in {"normal", "permanent"}:
        shifts = shifts.filter(plan_type=planning_type)
    if search:
        shifts = shifts.filter(Q(titre__icontains=search) | Q(lieu__icontains=search) | Q(employe__nom__icontains=search) | Q(employe__prenom__icontains=search) | Q(employe__matricule__icontains=search))
    can_manage = user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}
    shifts = shifts.order_by("departement__libelle", "service__libelle", "date_debut", "employe__nom")
    days = []
    cursor = start_date
    while cursor <= end_date:
        days.append(cursor)
        cursor += timezone.timedelta(days=1)
    employees = accessible_employees(user_profile)
    if employe_id:
        employees = employees.filter(pk=employe_id)
    if departement_id:
        employees = employees.filter(departement_id=departement_id)
    if service_id:
        employees = employees.filter(service_id=service_id)
    if search:
        employees = employees.filter(Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(matricule__icontains=search))
    shift_list = list(shifts[:300])
    grid_rows = []
    for employee in employees[:120]:
        employee_shifts = [shift for shift in shift_list if shift.employe_id == employee.pk]
        grid_rows.append(
            {
                "employee": employee,
                "total_hours": round(sum(float(shift.duree_heures or 0) for shift in employee_shifts), 2),
                "cells": [
                    {
                        "day": day,
                        "shifts": [shift for shift in employee_shifts if shift_occurs_on(shift, day)],
                    }
                    for day in days
                ],
            }
        )
    open_shifts = [shift for shift in shift_list if not shift.employe_id]
    summary = planning_summary(user_profile, start_date, end_date)
    conflicts = conflict_list(user_profile, start_date, end_date)
    scoped_employees = accessible_employees(user_profile)
    scoped_employee_ids = scoped_employees.values_list("pk", flat=True)
    pointages = Pointage.objects.select_related("employe", "employe__departement").filter(date__gte=start_date, date__lte=end_date, employe_id__in=scoped_employee_ids)
    all_leaves = DemandeConge.objects.select_related("employe").filter(date_debut__lte=end_date, date_fin__gte=start_date, employe_id__in=scoped_employee_ids)
    leaves = all_leaves.filter(statut=StatutDemande.VALIDEE)
    tasks = tasks_for_profile(user_profile).filter(Q(date_limite__date__gte=start_date, date_limite__date__lte=end_date) | Q(shift__date_debut__date__gte=start_date, shift__date_debut__date__lte=end_date))
    attendance_summary = {
        "records": pointages.count(),
        "late": pointages.filter(statut="retard").count(),
        "early": pointages.filter(statut="sortie_anticipee").count(),
        "absent": pointages.filter(statut="absent").count(),
        "open": pointages.filter(heure_sortie__isnull=True).count(),
        "hours": round(sum(float(pointage.total_heures or 0) for pointage in pointages), 2),
    }
    leave_summary = {
        "approved": leaves.count(),
        "pending": all_leaves.filter(statut=StatutDemande.EN_ATTENTE).count(),
    }
    task_summary = {
        "planned": tasks.count(),
        "overdue": sum(1 for task in tasks if task.is_overdue),
    }
    weekly_limit = 44
    hour_warnings = [{"employee": row["employee"], "hours": row["total_hours"]} for row in grid_rows if row["total_hours"] >= weekly_limit]
    agenda_days = [{"day": day, "shifts": [shift for shift in shift_list if shift_occurs_on(shift, day)]} for day in days]
    month_leading = []
    month_cursor = start_date - timezone.timedelta(days=start_date.weekday())
    month_end = end_date + timezone.timedelta(days=6 - end_date.weekday())
    while month_cursor <= month_end:
        month_leading.append({"day": month_cursor, "in_range": start_date <= month_cursor <= end_date, "shifts": [shift for shift in shift_list if shift_occurs_on(shift, month_cursor)]})
        month_cursor += timezone.timedelta(days=1)
    monthly_weeks = [month_leading[index : index + 7] for index in range(0, len(month_leading), 7)]
    pointage_details = [pointage_breakdown(item) for item in pointages.order_by("-date", "employe__nom")[:120]]
    report_summary = {
        "planned_hours": summary["planned_hours"],
        "actual_hours": attendance_summary["hours"],
        "missing_hours": round(sum(item["missing_hours"] for item in pointage_details), 2),
        "late_arrivals": attendance_summary["late"],
        "early_departures": attendance_summary["early"],
        "absences": attendance_summary["absent"],
        "by_employee": [{"name": row["employee"].nom_complet, "hours": row["total_hours"]} for row in grid_rows if row["total_hours"]][:8],
        "by_department": [],
    }
    department_hours = {}
    for shift in shift_list:
        department = shift.departement or (shift.employe.departement if shift.employe else None)
        key = department.libelle if department else "Sans departement"
        department_hours[key] = department_hours.get(key, 0) + float(shift.duree_heures or 0)
    report_summary["by_department"] = [{"name": name, "hours": round(hours, 2)} for name, hours in sorted(department_hours.items())[:8]]
    return render(
        request,
        "planning/index.html",
        {
            "page_title": "Planning",
            "active_tab": active_tab,
            "shifts": shift_list,
            "planning_groups": planning_board(shift_list),
            "grid_days": days,
            "grid_rows": grid_rows,
            "agenda_days": agenda_days,
            "monthly_weeks": monthly_weeks,
            "open_shifts": open_shifts,
            "summary": summary,
            "report_summary": report_summary,
            "attendance_summary": attendance_summary,
            "leave_summary": leave_summary,
            "task_summary": task_summary,
            "pointages": pointages.order_by("-date", "employe__nom")[:120],
            "pointage_details": pointage_details,
            "leaves": leaves.order_by("date_debut")[:120],
            "planning_tasks": tasks.order_by("date_limite")[:120],
            "hour_warnings": hour_warnings,
            "weekly_limit": weekly_limit,
            "conflicts": conflicts[:10],
            "form": PlanningBulkForm() if can_manage else None,
            "shift_form": PlanningShiftForm() if can_manage else None,
            "employes": accessible_employees(user_profile),
            "departements": Departement.objects.all(),
            "services": Service.objects.select_related("departement"),
            "statuts": PlanningShift.STATUTS,
            "date_debut": date_debut,
            "date_fin": date_fin,
            "prev_start": (start_date - timezone.timedelta(days=(end_date - start_date).days + 1)).isoformat(),
            "prev_end": (end_date - timezone.timedelta(days=(end_date - start_date).days + 1)).isoformat(),
            "next_start": (start_date + timezone.timedelta(days=(end_date - start_date).days + 1)).isoformat(),
            "next_end": (end_date + timezone.timedelta(days=(end_date - start_date).days + 1)).isoformat(),
            "statut_filtre": statut,
            "employe_filtre": employe_id,
            "departement_filtre": departement_id,
            "service_filtre": service_id,
            "search": search,
            "planning_type_filtre": planning_type,
            "conflict_level_filtre": conflict_level,
            "view_mode": view_mode,
            "can_manage": can_manage,
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def planning_create(request):
    form = PlanningBulkForm(request.POST)
    if form.is_valid():
        cleaned = form.cleaned_data
        period_type = cleaned.get("period_type") or "single"
        start_dt = cleaned["date_debut"]
        end_dt = cleaned.get("date_fin")
        duration = (end_dt - start_dt) if end_dt else None
        days = [start_dt.date()]
        if period_type == "weekly_unified":
            first = start_dt.date() - timezone.timedelta(days=start_dt.weekday())
            days = [first + timezone.timedelta(days=offset) for offset in range(5)]
        elif period_type == "biweekly":
            days = [start_dt.date() + timezone.timedelta(days=offset) for offset in range(14) if (start_dt.date() + timezone.timedelta(days=offset)).weekday() < 5]
        elif period_type == "monthly":
            first = start_dt.date().replace(day=1)
            next_month = (first + timezone.timedelta(days=32)).replace(day=1)
            cursor = first
            days = []
            while cursor < next_month:
                if cursor.weekday() < 5:
                    days.append(cursor)
                cursor += timezone.timedelta(days=1)
        base_payload = {
            "scope": "company" if period_type == "weekly_unified" else cleaned["scope"],
            "title": cleaned["titre"],
            "department_id": cleaned["departement"].pk if cleaned.get("departement") else "",
            "service_id": cleaned["service"].pk if cleaned.get("service") else "",
            "employee_ids": [employee.pk for employee in cleaned.get("employes", [])],
            "location": cleaned["lieu"],
            "plan_type": cleaned["plan_type"],
            "recurrence_rule": cleaned["recurrence_rule"],
            "permanent_end_time": cleaned["permanent_end_time"].isoformat() if cleaned.get("permanent_end_time") else "",
            "break_minutes": cleaned["pause_minutes"],
            "status": cleaned["statut"],
            "notes": cleaned["notes"],
        }
        try:
            created_rows = []
            skipped = []
            for day in days:
                starts_at = timezone.make_aware(timezone.datetime.combine(day, start_dt.time()))
                ends_at = starts_at + duration if duration else None
                break_starts_at = ""
                if cleaned.get("pause_debut"):
                    break_starts_at = timezone.make_aware(timezone.datetime.combine(day, cleaned["pause_debut"].time())).isoformat()
                payload = {
                    **base_payload,
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat() if ends_at else "",
                    "break_starts_at": break_starts_at,
                }
                result = bulk_create_shifts(profile(request), payload)
                created_rows.extend(result["created"])
                skipped.extend(result["skipped"])
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect("planning")
        created = len(created_rows)
        audit(request, "CREATION_PLANNING_GROUPE", f"{created} shift(s) crees via {base_payload['scope']}", "PlanningShift", None)
        if created:
            messages.success(request, f"{created} shift(s) ajoute(s) au planning.")
        if skipped:
            messages.warning(request, f"{len(skipped)} employe(s) ignore(s) pour conflit de planning ou conge.")
    else:
        messages.error(request, "Planning invalide: veuillez verifier les dates, conges et chevauchements.")
    return redirect("planning")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def planning_status(request, pk):
    shift = get_object_or_404(PlanningShift, pk=pk)
    statut = request.POST.get("statut")
    if statut not in dict(PlanningShift.STATUTS):
        messages.error(request, "Statut de shift invalide.")
        return redirect("planning")
    shift.statut = statut
    try:
        change_shift_status(profile(request), shift, statut)
        messages.success(request, "Planning mis a jour.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("planning")


def filtered_planning_queryset(request):
    user_profile = profile(request)
    shifts = planning_queryset_for_profile(user_profile)
    start = request.GET.get("date_debut") or request.GET.get("start_date")
    end = request.GET.get("date_fin") or request.GET.get("end_date")
    statut = request.GET.get("statut") or request.GET.get("status")
    employe_id = request.GET.get("employe") or request.GET.get("employee_id")
    departement_id = request.GET.get("departement") or request.GET.get("department_id")
    service_id = request.GET.get("service") or request.GET.get("service_id")
    planning_type = (request.GET.get("planning_type") or "").strip()
    search = (request.GET.get("search") or "").strip()
    if start:
        shifts = shifts.filter(Q(date_fin__date__gte=parse_day(start, "date_debut")) | Q(plan_type="permanent"))
    if end:
        shifts = shifts.filter(date_debut__date__lte=parse_day(end, "date_fin"))
    if statut:
        shifts = shifts.filter(statut=statut)
    if employe_id:
        shifts = shifts.filter(employe_id=employe_id)
    if departement_id:
        shifts = shifts.filter(Q(departement_id=departement_id) | Q(employe__departement_id=departement_id))
    if service_id:
        shifts = shifts.filter(Q(service_id=service_id) | Q(employe__service_id=service_id))
    if planning_type in {"normal", "permanent"}:
        shifts = shifts.filter(plan_type=planning_type)
    if search:
        shifts = shifts.filter(Q(titre__icontains=search) | Q(lieu__icontains=search) | Q(employe__nom__icontains=search) | Q(employe__prenom__icontains=search))
    return shifts.order_by("date_debut", "employe__nom")


def planning_export_rows(request):
    rows = []
    for shift in filtered_planning_queryset(request)[:1000]:
        rows.append(
            [
                shift.titre,
                shift.employe.nom_complet if shift.employe else "Shift ouvert",
                shift.departement.libelle if shift.departement else "",
                shift.service.libelle if shift.service else "",
                timezone.localtime(shift.date_debut).strftime("%d/%m/%Y %H:%M"),
                timezone.localtime(shift.date_fin).strftime("%d/%m/%Y %H:%M") if shift.date_fin else "",
                shift.get_statut_display(),
                shift.get_plan_type_display(),
                shift.duree_heures,
            ]
        )
    return rows


def minimal_pdf_bytes(title, headers, rows):
    def esc(value):
        return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [title, timezone.now().strftime("Genere le %d/%m/%Y %H:%M"), " | ".join(headers)]
    lines.extend(" | ".join(esc(item) for item in row) for row in rows[:35])
    stream_lines = ["BT", "/F1 10 Tf", "40 800 Td", "14 TL"]
    for line in lines:
        stream_lines.append(f"({esc(line)[:140]}) Tj")
        stream_lines.append("T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in pdf))
        pdf.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(part) for part in pdf)
    pdf.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.append(f"trailer << /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii"))
    return b"".join(pdf)


@login_required
def planning_export(request, file_format):
    file_format = (file_format or "").lower()
    if file_format not in {"csv", "excel", "pdf"}:
        messages.error(request, "Format d'export planning invalide.")
        return redirect(f"{reverse('planning')}?tab=reports")
    headers = ["Shift", "Employe", "Departement", "Service", "Debut", "Fin", "Statut", "Type", "Heures"]
    rows = planning_export_rows(request)
    filename = f"planning-{timezone.localdate().isoformat()}"
    if file_format == "pdf":
        response = HttpResponse(minimal_pdf_bytes("Rapport planning", headers, rows), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return response
    response = HttpResponse(content_type="text/csv; charset=utf-8" if file_format == "csv" else "application/vnd.ms-excel; charset=utf-8")
    extension = "csv" if file_format == "csv" else "xls"
    response["Content-Disposition"] = f'attachment; filename="{filename}.{extension}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


@login_required
@require_http_methods(["GET", "POST"])
def planning_api_shifts(request):
    try:
        if request.method == "GET":
            shifts = filtered_planning_queryset(request)[:300]
            return planning_json_ok({"shifts": [serialize_shift(shift) for shift in shifts]})
        shift = create_planning_shift(profile(request), planning_payload(request))
        return planning_json_ok({"shift": serialize_shift(shift)}, "Shift cree avec succes.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
def planning_api_shift_detail(request, pk):
    try:
        shift = get_object_or_404(planning_queryset_for_profile(profile(request)), pk=pk)
        if request.method == "GET":
            return planning_json_ok({"shift": serialize_shift(shift)})
        if request.method == "DELETE":
            updated = change_shift_status(profile(request), shift, "annule")
            return planning_json_ok({"shift": serialize_shift(updated)}, "Shift annule.")
        updated = update_planning_shift(profile(request), shift, planning_payload(request))
        return planning_json_ok({"shift": serialize_shift(updated)}, "Shift mis a jour.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_POST
def planning_api_move(request, pk):
    try:
        shift = get_object_or_404(planning_queryset_for_profile(profile(request)), pk=pk)
        moved = move_shift(profile(request), shift, planning_payload(request))
        return planning_json_ok({"shift": serialize_shift(moved)}, "Shift deplace.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_POST
def planning_api_resize(request, pk):
    try:
        shift = get_object_or_404(planning_queryset_for_profile(profile(request)), pk=pk)
        resized = resize_shift(profile(request), shift, planning_payload(request))
        return planning_json_ok({"shift": serialize_shift(resized)}, "Shift redimensionne.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_POST
def planning_api_bulk(request):
    try:
        result = bulk_create_shifts(profile(request), planning_payload(request))
        return planning_json_ok(result, "Creation groupee traitee.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_POST
def planning_api_copy(request):
    try:
        result = copy_planning(profile(request), planning_payload(request))
        return planning_json_ok(result, "Copie du planning traitee.")
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


@login_required
@require_http_methods(["GET", "POST"])
def planning_api_conflicts(request):
    try:
        source = request.GET if request.method == "GET" else planning_payload(request)
        start = parse_day(source.get("start_date") or source.get("date_debut"), "start_date") if (source.get("start_date") or source.get("date_debut")) else None
        end = parse_day(source.get("end_date") or source.get("date_fin"), "end_date") if (source.get("end_date") or source.get("date_fin")) else None
        conflicts = conflict_list(profile(request), start, end)
        return planning_json_ok({"conflicts": conflicts})
    except ValidationError as exc:
        return planning_json_error(exc)


@login_required
def planning_api_summary(request):
    try:
        start = parse_day(request.GET.get("start_date") or request.GET.get("date_debut"), "start_date") if (request.GET.get("start_date") or request.GET.get("date_debut")) else None
        end = parse_day(request.GET.get("end_date") or request.GET.get("date_fin"), "end_date") if (request.GET.get("end_date") or request.GET.get("date_fin")) else None
        return planning_json_ok({"summary": planning_summary(profile(request), start, end)})
    except ValidationError as exc:
        return planning_json_error(exc)


@login_required
def planning_api_available_employees(request):
    try:
        employees = available_employees(profile(request), request.GET)
        return planning_json_ok({"employees": employees})
    except ValidationError as exc:
        return planning_json_error(exc)


@login_required
@require_POST
def planning_api_assistant(request):
    try:
        payload = planning_payload(request)
        start = parse_day(payload.get("start_date") or payload.get("date_debut"), "start_date") if (payload.get("start_date") or payload.get("date_debut")) else None
        end = parse_day(payload.get("end_date") or payload.get("date_fin"), "end_date") if (payload.get("end_date") or payload.get("date_fin")) else None
        result = handle_planning_assistant(profile(request), payload.get("message", ""), start, end)
        return planning_json_ok(result)
    except (PermissionDenied, ValidationError) as exc:
        return planning_json_error(exc)


def tasks_for_profile(user_profile):
    qs = TacheEquipe.objects.select_related("employe", "accepte_par", "manager", "departement", "service", "shift", "cree_par")
    if not user_profile or not user_profile.employe:
        return qs.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return qs
    if user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        return qs.filter(Q(manager=user_profile.employe) | Q(employe__responsable=user_profile.employe) | Q(accepte_par__responsable=user_profile.employe))
    return qs.filter(Q(employe=user_profile.employe) | Q(accepte_par=user_profile.employe) | Q(manager=user_profile.employe.responsable, mode_affectation="open", statut="ouverte"))


def managed_task_employees(user_profile, departement=None, service=None):
    if not user_profile or not user_profile.employe:
        return Employe.objects.none()
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        qs = Employe.objects.filter(actif=True)
    elif user_profile.role == Role.RESPONSABLE_HIERARCHIQUE:
        qs = Employe.objects.filter(actif=True, responsable=user_profile.employe)
    else:
        return Employe.objects.none()
    if departement:
        qs = qs.filter(departement=departement)
    if service:
        qs = qs.filter(service=service)
    return qs.select_related("departement", "service", "responsable")


def can_manage_task(user_profile, task):
    if not user_profile or not user_profile.employe:
        return False
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return True
    if user_profile.role != Role.RESPONSABLE_HIERARCHIQUE:
        return False
    assignee = task.assignee
    return task.manager_id == user_profile.employe_id or bool(assignee and assignee.responsable_id == user_profile.employe_id)


MANAGER_MONTHLY_TASK_POINTS = 120
TASK_POINT_MAX = 30


def task_points_used(user_profile):
    if not user_profile:
        return 0
    today = timezone.localdate()
    return (
        TransactionPoints.objects.filter(
            cree_par=user_profile,
            source="tache",
            type_transaction="gain",
            date_transaction__year=today.year,
            date_transaction__month=today.month,
        ).aggregate(total=Sum("points")).get("total")
        or 0
    )


def suggested_task_points(task):
    base = {"basse": 5, "normale": 10, "haute": 16, "urgente": 22}.get(task.priorite, 10)
    size_bonus = {"petite": 0, "moyenne": 4, "grande": 8}.get(task.taille, 4)
    delay_penalty = 5 if task.date_limite and task.date_completion and task.date_completion > task.date_limite else 0
    return max(0, min(TASK_POINT_MAX, base + size_bonus - delay_penalty))


def auto_assign_open_tasks(user_profile):
    if not user_profile or not user_profile.employe:
        return
    now = timezone.now()
    open_tasks = tasks_for_profile(user_profile).filter(mode_affectation="open", statut="ouverte", auto_assign_at__isnull=False, auto_assign_at__lte=now, accepte_par__isnull=True)
    for task in open_tasks:
        manager = task.manager or (task.cree_par.employe if task.cree_par and task.cree_par.employe else None)
        if task.cree_par:
            candidate = managed_task_employees(task.cree_par, task.departement, task.service).order_by("taches__date_creation", "nom").first()
        else:
            candidate = Employe.objects.filter(actif=True, responsable=manager).order_by("taches__date_creation", "nom").first() if manager else None
        if candidate:
            task.accepte_par = candidate
            task.employe = candidate
            task.statut = "acceptee"
            task.save(update_fields=["accepte_par", "employe", "statut"])
            notify_employee(candidate, f"Tache auto-affectee: {task.titre}", "/taches")


@login_required
def team_tasks(request):
    user_profile = profile(request)
    can_manage = user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE}
    auto_assign_open_tasks(user_profile)
    tasks = tasks_for_profile(user_profile)
    requested_tab = request.GET.get("tab")
    allowed_tabs = {"overview", "create", "open", "mine", "team", "approval", "points", "archive"}
    if not requested_tab:
        return redirect(f"{reverse('team_tasks')}?tab=overview")
    active_tab = requested_tab
    if active_tab not in allowed_tabs:
        messages.warning(request, "Section Taches equipe introuvable. Retour a l'apercu.")
        return redirect(f"{reverse('team_tasks')}?tab=overview")
    manager_tabs = {"create", "team", "approval", "points"}
    if active_tab in manager_tabs and not can_manage:
        messages.warning(request, "Vous n'avez pas acces a cette section Taches equipe.")
        active_tab = "overview"
    statut = request.GET.get("statut", "").strip()
    if statut:
        tasks = tasks.filter(statut=statut)
    open_tasks = tasks.filter(mode_affectation="open", statut="ouverte")
    my_tasks = tasks.filter(Q(employe=user_profile.employe) | Q(accepte_par=user_profile.employe)) if user_profile and user_profile.employe else tasks.none()
    team_followup = tasks.exclude(statut__in=["archivee"]) if can_manage else my_tasks
    pending_approval = tasks.filter(statut="soumise")
    archive = tasks.filter(statut__in=["terminee", "rejetee", "annulee", "archivee"])
    points_used = task_points_used(user_profile) if can_manage else 0
    return render(
        request,
        "taches/index.html",
        {
            "page_title": "Taches equipe",
            "tasks": tasks[:200],
            "form": TacheEquipeForm(user_profile=user_profile) if can_manage else None,
            "statuts": TacheEquipe.STATUTS,
            "statut_filtre": statut,
            "can_manage": can_manage,
            "active_tab": active_tab,
            "open_tasks": open_tasks,
            "my_tasks": my_tasks,
            "team_followup": team_followup,
            "pending_approval": pending_approval,
            "archive": archive,
            "overview": {
                "total": tasks.count(),
                "urgent": tasks.filter(priorite="urgente").exclude(statut__in=["terminee", "archivee", "annulee"]).count(),
                "overdue": sum(1 for task in tasks if task.is_overdue),
                "pending": pending_approval.count(),
                "completed": tasks.filter(statut="terminee").count(),
            },
            "points_budget": MANAGER_MONTHLY_TASK_POINTS,
            "points_used": points_used,
            "points_remaining": max(MANAGER_MONTHLY_TASK_POINTS - points_used, 0),
            "task_point_max": TASK_POINT_MAX,
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE)
@require_POST
def task_create(request):
    user_profile = profile(request)
    form = TacheEquipeForm(request.POST, request.FILES, user_profile=user_profile)
    if form.is_valid():
        task = form.save(commit=False)
        task.cree_par = user_profile
        if user_profile and user_profile.employe:
            task.manager = user_profile.employe
        try:
            attach_task_file(task, request.FILES.get("piece_jointe"))
            eligible = managed_task_employees(user_profile, task.departement, task.service)
            if task.mode_affectation in {"team", "open"} and not eligible.exists():
                raise ValidationError("Aucun employe eligible dans ce perimetre.")
            if task.mode_affectation == "direct" and task.employe and not eligible.filter(pk=task.employe_id).exists():
                raise PermissionDenied("Employe hors de votre perimetre manager.")
            if task.mode_affectation == "team":
                created = 0
                for employee in eligible:
                    clone = TacheEquipe(
                        titre=task.titre,
                        description=task.description,
                        employe=employee,
                        manager=task.manager,
                        departement=employee.departement or task.departement,
                        service=employee.service or task.service,
                        priorite=task.priorite,
                        mode_affectation="direct",
                        obligatoire=task.obligatoire,
                        taille=task.taille,
                        statut="a_faire",
                        date_debut=task.date_debut,
                        date_fin=task.date_fin,
                        date_limite=task.date_limite,
                        max_acceptations=1,
                        piece_jointe=task.piece_jointe,
                        nom_piece_jointe=task.nom_piece_jointe,
                        cree_par=user_profile,
                    )
                    clone.points_suggeres = suggested_task_points(clone)
                    clone.full_clean()
                    clone.save()
                    notify_employee(employee, f"Nouvelle tache equipe: {clone.titre}", "/taches?tab=mine")
                    created += 1
                audit(request, "CREATION_TACHE_EQUIPE", f"{created} tache(s) creee(s): {task.titre}", "TacheEquipe", None)
                messages.success(request, f"{created} tache(s) equipe creee(s).")
                return redirect(f"{reverse('team_tasks')}?tab=team")
            if task.mode_affectation == "open":
                task.statut = "ouverte"
                task.employe = None
            else:
                task.statut = "a_faire"
            task.points_suggeres = suggested_task_points(task)
            task.full_clean()
            task.save()
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(f"{reverse('team_tasks')}?tab=create")
        except PermissionDenied as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('team_tasks')}?tab=create")
        if task.employe:
            notify_employee(task.employe, f"Nouvelle tache: {task.titre}", "/taches?tab=mine")
        elif task.mode_affectation == "open" and task.manager:
            for emp in managed_task_employees(user_profile, task.departement, task.service):
                notify_employee(emp, f"Nouvelle tache ouverte: {task.titre}", "/taches?tab=open")
        audit(request, "CREATION_TACHE", f"Tache creee: {task.titre}", "TacheEquipe", task.pk)
        messages.success(request, "Tache creee.")
    else:
        errors = []
        for field_errors in form.errors.values():
            errors.extend(field_errors)
        messages.error(request, " ".join(errors) or "Tache invalide.")
    return redirect(f"{reverse('team_tasks')}?tab=create")


@login_required
def task_detail(request, pk):
    user_profile = profile(request)
    task = get_object_or_404(tasks_for_profile(user_profile).prefetch_related("messages"), pk=pk)
    can_manage = user_profile and can_manage_task(user_profile, task)
    can_reply = bool(user_profile and user_profile.employe)
    if request.method == "POST":
        form = TacheEquipeMessageForm(request.POST, request.FILES)
        if not can_reply:
            messages.error(request, "Vous n'etes pas autorise a repondre a cette tache.")
            return redirect("task_detail", pk=task.pk)
        if form.is_valid():
            try:
                message = form.save(commit=False)
                message.tache = task
                message.auteur = user_profile
                attach_task_file(message, request.FILES.get("piece_jointe"))
                message.full_clean()
                message.save()
                audit(request, "MESSAGE_TACHE", f"Reponse sur la tache: {task.titre}", "TacheEquipe", task.pk)
                if can_manage and task.assignee:
                    notify_employee(task.assignee, f"Nouveau message sur la tache: {task.titre}", reverse("task_detail", args=[task.pk]))
                elif task.manager:
                    notify_employee(task.manager, f"Nouveau message sur la tache: {task.titre}", reverse("task_detail", args=[task.pk]))
                messages.success(request, "Reponse ajoutee.")
                return redirect("task_detail", pk=task.pk)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        else:
            messages.error(request, "Message invalide: ajoutez un texte ou une piece jointe valide.")
    else:
        form = TacheEquipeMessageForm()
    return render(
        request,
        "taches/detail.html",
        {
            "page_title": f"Tache - {task.titre}",
            "task": task,
            "messages_tache": task.messages.select_related("auteur", "auteur__employe"),
            "message_form": form,
            "can_manage_task": can_manage,
            "can_reply": can_reply,
        },
    )


@login_required
@require_POST
def task_status(request, pk):
    user_profile = profile(request)
    try:
        with transaction.atomic():
            action = request.POST.get("action") or request.POST.get("statut")
            task = get_object_or_404(TacheEquipe.objects.select_for_update(), pk=pk)
            visible = tasks_for_profile(user_profile).filter(pk=task.pk).exists()
            stale_open_accept = (
                action == "accept"
                and user_profile
                and user_profile.employe
                and task.mode_affectation == "open"
                and task.manager_id == user_profile.employe.responsable_id
            )
            if not visible and not stale_open_accept:
                raise PermissionDenied("Vous n'avez pas acces a cette tache.")
            is_manager = user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE}
            assignee = task.assignee
            owns_task = user_profile and user_profile.employe and assignee and assignee.pk == user_profile.employe_id
            terminal_statuses = {"terminee", "rejetee", "annulee", "archivee"}
            if action == "accept":
                if not user_profile or not user_profile.employe:
                    raise PermissionDenied("Profil employe introuvable.")
                if task.statut != "ouverte" or task.mode_affectation != "open" or task.assignee:
                    raise ValidationError("Cette tache n'est plus disponible.")
                task.accepte_par = user_profile.employe
                task.employe = user_profile.employe
                task.statut = "acceptee"
            elif action == "start":
                if not owns_task:
                    raise PermissionDenied("Vous ne pouvez demarrer que vos propres taches.")
                if task.statut in terminal_statuses:
                    raise ValidationError("Cette tache est deja cloturee.")
                task.statut = "en_cours"
            elif action == "submit":
                if not owns_task:
                    raise PermissionDenied("Vous ne pouvez soumettre que vos propres taches.")
                if task.statut in terminal_statuses or task.statut == "soumise":
                    raise ValidationError("Cette tache ne peut plus etre soumise.")
                task.message_completion = (request.POST.get("message_completion") or "").strip()
                task.statut = "soumise"
                task.terminee_par = user_profile
                task.date_completion = timezone.now()
            elif action == "approve":
                if not is_manager or not can_manage_task(user_profile, task):
                    raise PermissionDenied("Seul un manager peut approuver une tache.")
                if task.statut != "soumise":
                    raise ValidationError("Seules les taches soumises peuvent etre approuvees.")
                try:
                    points = int(request.POST.get("points") or 0)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("Les points doivent etre un nombre valide.") from exc
                if points < 0 or points > TASK_POINT_MAX:
                    raise ValidationError(f"Les points doivent etre entre 0 et {TASK_POINT_MAX}.")
                remaining = MANAGER_MONTHLY_TASK_POINTS - task_points_used(user_profile)
                if points > remaining:
                    raise ValidationError("Budget mensuel de points insuffisant.")
                task.feedback_manager = (request.POST.get("feedback_manager") or "").strip()
                task.points_attribues = points
                task.points_attribues_par = user_profile
                task.points_attribues_at = timezone.now() if points else None
                task.statut = "terminee"
                if points and task.assignee:
                    appliquer_transaction_points(task.assignee, "gain", points, "tache", f"Tache approuvee: {task.titre}", user_profile, f"TacheEquipe:{task.pk}")
            elif action == "changes":
                if not is_manager or not can_manage_task(user_profile, task):
                    raise PermissionDenied("Seul un manager peut demander des changements.")
                if task.statut != "soumise":
                    raise ValidationError("Seules les taches soumises peuvent etre renvoyees.")
                task.feedback_manager = (request.POST.get("feedback_manager") or "").strip() or "Changements demandes."
                task.statut = "changements"
            elif action == "reject":
                if not is_manager or not can_manage_task(user_profile, task):
                    raise PermissionDenied("Seul un manager peut rejeter une tache.")
                if task.statut != "soumise":
                    raise ValidationError("Seules les taches soumises peuvent etre rejetees.")
                task.feedback_manager = (request.POST.get("feedback_manager") or "").strip() or "Tache rejetee."
                task.statut = "rejetee"
            elif action in {"annulee", "archivee"}:
                if not is_manager or not can_manage_task(user_profile, task):
                    raise PermissionDenied("Vous ne pouvez pas modifier cette tache.")
                task.statut = action
            else:
                raise ValidationError("Action de tache invalide.")
            task.full_clean()
            task.save()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect(f"{reverse('team_tasks')}?tab=overview")
    except (PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('team_tasks')}?tab=overview")
    audit(request, "STATUT_TACHE", f"{task.titre} -> {task.statut}", "TacheEquipe", task.pk)
    messages.success(request, "Tache mise a jour.")
    if action in {"approve", "changes", "reject"}:
        return redirect(f"{reverse('team_tasks')}?tab=approval")
    if action == "accept":
        return redirect(f"{reverse('team_tasks')}?tab=mine")
    return redirect(f"{reverse('team_tasks')}?tab=mine")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def formations_admin(request):
    if request.method == "POST":
        form = AffectationFormationForm(request.POST)
        if form.is_valid():
            formation = form.cleaned_data["formation"]
            employe = form.cleaned_data["employe"]
            existing_active = AffectationFormation.objects.filter(formation=formation, employe=employe, statut__in=["assignee", "en_cours"]).first()
            if existing_active:
                messages.warning(request, "Cette formation est deja affectee a cet employe.")
            else:
                aff = AffectationFormation.objects.create(
                    formation=formation,
                    employe=employe,
                    assigne_par=profile(request),
                    date_limite=form.cleaned_data["date_limite"],
                )
                notify_employee(employe, f"Nouvelle formation assignee: {formation.titre}", "/formations/mes-formations")
                audit(request, "AFFECTATION_FORMATION", f"Formation assignee: {formation.titre} a {employe.nom_complet}", "AffectationFormation", aff.pk)
                messages.success(request, "Formation assignee.")
            return redirect("formations_admin")
    else:
        form = AffectationFormationForm()
    return render(request, "formations/admin.html", {"page_title": "Affectation des formations", "form": form, "formations": Formation.objects.all(), "affectations": AffectationFormation.objects.select_related("formation", "employe").order_by("-date_affectation", "-id"), "formation_form": FormationForm()})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def formation_create(request):
    form = FormationForm(request.POST)
    if form.is_valid():
        formation = form.save(commit=False)
        formation.full_clean()
        formation.save()
        audit(request, "CREATION_FORMATION", f"Formation creee: {formation.titre}", "Formation", formation.pk)
        messages.success(request, "Formation creee.")
    else:
        messages.error(request, "Formation invalide.")
    return redirect("formations_admin")


@login_required
def my_trainings(request):
    user_profile = profile(request)
    qs = AffectationFormation.objects.filter(employe=user_profile.employe).select_related("formation") if user_profile and user_profile.employe else AffectationFormation.objects.none()
    return render(request, "formations/me.html", {"page_title": "Mes formations", "affectations": qs})


@login_required
@require_POST
def training_status(request, pk):
    aff = get_object_or_404(AffectationFormation, pk=pk, employe=profile(request).employe)
    if aff.statut == "annulee":
        messages.error(request, "Cette formation a ete annulee par les RH.")
        return redirect("my_trainings")
    statut = request.POST.get("statut")
    if statut in {"en_cours", "terminee"}:
        was_awarded = aff.points_attribues
        aff.statut = statut
        if statut == "terminee":
            aff.date_completion = timezone.localdate()
        aff.full_clean()
        aff.save()
        # TRAITEMENT POINTS FORMATION — attribue les points une seule fois apres completion.
        if statut == "terminee" and not was_awarded and aff.formation.points_recompense > 0:
            appliquer_transaction_points(aff.employe, "gain", aff.formation.points_recompense, "formation", f"Formation terminee: {aff.formation.titre}", profile(request), f"AffectationFormation:{aff.pk}")
            aff.points_attribues = True
            aff.save(update_fields=["points_attribues"])
            notify_employee(aff.employe, f"Points attribues pour la formation {aff.formation.titre}.", "/pointage")
            audit(request, "FORMATION_TERMINEE", f"Formation terminee: {aff.formation.titre}", "AffectationFormation", aff.pk)
        messages.success(request, "Formation mise a jour.")
    return redirect("my_trainings")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def formation_assignment_status(request, pk):
    aff = get_object_or_404(AffectationFormation.objects.select_related("formation", "employe"), pk=pk)
    statut = request.POST.get("statut")
    if statut not in {"assignee", "en_cours", "terminee", "en_retard", "annulee"}:
        messages.error(request, "Statut de formation invalide.")
        return redirect("formations_admin")
    was_awarded = aff.points_attribues
    aff.statut = statut
    if statut == "terminee" and not aff.date_completion:
        aff.date_completion = timezone.localdate()
    aff.full_clean()
    aff.save()
    if statut == "annulee":
        notify_employee(aff.employe, f"La formation {aff.formation.titre} a ete annulee par les RH.", "/formations/mes-formations")
    if statut == "terminee" and not was_awarded and aff.formation.points_recompense > 0:
        appliquer_transaction_points(aff.employe, "gain", aff.formation.points_recompense, "formation", f"Formation terminee par RH: {aff.formation.titre}", profile(request), f"AffectationFormation:{aff.pk}")
        aff.points_attribues = True
        aff.save(update_fields=["points_attribues"])
        notify_employee(aff.employe, f"Points attribues pour la formation {aff.formation.titre}.", "/pointage")
    audit(request, "MISE_A_JOUR_FORMATION", f"{aff.formation.titre} - {aff.employe.nom_complet} - {statut}", "AffectationFormation", aff.pk)
    messages.success(request, "Affectation de formation mise a jour.")
    return redirect("formations_admin")


def conversations_for_profile(user_profile):
    if not user_profile or not user_profile.employe:
        return ConversationRH.objects.none()
    qs = ConversationRH.objects.select_related("employe", "responsable_rh", "cloture_par").prefetch_related("messages", "participants")
    if user_profile.role == Role.ADMIN:
        return qs
    if user_profile.role == Role.RESPONSABLE_RH:
        return qs.filter(Q(responsable_rh__isnull=True) | Q(responsable_rh=user_profile) | Q(employe=user_profile.employe) | Q(participants=user_profile.employe)).distinct()
    return qs.filter(Q(employe=user_profile.employe) | Q(participants=user_profile.employe)).distinct()


def can_handle_ticket(user_profile, conv):
    if not user_profile or user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        return False
    return user_profile.role == Role.ADMIN or not conv.responsable_rh_id or conv.responsable_rh_id == user_profile.id


def next_ticket_number():
    return (ConversationRH.objects.aggregate(max_number=Max("numero_ticket")).get("max_number") or 0) + 1


def month_start(day=None):
    day = day or timezone.localdate()
    return day.replace(day=1)


def support_ranking(month=None):
    month = month or month_start()
    return (
        ConversationRH.objects.filter(statut="cloturee", note_support__isnull=False, date_note__year=month.year, date_note__month=month.month, responsable_rh__employe__isnull=False)
        .values("responsable_rh", "responsable_rh__employe__nom", "responsable_rh__employe__prenom", "responsable_rh__employe_id")
        .annotate(total_stars=Sum("note_support"), rated_tickets=Count("id"))
        .order_by("-total_stars", "-rated_tickets", "responsable_rh__employe__nom")
    )


def generate_support_rewards(user_profile, month=None):
    month = month or month_start()
    ranking = list(support_ranking(month))
    if not ranking:
        return 0
    eligible_count = max(1, int(len(ranking) * 0.1))
    created = 0
    for index, row in enumerate(ranking[:eligible_count], start=1):
        points = max(10, 50 - ((index - 1) * 5))
        _, was_created = SupportRHReward.objects.get_or_create(
            employe_id=row["responsable_rh__employe_id"],
            mois=month,
            defaults={"total_etoiles": row["total_stars"], "rang": index, "points": points, "genere_par": user_profile},
        )
        created += 1 if was_created else 0
    return created


def rh_ticket_context(request, selected=None, message_form=None, close_form=None):
    user_profile = profile(request)
    conversations = conversations_for_profile(user_profile).order_by("-date_derniere_reponse")
    search = (request.GET.get("q") or "").strip()
    active_tab = request.GET.get("tab") or ("closed" if selected and selected.is_closed else "available")
    allowed_tabs = {"available", "handled", "new", "closed", "ranking", "rewards"}
    if active_tab not in allowed_tabs:
        messages.warning(request, "Section Support RH introuvable. Retour aux tickets non traites.")
        active_tab = "available"
    can_manage = bool(user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH})
    can_approve_rewards = bool(user_profile and user_profile.role in {Role.ADMIN, Role.RESPONSABLE_HIERARCHIQUE})
    if active_tab in {"ranking", "rewards"} and not (can_manage or can_approve_rewards):
        active_tab = "available"
    if search:
        conversations = conversations.filter(Q(sujet__icontains=search) | Q(employe__nom__icontains=search) | Q(employe__prenom__icontains=search) | Q(messages__contenu__icontains=search)).distinct()
    active_tickets = conversations.exclude(statut="cloturee")
    if can_manage:
        available_tickets = active_tickets.filter(responsable_rh__isnull=True)
        handled_tickets = active_tickets.filter(responsable_rh__isnull=False)
    else:
        available_tickets = active_tickets
        handled_tickets = active_tickets
    closed_tickets = conversations.filter(statut="cloturee")
    if not selected and active_tab == "available":
        selected = available_tickets.first()
    elif not selected and active_tab == "handled":
        selected = handled_tickets.first()
    elif not selected and active_tab == "closed":
        selected = closed_tickets.first()
    ranking_month = month_start()
    ranking = list(support_ranking(ranking_month))
    return {
        "page_title": "Support RH",
        "active_tab": active_tab,
        "search_query": search,
        "conversations": conversations,
        "available_tickets": available_tickets,
        "handled_tickets": handled_tickets,
        "active_tickets": active_tickets,
        "closed_tickets": closed_tickets,
        "waiting_tickets": active_tickets.filter(statut="en_attente"),
        "selected_ticket": selected,
        "form": ConversationRHForm(user_profile=user_profile),
        "message_form": message_form or MessageRHForm(),
        "close_form": close_form or ConversationRHCloseForm(),
        "rename_form": ConversationRHRenameForm(initial={"sujet": selected.sujet}) if selected else ConversationRHRenameForm(),
        "participant_form": ConversationRHParticipantForm(),
        "rating_form": ConversationRHRatingForm(),
        "can_manage_rh_tickets": can_manage,
        "can_handle_selected_ticket": can_handle_ticket(user_profile, selected) if selected else False,
        "can_rate_selected_ticket": bool(selected and selected.is_closed and not selected.note_support and user_profile and selected.employe_id == user_profile.employe_id and (not selected.responsable_rh or selected.responsable_rh_id != user_profile.id)),
        "support_ranking": ranking,
        "support_rewards": SupportRHReward.objects.filter(mois=ranking_month).select_related("employe", "approuve_par").order_by("rang"),
        "can_approve_rewards": can_approve_rewards,
    }


@login_required
def rh_messages(request):
    if "tab" not in request.GET:
        return redirect(f"{reverse('rh_messages')}?tab=available")
    return render(request, "messages_rh/list.html", rh_ticket_context(request))


@login_required
@require_POST
def rh_conversation_create(request):
    user_profile = profile(request)
    if not user_profile:
        messages.error(request, "Aucun profil n'est lie a votre compte.")
        return redirect("rh_messages")
    if not user_profile.employe and user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        messages.error(request, "Aucun employe n'est lie a votre compte.")
        return redirect("rh_messages")
    form = ConversationRHForm(request.POST, request.FILES, user_profile=user_profile)
    if form.is_valid():
        target_employee = form.cleaned_data.get("employe") if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} else user_profile.employe
        conv = None
        try:
            with transaction.atomic():
                number = next_ticket_number()
                default_name = f"Conversation {number}"
                conv = ConversationRH.objects.create(
                    numero_ticket=number,
                    sujet=default_name,
                    employe=target_employee,
                    responsable_rh=user_profile if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} else None,
                    statut="attente_employe" if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} else "en_attente",
                    categorie=form.cleaned_data.get("categorie") or "general",
                    priorite=form.cleaned_data.get("priorite") or "normale",
                )
                participants = list(form.cleaned_data.get("participants") or [])
                if target_employee not in participants:
                    participants.append(target_employee)
                conv.participants.set(participants)
                initial_text = form.cleaned_data["contenu"]
                requested_subject = form.cleaned_data.get("sujet")
                if requested_subject:
                    initial_text = f"Objet initial: {requested_subject}\n\n{initial_text}".strip()
                msg = MessageRH(conversation=conv, expediteur=user_profile, contenu=initial_text)
                if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
                    msg.destinataire = getattr(target_employee, "utilisateur_profile", None)
                msg = attach_message_file(msg, request.FILES.get("piece_jointe"))
                msg.full_clean()
                msg.save()
            if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
                notify_employee(target_employee, "Nouveau message RH.", f"/messages-rh/{conv.pk}")
            else:
                notify_rh_and_admin(f"Nouveau message RH de {user_profile.employe.nom_complet}", "/messages-rh")
            audit(request, "CREATION_CONVERSATION_RH", conv.sujet, "ConversationRH", conv.pk)
            messages.success(request, "Ticket RH cree.")
            return redirect(f"{reverse('rh_conversation_detail', args=[conv.pk])}?tab=handled" if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} else f"{reverse('rh_conversation_detail', args=[conv.pk])}?tab=available")
        except ValidationError as exc:
            if conv:
                conv.delete()
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Ticket invalide: verifiez le destinataire, le texte ou la piece jointe.")
    return redirect(f"{reverse('rh_messages')}?tab=new")


@login_required
def rh_conversation_detail(request, pk):
    user_profile = profile(request)
    conv = get_object_or_404(conversations_for_profile(user_profile), pk=pk)
    conv.messages.filter(lu=False).exclude(expediteur=user_profile).filter(Q(destinataire=user_profile) | Q(destinataire__isnull=True)).update(lu=True)
    if hasattr(conv, "_prefetched_objects_cache"):
        conv._prefetched_objects_cache.pop("messages", None)
    if request.method == "POST":
        form = MessageRHForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    conv = get_object_or_404(conversations_for_profile(user_profile).select_for_update(), pk=pk)
                    if conv.statut == "cloturee":
                        raise ValidationError("Ce ticket est cloture: aucune nouvelle reponse ne peut etre ajoutee.")
                    if user_profile.role == Role.RESPONSABLE_RH and conv.responsable_rh_id and conv.responsable_rh_id != user_profile.id:
                        raise PermissionDenied("Ce ticket est deja pris en charge par un autre RH.")
                    msg = form.save(commit=False)
                    msg.conversation = conv
                    msg.expediteur = user_profile
                    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
                        if not conv.responsable_rh_id:
                            conv.responsable_rh = user_profile
                        msg.destinataire = getattr(conv.employe, "utilisateur_profile", None)
                    else:
                        msg.destinataire = conv.responsable_rh
                    msg = attach_message_file(msg, request.FILES.get("piece_jointe"))
                    msg.full_clean()
                    msg.save()
                    conv.date_derniere_reponse = timezone.now()
                    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
                        conv.statut = "attente_employe"
                        conv.save(update_fields=["date_derniere_reponse", "responsable_rh", "statut"])
                        notify_employee(conv.employe, "Nouvelle reponse RH.", f"/messages-rh/{conv.pk}")
                    else:
                        conv.statut = "en_attente"
                        conv.save(update_fields=["date_derniere_reponse", "statut"])
                        notify_rh_and_admin("Nouvelle reponse dans une conversation RH.", f"/messages-rh/{conv.pk}")
                audit(request, "MESSAGE_RH", conv.sujet, "ConversationRH", conv.pk)
                return redirect("rh_conversation_detail", pk=pk)
            except ValidationError as exc:
                form.add_error(None, exc)
            except PermissionDenied as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Message invalide: ajoutez un texte ou une piece jointe valide.")
    else:
        form = MessageRHForm()
    return render(request, "messages_rh/list.html", rh_ticket_context(request, selected=conv, message_form=form))


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def rh_conversation_close(request, pk):
    user_profile = profile(request)
    form = ConversationRHCloseForm(request.POST)
    try:
        with transaction.atomic():
            conv = get_object_or_404(conversations_for_profile(user_profile).select_for_update(), pk=pk)
            if conv.statut == "cloturee":
                messages.info(request, "Ce ticket est deja cloture.")
                return redirect("rh_conversation_detail", pk=pk)
            if user_profile.role == Role.RESPONSABLE_RH and conv.responsable_rh_id and conv.responsable_rh_id != user_profile.id:
                raise PermissionDenied("Seul le RH proprietaire peut cloturer ce ticket.")
            if not form.is_valid():
                messages.error(request, "Choisissez un motif de cloture valide.")
                return render(request, "messages_rh/list.html", rh_ticket_context(request, selected=conv, close_form=form))
            conv.statut = "cloturee"
            conv.responsable_rh = user_profile
            conv.cloture_par = user_profile
            conv.date_cloture = timezone.now()
            conv.motif_cloture = form.cleaned_data["motif_cloture"]
            conv.detail_cloture = form.cleaned_data.get("detail_cloture", "").strip()
            conv.date_derniere_reponse = timezone.now()
            conv.save(update_fields=["statut", "responsable_rh", "cloture_par", "date_cloture", "motif_cloture", "detail_cloture", "date_derniere_reponse"])
        notify_employee(conv.employe, "Votre ticket RH a ete cloture.", f"/messages-rh/{conv.pk}?tab=closed")
        audit(request, "CLOTURE_CONVERSATION_RH", conv.sujet, "ConversationRH", conv.pk)
        messages.success(request, "Ticket RH cloture.")
        return redirect(f"{reverse('rh_conversation_detail', args=[pk])}?tab=closed")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("rh_conversation_detail", pk=pk)
    except PermissionDenied as exc:
        messages.error(request, str(exc))
        return redirect("rh_conversation_detail", pk=pk)


@login_required
def rh_message_attachment(request, pk):
    user_profile = profile(request)
    message = get_object_or_404(MessageRH.objects.select_related("conversation"), pk=pk, conversation__in=conversations_for_profile(user_profile))
    if not message.piece_jointe:
        messages.error(request, "Piece jointe introuvable.")
        return redirect("rh_conversation_detail", pk=message.conversation_id)
    try:
        return FileResponse(message.piece_jointe.open("rb"), as_attachment=False, filename=message.nom_piece_jointe or Path(message.piece_jointe.name).name)
    except OSError:
        messages.error(request, "Impossible d'ouvrir cette piece jointe.")
        return redirect("rh_conversation_detail", pk=message.conversation_id)


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def rh_conversation_accept(request, pk):
    user_profile = profile(request)
    try:
        with transaction.atomic():
            conv = get_object_or_404(conversations_for_profile(user_profile).select_for_update(), pk=pk)
            if conv.statut == "cloturee":
                raise ValidationError("Ce ticket est deja cloture.")
            if conv.responsable_rh_id and conv.responsable_rh_id != user_profile.id:
                raise ValidationError("Ce ticket est deja pris en charge par un autre RH.")
            conv.responsable_rh = user_profile
            conv.statut = "ouverte"
            conv.date_derniere_reponse = timezone.now()
            conv.save(update_fields=["responsable_rh", "statut", "date_derniere_reponse"])
        messages.success(request, "Ticket accepte et assigne a votre file.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(f"{reverse('rh_conversation_detail', args=[pk])}?tab=handled")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def rh_conversation_rename(request, pk):
    user_profile = profile(request)
    conv = get_object_or_404(conversations_for_profile(user_profile), pk=pk)
    if not can_handle_ticket(user_profile, conv) or not conv.responsable_rh_id:
        messages.error(request, "Acceptez ce ticket avant de le renommer.")
        return redirect("rh_conversation_detail", pk=pk)
    form = ConversationRHRenameForm(request.POST)
    if form.is_valid():
        new_name = form.cleaned_data["sujet"]
        if ConversationRH.objects.exclude(pk=conv.pk).filter(sujet__iexact=new_name).exists():
            messages.error(request, "Un autre ticket porte deja ce nom.")
        else:
            conv.sujet = new_name
            conv.save(update_fields=["sujet"])
            audit(request, "RENOMMAGE_TICKET_RH", new_name, "ConversationRH", conv.pk)
            messages.success(request, "Ticket renomme.")
    else:
        messages.error(request, "Nom de ticket invalide.")
    return redirect("rh_conversation_detail", pk=pk)


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def rh_conversation_participant(request, pk):
    user_profile = profile(request)
    conv = get_object_or_404(conversations_for_profile(user_profile), pk=pk)
    if not can_handle_ticket(user_profile, conv) or not conv.responsable_rh_id:
        messages.error(request, "Seul le RH proprietaire peut modifier les participants.")
        return redirect("rh_conversation_detail", pk=pk)
    action = request.POST.get("action")
    employee_id = request.POST.get("employe")
    employee = get_object_or_404(Employe, pk=employee_id, actif=True)
    if action == "add":
        if conv.participants.filter(pk=employee.pk).exists():
            messages.info(request, "Ce participant est deja ajoute.")
        else:
            conv.participants.add(employee)
            audit(request, "AJOUT_PARTICIPANT_TICKET_RH", employee.nom_complet, "ConversationRH", conv.pk)
            messages.success(request, "Participant ajoute.")
    elif action == "remove":
        if employee.pk == conv.employe_id:
            messages.error(request, "Le createur du ticket ne peut pas etre retire.")
        elif not conv.participants.filter(pk=employee.pk).exists():
            messages.info(request, "Ce participant n'est pas rattache au ticket.")
        else:
            conv.participants.remove(employee)
            audit(request, "RETRAIT_PARTICIPANT_TICKET_RH", employee.nom_complet, "ConversationRH", conv.pk)
            messages.success(request, "Participant retire.")
    else:
        messages.error(request, "Action participant invalide.")
    return redirect("rh_conversation_detail", pk=pk)


@login_required
@require_POST
def rh_conversation_rate(request, pk):
    user_profile = profile(request)
    conv = get_object_or_404(conversations_for_profile(user_profile), pk=pk)
    form = ConversationRHRatingForm(request.POST)
    if not conv.is_closed:
        messages.error(request, "La note est disponible uniquement apres cloture.")
    elif conv.note_support:
        messages.error(request, "Ce ticket a deja ete note.")
    elif not user_profile or conv.employe_id != user_profile.employe_id:
        messages.error(request, "Seul le createur du ticket peut le noter.")
    elif conv.responsable_rh_id == user_profile.id:
        messages.error(request, "Un RH ne peut pas noter son propre traitement.")
    elif form.is_valid():
        conv.note_support = form.cleaned_data["note_support"]
        conv.note_commentaire = form.cleaned_data.get("note_commentaire", "").strip()
        conv.note_par = user_profile.employe
        conv.date_note = timezone.now()
        conv.full_clean()
        conv.save(update_fields=["note_support", "note_commentaire", "note_par", "date_note"])
        messages.success(request, "Merci, votre note a ete enregistree.")
    else:
        messages.error(request, "La note doit etre comprise entre 1 et 5.")
    return redirect(f"{reverse('rh_conversation_detail', args=[pk])}?tab=closed")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def rh_support_rewards_generate(request):
    created = generate_support_rewards(profile(request))
    messages.success(request, f"{created} recompense(s) RH proposee(s) pour validation.")
    return redirect(f"{reverse('rh_messages')}?tab=rewards")


@role_required(Role.ADMIN, Role.RESPONSABLE_HIERARCHIQUE)
@require_POST
def rh_support_reward_decision(request, pk):
    user_profile = profile(request)
    reward = get_object_or_404(SupportRHReward.objects.select_related("employe"), pk=pk)
    action = request.POST.get("action")
    if reward.statut not in {"pending", "approved"}:
        messages.error(request, "Cette recompense a deja ete traitee.")
    elif action == "reject":
        reward.statut = "rejected"
        reward.approuve_par = user_profile
        reward.date_decision = timezone.now()
        reward.save(update_fields=["statut", "approuve_par", "date_decision"])
        messages.success(request, "Recompense rejetee.")
    elif action == "approve":
        try:
            appliquer_transaction_points(reward.employe, "gain", reward.points, "manuel", f"Recompense Support RH {reward.mois:%m/%Y}", user_profile, f"SupportRHReward:{reward.pk}")
            reward.statut = "awarded"
            reward.approuve_par = user_profile
            reward.date_decision = timezone.now()
            reward.save(update_fields=["statut", "approuve_par", "date_decision"])
            messages.success(request, "Points de recompense attribues.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Decision invalide.")
    return redirect(f"{reverse('rh_messages')}?tab=rewards")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def payroll_analytics(request):
    remunerations = Remuneration.objects.filter(actif=True).select_related("employe", "employe__departement", "employe__poste")
    departement_id = request.GET.get("departement", "").strip()
    poste_id = request.GET.get("poste", "").strip()
    if departement_id:
        remunerations = remunerations.filter(employe__departement_id=departement_id)
    if poste_id:
        remunerations = remunerations.filter(employe__poste_id=poste_id)
    salaires = list(remunerations.values_list("salaire_base", flat=True))
    mediane = sorted(salaires)[len(salaires) // 2] if salaires else 0
    stats = remunerations.aggregate(min=Min("salaire_base"), max=Max("salaire_base"), avg=Avg("salaire_base"), total=Sum("salaire_base"), primes=Sum("prime"))
    max_salary = stats["max"] or 0
    par_departement = list(remunerations.values("employe__departement__libelle").annotate(total=Count("id"), moyenne=Avg("salaire_base"), minimum=Min("salaire_base"), maximum=Max("salaire_base")).order_by("employe__departement__libelle"))
    for row in par_departement:
        row["label"] = row["employe__departement__libelle"] or "Non affecte"
        row["bar_width"] = round((float(row["moyenne"] or 0) / float(max_salary)) * 100, 1) if max_salary else 0
    par_poste = list(remunerations.values("employe__poste__libelle").annotate(total=Count("id"), moyenne=Avg("salaire_base"), minimum=Min("salaire_base"), maximum=Max("salaire_base")).order_by("-moyenne")[:20])
    for row in par_poste:
        row["label"] = row["employe__poste__libelle"] or "Non affecte"
        row["bar_width"] = round((float(row["moyenne"] or 0) / float(max_salary)) * 100, 1) if max_salary else 0
    monthly_payroll = list(
        remunerations.values("date_effet__year", "date_effet__month")
        .annotate(total=Sum("salaire_base"), count=Count("id"))
        .order_by("date_effet__year", "date_effet__month")[:12]
    )
    max_monthly = max([float(row["total"] or 0) for row in monthly_payroll], default=0)
    for row in monthly_payroll:
        row["label"] = f"{row['date_effet__month']:02d}/{row['date_effet__year']}"
        row["bar_height"] = round((float(row["total"] or 0) / max_monthly) * 100, 1) if max_monthly else 0
    return render(
        request,
        "paie/analytics.html",
        {
            "page_title": "Paie et analyses salariales",
            "remunerations": remunerations[:100],
            "stats": stats,
            "mediane": mediane,
            "par_departement": par_departement,
            "par_poste": par_poste,
            "monthly_payroll": monthly_payroll,
            "departements": Departement.objects.all(),
            "postes": Poste.objects.all(),
            "departement_filtre": departement_id,
            "poste_filtre": poste_id,
        },
    )


@role_required(Role.ADMIN)
def salary_edit(request, pk):
    remuneration = get_object_or_404(Remuneration, pk=pk)
    if request.method == "POST":
        before = f"{remuneration.salaire_base} {remuneration.devise} + prime {remuneration.prime}"
        form = RemunerationForm(request.POST, instance=remuneration)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.cree_par = profile(request)
            saved.full_clean()
            saved.save()
            audit(request, "MISE_A_JOUR_SALAIRE", f"{saved.employe.nom_complet}: {before} -> {saved.salaire_base} {saved.devise} + prime {saved.prime}", "Remuneration", saved.pk)
            messages.success(request, "Remuneration mise a jour.")
            return redirect("payroll_analytics")
    else:
        form = RemunerationForm(instance=remuneration)
    return render(request, "paie/form.html", {"page_title": "Modifier la remuneration", "form": form, "remuneration": remuneration})


@login_required
def news_list(request):
    user_profile = profile(request)
    news = Actualite.objects.filter(statut="publiee").order_by("-date_publication", "-id")
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        news = Actualite.objects.filter(statut="publiee").order_by("-date_publication", "-id")
    return render(request, "actualites/list.html", {"page_title": "Actualites / Newsletter", "actualites": news, "form": ActualiteForm() if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH} else None})


@login_required
def news_detail(request, pk):
    user_profile = profile(request)
    qs = Actualite.objects.prefetch_related("pieces_jointes").filter(statut="publiee")
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        qs = Actualite.objects.prefetch_related("pieces_jointes").filter(statut="publiee")
    news = get_object_or_404(qs, pk=pk)
    return render(request, "actualites/detail.html", {"page_title": news.titre, "actualite": news})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def news_create(request):
    form = ActualiteForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            image = request.FILES.get("image")
            if image:
                validate_uploaded_file(image, PHOTO_EXTENSION_VALIDATOR)
            for uploaded in request.FILES.getlist("pieces_jointes"):
                validate_uploaded_file(uploaded, DOCUMENT_EXTENSION_VALIDATOR)
            news = form.save(commit=False)
            news.auteur = profile(request)
            news.statut = "publiee"
            news.date_publication = timezone.now()
            news.full_clean()
            news.save()
            for uploaded in request.FILES.getlist("pieces_jointes"):
                ActualitePieceJointe.objects.create(actualite=news, fichier=uploaded, nom_fichier=Path(uploaded.name).name[:255])
            audit(request, "PUBLICATION_ACTUALITE", news.titre, "Actualite", news.pk)
            messages.success(request, "Actualite publiee.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Actualite invalide: titre, contenu et fichier doivent etre valides.")
    return redirect("news_list")


@login_required
def shop(request):
    user_profile = profile(request)
    employe = user_profile.employe
    if request.method == "POST":
        form = CommandeProduitForm(request.POST, employe=employe)
        if form.is_valid():
            # TRAITEMENT BOUTIQUE — creation d'une commande en attente apres validation stock/points.
            commande = form.save(commit=False)
            commande.employe = employe
            commande.cout_total_points = commande.produit.cout_points * commande.quantite
            commande.full_clean()
            commande.save()
            notify_rh_and_admin(f"Nouvelle commande materiel de {employe.nom_complet}", "/boutique")
            messages.success(request, "Commande envoyee.")
            return redirect("shop")
    else:
        form = CommandeProduitForm(employe=employe)
    commandes = CommandeProduit.objects.filter(employe=employe).select_related("produit")
    if user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}:
        commandes = CommandeProduit.objects.select_related("employe", "produit")
    is_rh = user_profile.role in {Role.ADMIN, Role.RESPONSABLE_RH}
    materiels = AffectationMateriel.objects.select_related("employe", "produit") if is_rh else AffectationMateriel.objects.filter(employe=employe).select_related("produit")
    transactions = TransactionPoints.objects.filter(employe=employe, source="boutique")[:50]
    active_order_statuses = ["en_attente", "approuvee"]
    return render(
        request,
        "boutique/index.html",
        {
            "page_title": "Boutique employe / Materiel",
            "produits": Produit.objects.filter(actif=True).select_related("categorie"),
            "produits_stock": Produit.objects.select_related("categorie").order_by("-actif", "nom") if is_rh else Produit.objects.none(),
            "categories": CategorieProduit.objects.order_by("nom") if is_rh else CategorieProduit.objects.none(),
            "form": form,
            "commandes": commandes,
            "commandes_a_traiter": commandes.filter(statut__in=active_order_statuses) if is_rh else commandes,
            "commandes_historique": commandes.exclude(statut__in=active_order_statuses) if is_rh else commandes.exclude(statut="en_attente"),
            "compte": ComptePoints.objects.get_or_create(employe=employe)[0],
            "produit_form": ProduitForm() if is_rh else None,
            "materiels": materiels[:80],
            "transactions_boutique": transactions,
            "is_rh": is_rh,
        },
    )


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def product_create(request):
    form = ProduitForm(request.POST, request.FILES)
    if form.is_valid():
        produit = form.save(commit=False)
        produit.full_clean()
        produit.save()
        audit(request, "CREATION_PRODUIT", f"Produit enregistre: {produit.nom}", "Produit", produit.pk)
        messages.success(request, "Produit enregistre.")
    else:
        messages.error(request, "Produit invalide.")
    return redirect("shop")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def product_update(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    form = ProduitForm(request.POST, request.FILES, instance=produit)
    if form.is_valid():
        produit = form.save(commit=False)
        produit.full_clean()
        produit.save()
        audit(request, "MODIFICATION_PRODUIT", f"Produit modifie: {produit.nom}", "Produit", produit.pk)
        messages.success(request, "Produit mis a jour.")
    else:
        messages.error(request, "Produit invalide: verifiez la categorie, la description, le stock et les points.")
    return redirect("shop")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def product_delete(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    produit.actif = False
    produit.save(update_fields=["actif"])
    audit(request, "SUPPRESSION_PRODUIT", f"Produit retire du catalogue: {produit.nom}", "Produit", produit.pk)
    messages.success(request, "Produit retire du catalogue.")
    return redirect("shop")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def order_process(request, pk):
    commande = get_object_or_404(CommandeProduit, pk=pk)
    try:
        action = request.POST.get("action")
        if action == "approuver":
            approuver_commande(commande, profile(request))
        elif action == "livrer":
            livrer_commande(commande, profile(request))
        elif action in {"refuser", "annuler"}:
            refuser_ou_annuler_commande(commande, "refusee" if action == "refuser" else "annulee", profile(request), request.POST.get("motif", ""))
        messages.success(request, "Commande traitee.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("shop")


@login_required
def reclamations(request):
    messages.info(request, "Les reclamations RH sont maintenant traitees via Support RH.")
    return redirect(f"{reverse('rh_messages')}?tab=available")
    user_profile = profile(request)
    qs = ReclamationRH.objects.select_related("employe", "traite_par")
    if user_profile.role not in {Role.ADMIN, Role.RESPONSABLE_RH}:
        qs = qs.filter(employe=user_profile.employe)
    return render(request, "reclamations/list.html", {"page_title": "Reclamations RH", "reclamations": qs, "form": ReclamationRHForm()})


@login_required
@require_POST
def reclamation_create(request):
    user_profile = profile(request)
    form = ReclamationRHForm(request.POST)
    if form.is_valid():
        rec = form.save(commit=False)
        rec.employe = user_profile.employe
        rec.full_clean()
        rec.save()
        notify_rh_and_admin(f"Nouvelle reclamation de {rec.employe.nom_complet}", "/reclamations")
        audit(request, "CREATION_RECLAMATION", rec.sujet, "ReclamationRH", rec.pk)
        messages.success(request, "Reclamation envoyee.")
    else:
        messages.error(request, "Reclamation invalide.")
    return redirect("reclamations")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
@require_POST
def reclamation_process(request, pk):
    rec = get_object_or_404(ReclamationRH, pk=pk)
    form = TraitementReclamationForm(request.POST, instance=rec)
    if form.is_valid():
        action = form.cleaned_data["action"]
        rec.reponse_rh = form.cleaned_data["reponse_rh"]
        rec.date_traitement = timezone.now()
        rec.traite_par = profile(request)
        rec.points_accordes = form.cleaned_data["points_accordes"] or 0
        rec.statut = {"refuser": "refusee", "accepter": "acceptee", "points": "acceptee", "infos": "en_cours", "cloturer": "cloturee"}[action]
        # TRAITEMENT RECLAMATION/POINTS — evite le double ajout grace a action_points_appliquee.
        if action == "points" and not rec.action_points_appliquee:
            appliquer_transaction_points(rec.employe, "gain", rec.points_accordes, "reclamation", f"Compensation reclamation: {rec.sujet}", profile(request), f"ReclamationRH:{rec.pk}")
            rec.action_points_appliquee = True
        rec.full_clean()
        rec.save()
        notify_employee(rec.employe, "Votre reclamation RH a ete traitee.", "/reclamations")
        audit(request, "TRAITEMENT_RECLAMATION", rec.sujet, "ReclamationRH", rec.pk)
        messages.success(request, "Reclamation traitee.")
    else:
        messages.error(request, "Traitement invalide.")
    return redirect("reclamations")


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def manual_points(request):
    if request.method == "POST":
        form = AjustementPointsManuelForm(request.POST)
        if form.is_valid():
            adj = form.save(commit=False)
            adj.cree_par = profile(request)
            # TRAITEMENT PERMISSION POINTS — un RH ne peut pas ajuster ses propres points.
            if adj.employe_id == profile(request).employe_id and profile(request).role != Role.ADMIN:
                messages.error(request, "Un RH ne peut pas ajuster ses propres points.")
                return redirect("manual_points")
            type_tx = "gain" if adj.type_adjustement in {"ajout", "remboursement"} else "deduction"
            try:
                objet_lie = f"ConversationRH:{adj.ticket_lie_id}" if adj.ticket_lie_id else ""
                appliquer_transaction_points(adj.employe, type_tx, adj.nombre_points, "ticket" if adj.ticket_lie_id else "manuel", adj.motif_obligatoire, profile(request), objet_lie)
                adj.save()
                notify_employee(adj.employe, "Votre solde de points a ete ajuste par les RH.", "/pointage")
                messages.success(request, "Ajustement enregistre.")
                return redirect("manual_points")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        else:
            messages.error(request, "Ajustement invalide.")
    return render(request, "points/manual.html", {"page_title": "Correction manuelle des points", "form": AjustementPointsManuelForm(), "transactions": []})


@role_required(Role.ADMIN, Role.RESPONSABLE_RH)
def audit_history(request):
    # TRAITEMENT AUDIT — consultation filtree de l'historique par role, action, module et dates.
    actions = HistoriqueAction.objects.select_related("utilisateur", "utilisateur__user")
    search = request.GET.get("search", "").strip()
    role = request.GET.get("role", "").strip()
    action_type = request.GET.get("action", "").strip()
    module = request.GET.get("module", "").strip()
    date_debut = request.GET.get("date_debut", "").strip()
    date_fin = request.GET.get("date_fin", "").strip()
    if search:
        actions = actions.filter(Q(details__icontains=search) | Q(action__icontains=search) | Q(entite_concernee__icontains=search) | Q(utilisateur__user__username__icontains=search))
    if role:
        actions = actions.filter(utilisateur__role=role)
    if action_type:
        actions = actions.filter(action__icontains=action_type)
    if module:
        actions = actions.filter(entite_concernee__icontains=module)
    if date_debut:
        actions = actions.filter(date_action__date__gte=date_debut)
    if date_fin:
        actions = actions.filter(date_action__date__lte=date_fin)
    return render(request, "audit/list.html", {"page_title": "Historique / Audit", "actions": actions[:200], "roles": Role.choices})

