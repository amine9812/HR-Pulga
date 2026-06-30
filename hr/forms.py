import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Actualite,
    AffectationFormation,
    AjustementPointsManuel,
    CommandeProduit,
    ConversationRH,
    DemandeAdministrative,
    DemandeConge,
    Departement,
    Employe,
    Formation,
    MessageRH,
    PlanningShift,
    Poste,
    Produit,
    ReclamationRH,
    Remuneration,
    Service,
    SoldeConge,
    StatutDemande,
    TacheEquipe,
    TypeConge,
)


NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' -]+$")
PHONE_RE = re.compile(r"^\+?[0-9 ]{8,20}$")


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            field.widget.attrs.setdefault("class", css)


class EmployeForm(BootstrapModelForm):
    class Meta:
        model = Employe
        fields = [
            "matricule",
            "nom",
            "prenom",
            "email",
            "telephone",
            "date_naissance",
            "date_embauche",
            "adresse",
            "departement",
            "service",
            "poste",
            "responsable",
            "actif",
        ]
        widgets = {
            "date_naissance": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "date_embauche": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "adresse": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_matricule(self):
        matricule = (self.cleaned_data.get("matricule") or "").strip()
        if Employe.objects.filter(matricule__iexact=matricule).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ce matricule existe deja.")
        return matricule

    def clean_nom(self):
        return self._clean_person_name("nom")

    def clean_prenom(self):
        return self._clean_person_name("prenom")

    def _clean_person_name(self, field_name):
        value = (self.cleaned_data.get(field_name) or "").strip()
        if len(value) < 2:
            raise ValidationError("Ce champ doit contenir au moins 2 caracteres.")
        if not NAME_RE.match(value):
            raise ValidationError("Ce champ ne doit contenir que des lettres, espaces, apostrophes ou tirets.")
        return value

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if Employe.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Cet email est deja utilise par un autre employe.")
        return email

    def clean_telephone(self):
        telephone = (self.cleaned_data.get("telephone") or "").strip()
        if telephone and not PHONE_RE.match(telephone):
            raise ValidationError("Le telephone doit contenir 8 a 20 chiffres, espaces, et eventuellement +.")
        return telephone

    def clean_date_naissance(self):
        # TRAITEMENT DATE — la date de naissance ne peut pas etre dans le futur.
        value = self.cleaned_data.get("date_naissance")
        if value and value > timezone.localdate():
            raise ValidationError("La date de naissance ne peut pas etre dans le futur.")
        return value

    def clean_date_embauche(self):
        # TRAITEMENT DATE — la date d'embauche ne peut pas etre dans le futur.
        value = self.cleaned_data.get("date_embauche")
        if value and value > timezone.localdate():
            raise ValidationError("La date d'embauche ne peut pas etre dans le futur.")
        return value

    def clean_adresse(self):
        return (self.cleaned_data.get("adresse") or "").strip()

    def clean_responsable(self):
        responsable = self.cleaned_data.get("responsable")
        if self.instance.pk and responsable and responsable.pk == self.instance.pk:
            return None
        return responsable


class DepartementForm(BootstrapModelForm):
    class Meta:
        model = Departement
        fields = ["libelle", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean_libelle(self):
        libelle = (self.cleaned_data.get("libelle") or "").strip()
        if len(libelle) < 2:
            raise ValidationError("Le libelle doit contenir au moins 2 caracteres.")
        qs = Departement.objects.filter(libelle__iexact=libelle)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce departement existe deja.")
        return libelle

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()


class ServiceForm(BootstrapModelForm):
    class Meta:
        model = Service
        fields = ["libelle", "description", "departement"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean_libelle(self):
        libelle = (self.cleaned_data.get("libelle") or "").strip()
        if len(libelle) < 2:
            raise ValidationError("Le libelle doit contenir au moins 2 caracteres.")
        return libelle

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean(self):
        cleaned = super().clean()
        libelle = cleaned.get("libelle")
        departement = cleaned.get("departement")
        if libelle:
            qs = Service.objects.filter(libelle__iexact=libelle)
            if departement:
                qs = qs.filter(departement=departement)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("libelle", "Ce service existe deja pour ce departement.")
        return cleaned


class PosteForm(BootstrapModelForm):
    class Meta:
        model = Poste
        fields = ["libelle", "description", "niveau", "rang_hierarchique", "est_direction", "est_manager"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "niveau": forms.TextInput(attrs={"list": "niveau-options", "autocomplete": "off"}),
        }

    def clean_libelle(self):
        libelle = (self.cleaned_data.get("libelle") or "").strip()
        if len(libelle) < 2:
            raise ValidationError("Le libelle doit contenir au moins 2 caracteres.")
        qs = Poste.objects.filter(libelle__iexact=libelle)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce poste existe deja.")
        return libelle

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_niveau(self):
        niveau = " ".join((self.cleaned_data.get("niveau") or "").split())
        return niveau[:1].upper() + niveau[1:] if niveau else ""


class DemandeCongeForm(BootstrapModelForm):
    def __init__(self, *args, employee=None, **kwargs):
        self.employee = employee
        super().__init__(*args, **kwargs)

    class Meta:
        model = DemandeConge
        fields = ["type", "date_debut", "date_fin", "motif"]
        widgets = {
            "date_debut": forms.DateInput(attrs={"type": "date", "id": "dateDebut"}),
            "date_fin": forms.DateInput(attrs={"type": "date", "id": "dateFin"}),
            "motif": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        # TRAITEMENT CONGE — dates coherentes, solde suffisant et absence de chevauchement actif.
        debut = cleaned.get("date_debut")
        fin = cleaned.get("date_fin")
        today = timezone.localdate()
        if debut and debut < today:
            self.add_error("date_debut", "La date de debut ne peut pas etre dans le passe.")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "La date de fin doit etre apres la date de debut.")
        if self.employee and debut and fin:
            jours = (fin - debut).days + 1
            solde = getattr(self.employee, "solde_conge", None)
            if cleaned.get("type") != TypeConge.SANS_SOLDE and solde and jours > solde.jours_disponibles:
                self.add_error("date_fin", "La duree demandee depasse votre solde de conges disponible.")
            overlapping = DemandeConge.objects.filter(
                employe=self.employee,
                date_debut__lte=fin,
                date_fin__gte=debut,
            ).exclude(statut__in=[StatutDemande.REFUSEE, StatutDemande.CLOTUREE])
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise ValidationError("Cette periode chevauche deja une autre demande de conge active.")
        return cleaned

    def clean_motif(self):
        return (self.cleaned_data.get("motif") or "").strip()


class DemandeAdministrativeForm(BootstrapModelForm):
    class Meta:
        model = DemandeAdministrative
        fields = ["type_demande", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def clean_type_demande(self):
        value = (self.cleaned_data.get("type_demande") or "").strip()
        if len(value) < 2:
            raise ValidationError("Le type de demande doit contenir au moins 2 caracteres.")
        return value

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if len(value) < 10:
            raise ValidationError("La description doit contenir au moins 10 caracteres.")
        return value


class GestionPosteForm(BootstrapModelForm):
    class Meta:
        model = Employe
        fields = ["poste", "departement", "service", "responsable", "actif"]

    def clean_responsable(self):
        # TRAITEMENT HIERARCHIE — empeche un employe d'etre son propre responsable.
        responsable = self.cleaned_data.get("responsable")
        if self.instance.pk and responsable and responsable.pk == self.instance.pk:
            raise ValidationError("Un employe ne peut pas etre son propre responsable.")
        return responsable

    def clean(self):
        cleaned = super().clean()
        clone = self.instance
        clone.responsable = cleaned.get("responsable")
        clone.clean()
        return cleaned


class FormationForm(BootstrapModelForm):
    class Meta:
        model = Formation
        fields = ["titre", "description", "categorie", "duree_estimee_heures", "points_recompense", "actif"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_titre(self):
        value = (self.cleaned_data.get("titre") or "").strip()
        if len(value) < 2:
            raise ValidationError("Le titre est obligatoire.")
        return value


class AffectationFormationForm(BootstrapModelForm):
    employe = forms.ModelChoiceField(queryset=Employe.objects.filter(actif=True))

    class Meta:
        model = AffectationFormation
        fields = ["formation", "employe", "date_limite"]
        widgets = {"date_limite": forms.DateInput(attrs={"type": "date"})}

    def clean_date_limite(self):
        # TRAITEMENT DATE FORMATION — la date limite ne peut pas etre dans le passe.
        value = self.cleaned_data.get("date_limite")
        if value and value < timezone.localdate():
            raise ValidationError("La date limite ne peut pas etre dans le passe.")
        return value


class ConversationRHForm(BootstrapModelForm):
    employe = forms.ModelChoiceField(queryset=Employe.objects.filter(actif=True), required=False, label="Employe")
    participants = forms.ModelMultipleChoiceField(queryset=Employe.objects.filter(actif=True), required=False, label="Participants")
    contenu = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Decrivez votre besoin RH..."}), required=False, label="Message")
    piece_jointe = forms.FileField(required=False, label="Piece jointe")

    class Meta:
        model = ConversationRH
        fields = ["employe", "participants", "sujet", "categorie", "priorite", "contenu", "piece_jointe"]

    def __init__(self, *args, user_profile=None, **kwargs):
        self.user_profile = user_profile
        super().__init__(*args, **kwargs)
        self.fields["employe"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")
        self.fields["participants"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")
        self.fields["sujet"].required = False
        self.fields["sujet"].help_text = "Optionnel: le systeme cree un nom Conversation N automatiquement."
        if not user_profile or user_profile.role not in {"ADMIN", "RESPONSABLE_RH"}:
            self.fields["employe"].widget = forms.HiddenInput()
            self.fields["employe"].required = False
            self.fields["participants"].widget = forms.MultipleHiddenInput()

    def clean_sujet(self):
        value = (self.cleaned_data.get("sujet") or "").strip()
        if value and len(value) < 3:
            raise ValidationError("Le sujet doit contenir au moins 3 caracteres.")
        return value

    def clean_contenu(self):
        return (self.cleaned_data.get("contenu") or "").strip()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("contenu") and not cleaned.get("piece_jointe"):
            raise ValidationError("Ajoutez un message ou une piece jointe.")
        if self.user_profile and self.user_profile.role in {"ADMIN", "RESPONSABLE_RH"} and not cleaned.get("employe"):
            self.add_error("employe", "Choisissez un employe destinataire.")
        return cleaned


class MessageRHForm(BootstrapModelForm):
    piece_jointe = forms.FileField(required=False, label="Piece jointe")

    class Meta:
        model = MessageRH
        fields = ["contenu", "piece_jointe"]
        widgets = {"contenu": forms.Textarea(attrs={"rows": 3, "placeholder": "Ecrire une reponse..."})}

    def clean_contenu(self):
        value = (self.cleaned_data.get("contenu") or "").strip()
        return value

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("contenu") and not cleaned.get("piece_jointe"):
            raise ValidationError("Ajoutez un message ou une piece jointe.")
        return cleaned


class ConversationRHCloseForm(forms.Form):
    motif_cloture = forms.ChoiceField(choices=ConversationRH.CLOSE_REASONS, label="Motif de cloture")
    detail_cloture = forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Precisez la decision ou la prochaine reference utile..."}), required=False, label="Detail")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control" if isinstance(field.widget, forms.Textarea) else "form-select")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("motif_cloture") == "other" and not (cleaned.get("detail_cloture") or "").strip():
            self.add_error("detail_cloture", "Ajoutez une explication pour le motif Autre.")
        return cleaned


class ConversationRHRenameForm(forms.Form):
    sujet = forms.CharField(max_length=120, label="Nom du ticket")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sujet"].widget.attrs.setdefault("class", "form-control")

    def clean_sujet(self):
        value = (self.cleaned_data.get("sujet") or "").strip()
        if len(value) < 3:
            raise ValidationError("Le nom doit contenir au moins 3 caracteres.")
        return value


class ConversationRHParticipantForm(forms.Form):
    employe = forms.ModelChoiceField(queryset=Employe.objects.filter(actif=True), label="Participant")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employe"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")
        self.fields["employe"].widget.attrs.setdefault("class", "form-select")


class ConversationRHRatingForm(forms.Form):
    note_support = forms.IntegerField(min_value=1, max_value=5, label="Note")
    note_commentaire = forms.CharField(widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Commentaire optionnel"}), required=False, label="Commentaire")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note_support"].widget.attrs.setdefault("class", "form-control")
        self.fields["note_commentaire"].widget.attrs.setdefault("class", "form-control")


class ActualiteForm(BootstrapModelForm):
    class Meta:
        model = Actualite
        fields = ["titre", "contenu", "audience", "departement", "role_cible", "statut", "date_publication", "date_evenement", "image"]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 5}),
            "date_publication": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "date_evenement": forms.DateInput(attrs={"type": "date"}),
        }


class CommandeProduitForm(BootstrapModelForm):
    class Meta:
        model = CommandeProduit
        fields = ["produit", "quantite"]

    def __init__(self, *args, employe=None, **kwargs):
        self.employe = employe
        super().__init__(*args, **kwargs)
        self.fields["produit"].queryset = Produit.objects.filter(actif=True, stock_disponible__gt=0)

    def clean_quantite(self):
        value = self.cleaned_data.get("quantite")
        if not value or value <= 0:
            raise ValidationError("La quantite doit etre superieure a 0.")
        return value

    def clean(self):
        cleaned = super().clean()
        # TRAITEMENT BOUTIQUE — verifie le stock et le solde de points avant commande.
        produit = cleaned.get("produit")
        quantite = cleaned.get("quantite") or 0
        if produit and quantite:
            if produit.stock_disponible < quantite:
                raise ValidationError("Stock insuffisant.")
            compte = getattr(self.employe, "compte_points", None)
            if not compte or compte.solde_points < produit.cout_points * quantite:
                raise ValidationError("Points insuffisants pour cette commande.")
        return cleaned


class ProduitForm(BootstrapModelForm):
    class Meta:
        model = Produit
        fields = ["nom", "categorie", "description", "image", "cout_points", "stock_disponible", "actif"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_nom(self):
        value = (self.cleaned_data.get("nom") or "").strip()
        if len(value) < 2:
            raise ValidationError("Le nom du produit doit contenir au moins 2 caracteres.")
        return value


class AjustementPointsManuelForm(BootstrapModelForm):
    class Meta:
        model = AjustementPointsManuel
        fields = ["employe", "type_adjustement", "nombre_points", "motif_obligatoire", "reclamation_liee"]
        widgets = {"motif_obligatoire": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reclamation_liee"].required = False


class ReclamationRHForm(BootstrapModelForm):
    class Meta:
        model = ReclamationRH
        fields = ["type_reclamation", "sujet", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_sujet(self):
        value = (self.cleaned_data.get("sujet") or "").strip()
        if len(value) < 3:
            raise ValidationError("Le sujet doit contenir au moins 3 caracteres.")
        return value

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if len(value) < 10:
            raise ValidationError("La description doit contenir au moins 10 caracteres.")
        return value


class TraitementReclamationForm(BootstrapModelForm):
    ACTIONS = [
        ("refuser", "Refuser la reclamation"),
        ("accepter", "Accepter sans compensation"),
        ("points", "Accepter avec ajout de points"),
        ("infos", "Demander plus d'informations"),
        ("cloturer", "Cloturer la reclamation"),
    ]
    action = forms.ChoiceField(choices=ACTIONS)

    class Meta:
        model = ReclamationRH
        fields = ["action", "reponse_rh", "points_accordes"]
        widgets = {"reponse_rh": forms.Textarea(attrs={"rows": 4})}

    def clean(self):
        cleaned = super().clean()
        # TRAITEMENT RECLAMATION — les points accordes et la reponse RH sont obligatoires selon l'action.
        if cleaned.get("action") == "points" and (cleaned.get("points_accordes") or 0) <= 0:
            self.add_error("points_accordes", "Les points accordes sont obligatoires.")
        if not (cleaned.get("reponse_rh") or "").strip():
            self.add_error("reponse_rh", "La reponse RH est obligatoire.")
        return cleaned


class RemunerationForm(BootstrapModelForm):
    class Meta:
        model = Remuneration
        fields = ["employe", "salaire_base", "prime", "devise", "date_effet", "actif"]
        widgets = {"date_effet": forms.DateInput(attrs={"type": "date"})}

    def clean_salaire_base(self):
        value = self.cleaned_data.get("salaire_base")
        if value is not None and value < 0:
            raise ValidationError("Le salaire de base ne peut pas etre negatif.")
        return value

    def clean_prime(self):
        value = self.cleaned_data.get("prime")
        if value is not None and value < 0:
            raise ValidationError("La prime ne peut pas etre negative.")
        return value


class PlanningShiftForm(BootstrapModelForm):
    class Meta:
        model = PlanningShift
        fields = ["titre", "employe", "departement", "service", "lieu", "plan_type", "recurrence_rule", "date_debut", "date_fin", "permanent_end_time", "pause_minutes", "pause_debut", "statut", "notes"]
        widgets = {
            "date_debut": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "date_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "permanent_end_time": forms.TimeInput(attrs={"type": "time"}),
            "pause_debut": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employe"].required = False
        self.fields["departement"].required = False
        self.fields["service"].required = False
        self.fields["employe"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")

    def clean_titre(self):
        value = (self.cleaned_data.get("titre") or "").strip()
        if len(value) < 2:
            raise ValidationError("Le titre du shift est obligatoire.")
        return value

    def clean_date_debut(self):
        value = self.cleaned_data.get("date_debut")
        if value and self.cleaned_data.get("plan_type") != "permanent" and not self.instance.pk and value < timezone.now():
            raise ValidationError("Le debut du shift ne peut pas etre dans le passe.")
        return value


class PlanningBulkForm(forms.Form):
    SCOPE_CHOICES = [
        ("service", "Un service"),
        ("departement", "Un departement"),
        ("company", "Toute l'entreprise"),
        ("employees", "Selection d'employes"),
    ]
    scope = forms.ChoiceField(choices=SCOPE_CHOICES, label="Cible")
    titre = forms.CharField(max_length=160, initial="Shift", label="Nom du shift")
    departement = forms.ModelChoiceField(queryset=Departement.objects.all(), required=False, label="Departement")
    service = forms.ModelChoiceField(queryset=Service.objects.select_related("departement"), required=False, label="Service")
    employes = forms.ModelMultipleChoiceField(queryset=Employe.objects.filter(actif=True), required=False, label="Employes")
    lieu = forms.CharField(max_length=255, required=False, initial="Casablanca", label="Lieu")
    date_debut = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), label="Debut")
    date_fin = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), required=False, label="Fin")
    plan_type = forms.ChoiceField(choices=PlanningShift.PLAN_TYPES, initial="normal", label="Type")
    recurrence_rule = forms.ChoiceField(choices=PlanningShift.RECURRENCE_RULES, initial="none", required=False, label="Recurrence")
    permanent_end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}), required=False, label="Fin standard")
    pause_minutes = forms.IntegerField(min_value=0, max_value=240, initial=0, label="Pause")
    pause_debut = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), required=False, label="Debut pause")
    statut = forms.ChoiceField(choices=[("publie", "Publier"), ("brouillon", "Brouillon")], initial="publie", label="Mode")
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False, label="Notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs.setdefault("class", "form-select")
                field.widget.attrs.setdefault("size", "8")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        self.fields["employes"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")
        date_debut = cleaned.get("date_debut")
        date_fin = cleaned.get("date_fin")
        plan_type = cleaned.get("plan_type") or "normal"
        recurrence_rule = cleaned.get("recurrence_rule") or "none"
        pause_debut = cleaned.get("pause_debut")
        pause_minutes = cleaned.get("pause_minutes") or 0
        if date_debut and plan_type != "permanent" and date_debut < timezone.now():
            self.add_error("date_debut", "Le debut du shift ne peut pas etre dans le passe.")
        if plan_type == "normal" and not date_fin:
            self.add_error("date_fin", "La fin est obligatoire pour un planning normal.")
        if plan_type == "permanent" and not (date_fin or cleaned.get("permanent_end_time")):
            self.add_error("permanent_end_time", "Indiquez l'heure de fin standard du plan permanent.")
        if plan_type == "normal" and recurrence_rule != "none":
            self.add_error("recurrence_rule", "La recurrence est disponible pour les plans permanents. Creez des shifts normaux separes pour une recurrence operationnelle.")
        if date_debut and date_fin and date_fin <= date_debut:
            self.add_error("date_fin", "Overnight shifts are not supported yet. Please create two separate shifts or choose a valid same-day time range.")
        if date_debut and date_fin and pause_minutes:
            duration_minutes = (date_fin - date_debut).total_seconds() / 60
            if pause_minutes >= duration_minutes:
                self.add_error("pause_minutes", "La pause doit etre plus courte que le shift.")
        if pause_debut and not pause_minutes:
            self.add_error("pause_debut", "Indiquez une duree de pause.")
        if pause_debut and date_debut and pause_debut < date_debut:
            self.add_error("pause_debut", "La pause doit commencer apres le debut du shift.")
        if pause_debut and date_fin and pause_debut + timezone.timedelta(minutes=pause_minutes) > date_fin:
            self.add_error("pause_debut", "La pause doit se terminer avant la fin du shift.")
        if scope == "service" and not cleaned.get("service"):
            self.add_error("service", "Choisissez un service.")
        if scope == "departement" and not cleaned.get("departement"):
            self.add_error("departement", "Choisissez un departement.")
        if scope == "employees" and not cleaned.get("employes"):
            self.add_error("employes", "Choisissez au moins un employe.")
        return cleaned


class TacheEquipeForm(BootstrapModelForm):
    class Meta:
        model = TacheEquipe
        fields = ["titre", "description", "mode_affectation", "employe", "departement", "service", "shift", "priorite", "taille", "date_debut", "date_fin", "date_limite", "auto_assign_at", "max_acceptations"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "date_debut": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "date_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "date_limite": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "auto_assign_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, user_profile=None, **kwargs):
        self.user_profile = user_profile
        super().__init__(*args, **kwargs)
        self.fields["employe"].required = False
        self.fields["departement"].required = False
        self.fields["service"].required = False
        self.fields["shift"].required = False
        if user_profile and user_profile.role == "RESPONSABLE_HIERARCHIQUE" and user_profile.employe:
            scoped = Employe.objects.filter(actif=True, responsable=user_profile.employe)
            self.fields["employe"].queryset = scoped.select_related("departement", "service")
            self.fields["departement"].queryset = Departement.objects.filter(pk__in=scoped.exclude(departement__isnull=True).values_list("departement_id", flat=True)).distinct()
            self.fields["service"].queryset = Service.objects.filter(pk__in=scoped.exclude(service__isnull=True).values_list("service_id", flat=True)).select_related("departement").distinct()
        else:
            self.fields["employe"].queryset = Employe.objects.filter(actif=True).select_related("departement", "service")
            self.fields["departement"].queryset = Departement.objects.all()
            self.fields["service"].queryset = Service.objects.select_related("departement")
        self.fields["shift"].queryset = PlanningShift.objects.exclude(statut__in=["annule", "termine"])

    def clean_titre(self):
        value = (self.cleaned_data.get("titre") or "").strip()
        if len(value) < 2:
            raise ValidationError("Le titre de la tache est obligatoire.")
        return value

    def clean_date_limite(self):
        value = self.cleaned_data.get("date_limite")
        if value and not self.instance.pk and value < timezone.now():
            raise ValidationError("La date limite ne peut pas etre dans le passe.")
        return value

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode_affectation")
        employe = cleaned.get("employe")
        departement = cleaned.get("departement")
        service = cleaned.get("service")
        debut = cleaned.get("date_debut")
        fin = cleaned.get("date_fin")
        deadline = cleaned.get("date_limite")
        auto_at = cleaned.get("auto_assign_at")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "La date de fin doit etre apres le debut.")
        if deadline and debut and deadline < debut:
            self.add_error("date_limite", "La deadline ne peut pas etre avant le debut.")
        if auto_at and deadline and auto_at > deadline:
            self.add_error("auto_assign_at", "L'auto-affectation doit intervenir avant la deadline.")
        if mode == "direct" and not employe:
            self.add_error("employe", "Choisissez un employe pour une affectation directe.")
        if mode == "open" and employe:
            self.add_error("employe", "Laissez l'employe vide pour une tache ouverte.")
        if self.user_profile and self.user_profile.role == "RESPONSABLE_HIERARCHIQUE":
            scoped = Employe.objects.filter(actif=True, responsable=self.user_profile.employe)
            if not scoped.exists():
                raise ValidationError("Aucun collaborateur actif n'est rattache a votre perimetre manager.")
            if employe and not scoped.filter(pk=employe.pk).exists():
                self.add_error("employe", "Vous ne pouvez assigner que vos collaborateurs directs.")
            if departement and not scoped.filter(departement=departement).exists():
                self.add_error("departement", "Ce departement n'appartient pas a votre perimetre.")
            if service and not scoped.filter(service=service).exists():
                self.add_error("service", "Ce service n'appartient pas a votre perimetre.")
        return cleaned
