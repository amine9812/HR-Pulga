from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StatutDemande(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    EN_COURS = "EN_COURS", "En cours"
    VALIDEE = "VALIDEE", "Validee"
    REFUSEE = "REFUSEE", "Refusee"
    CLOTUREE = "CLOTUREE", "Cloturee"


class TypeConge(models.TextChoices):
    ANNUEL = "ANNUEL", "Annuel"
    MALADIE = "MALADIE", "Maladie"
    MATERNITE = "MATERNITE", "Maternite"
    SANS_SOLDE = "SANS_SOLDE", "Sans solde"


class Departement(models.Model):
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle


class Service(models.Model):
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    departement = models.ForeignKey(Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name="services")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle


class Poste(models.Model):
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    niveau = models.CharField(max_length=255, blank=True)
    rang_hierarchique = models.PositiveSmallIntegerField(default=50)
    est_direction = models.BooleanField(default=False)
    est_manager = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle


class Employe(models.Model):
    # ==================================================
    # TABLE : EMPLOYE
    # Gestion du profil RH, poste, departement et hierarchie
    # ==================================================
    matricule = models.CharField(max_length=100, unique=True)
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255)
    email = models.EmailField()
    telephone = models.CharField(max_length=80, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    date_embauche = models.DateField()
    adresse = models.TextField(blank=True)
    photo = models.ImageField(upload_to="uploads/photos/", null=True, blank=True)
    departement = models.ForeignKey(Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name="employes")
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="employes")
    poste = models.ForeignKey(Poste, on_delete=models.SET_NULL, null=True, blank=True, related_name="employes")
    responsable = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="collaborateurs")
    localisation = models.CharField(max_length=255, blank=True, default="Casablanca")
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom", "prenom"]

    def __str__(self):
        return self.nom_complet

    @property
    def nom_complet(self):
        return f"{self.prenom or ''} {self.nom or ''}".strip()

    @property
    def anciennete_annees(self):
        if not self.date_embauche:
            return 0
        return max(0, int((timezone.localdate() - self.date_embauche).days / 365))

    def clean(self):
        super().clean()
        # TRAITEMENT HIERARCHIE — empeche un employe d'etre son propre responsable ou de creer une boucle.
        if self.responsable_id and self.pk and self.responsable_id == self.pk:
            raise ValidationError({"responsable": "Un employe ne peut pas etre son propre responsable."})
        manager = self.responsable
        visited = set()
        while manager:
            if manager.pk == self.pk:
                raise ValidationError({"responsable": "Cette affectation cree une boucle hierarchique."})
            if manager.pk in visited:
                raise ValidationError({"responsable": "La chaine hierarchique contient deja une boucle."})
            visited.add(manager.pk)
            manager = manager.responsable


class DemandeConge(models.Model):
    # ==================================================
    # TABLE : DEMANDE_CONGE
    # Gestion des conges, dates, statuts et solde
    # ==================================================
    type = models.CharField(max_length=30, choices=TypeConge.choices)
    date_debut = models.DateField()
    date_fin = models.DateField()
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=30, choices=StatutDemande.choices, default=StatutDemande.EN_ATTENTE)
    APPROVAL_PENDING = "pending"
    APPROVAL_APPROVED = "approved"
    APPROVAL_REFUSED = "refused"
    APPROVAL_CHOICES = [
        (APPROVAL_PENDING, "En attente"),
        (APPROVAL_APPROVED, "Approuve"),
        (APPROVAL_REFUSED, "Refuse"),
    ]
    manager_approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default=APPROVAL_PENDING)
    manager_approved_by = models.ForeignKey(
        "Employe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conges_approuves_manager",
    )
    manager_approved_at = models.DateTimeField(null=True, blank=True)
    manager_refusal_reason = models.TextField(blank=True)
    hr_approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default=APPROVAL_PENDING)
    hr_approved_by = models.ForeignKey(
        "Employe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conges_approuves_rh",
    )
    hr_approved_at = models.DateTimeField(null=True, blank=True)
    hr_refusal_reason = models.TextField(blank=True)
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="conges")
    traitee_par = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conges_traites",
    )
    date_traitement = models.DateTimeField(null=True, blank=True)
    commentaire_reponse = models.TextField(blank=True)
    date_creation = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.employe} - {self.type}"

    @property
    def duree_jours(self):
        if not self.date_debut or not self.date_fin:
            return 0
        return (self.date_fin - self.date_debut).days + 1

    def clean(self):
        super().clean()
        # TRAITEMENT DATE — bloque une demande en attente dans le passe et une date de fin avant le debut.
        today = timezone.localdate()
        if self.date_debut and self.date_debut < today and self.statut == StatutDemande.EN_ATTENTE:
            raise ValidationError({"date_debut": "La date de debut ne peut pas etre dans le passe."})
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin doit etre apres la date de debut."})
        if self.date_traitement and self.date_creation and self.date_traitement < self.date_creation:
            raise ValidationError({"date_traitement": "La date de traitement ne peut pas etre avant la creation."})

    @property
    def manager_approval_label(self):
        return dict(self.APPROVAL_CHOICES).get(self.manager_approval_status, "En attente")

    @property
    def hr_approval_label(self):
        return dict(self.APPROVAL_CHOICES).get(self.hr_approval_status, "En attente")

    @property
    def workflow_waiting_label(self):
        if self.statut == StatutDemande.REFUSEE:
            refused_by = []
            if self.manager_approval_status == self.APPROVAL_REFUSED:
                refused_by.append("manager")
            if self.hr_approval_status == self.APPROVAL_REFUSED:
                refused_by.append("RH")
            return "Refuse par " + " et ".join(refused_by) if refused_by else "Refuse"
        if self.statut == StatutDemande.VALIDEE:
            return "Approuve par manager et RH"
        waiting = []
        if self.manager_approval_status == self.APPROVAL_PENDING:
            waiting.append("manager")
        if self.hr_approval_status == self.APPROVAL_PENDING:
            waiting.append("RH")
        return "En attente " + " et ".join(waiting) if waiting else "En cours"

    def recompute_final_status(self):
        if self.manager_approval_status == self.APPROVAL_REFUSED or self.hr_approval_status == self.APPROVAL_REFUSED:
            self.statut = StatutDemande.REFUSEE
        elif self.manager_approval_status == self.APPROVAL_APPROVED and self.hr_approval_status == self.APPROVAL_APPROVED:
            self.statut = StatutDemande.VALIDEE
        elif self.manager_approval_status == self.APPROVAL_APPROVED or self.hr_approval_status == self.APPROVAL_APPROVED:
            self.statut = StatutDemande.EN_COURS
        else:
            self.statut = StatutDemande.EN_ATTENTE
        return self.statut


class DemandeAdministrative(models.Model):
    type_demande = models.CharField(max_length=255)
    description = models.TextField()
    statut = models.CharField(max_length=30, choices=StatutDemande.choices, default=StatutDemande.EN_ATTENTE)
    date_creation = models.DateTimeField(default=timezone.now)
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="demandes_administratives")
    traitee_par = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_admin_traitees",
    )
    date_traitement = models.DateTimeField(null=True, blank=True)
    reponse = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.type_demande} - {self.employe}"

    def clean(self):
        super().clean()
        if self.date_traitement and self.date_creation and self.date_traitement < self.date_creation:
            raise ValidationError({"date_traitement": "La date de traitement ne peut pas etre avant la creation."})


class Document(models.Model):
    fichier = models.FileField(upload_to="uploads/documents/")
    nom_fichier = models.CharField(max_length=255)
    nom_original = models.CharField(max_length=255)
    categorie = models.CharField(max_length=255, blank=True, default="General")
    chemin_fichier = models.CharField(max_length=500, blank=True)
    date_ajout = models.DateTimeField(default=timezone.now)
    taille = models.PositiveBigIntegerField(default=0)
    employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    demande_admin = models.ForeignKey(
        DemandeAdministrative,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    uploade_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents_uploades")
    archive = models.BooleanField(default=False)
    date_archivage = models.DateTimeField(null=True, blank=True)
    archive_par = models.ForeignKey(
        "accounts.UtilisateurProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_archives",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_ajout"]

    def __str__(self):
        return self.nom_original


class Notification(models.Model):
    message = models.TextField()
    date_envoi = models.DateTimeField(default=timezone.now)
    lue = models.BooleanField(default=False)
    destinataire = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.CASCADE, related_name="notifications")
    lien = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_envoi"]

    def __str__(self):
        return self.message[:80]


class HistoriqueAction(models.Model):
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    date_action = models.DateTimeField(default=timezone.now)
    utilisateur = models.ForeignKey(
        "accounts.UtilisateurProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
    )
    entite_concernee = models.CharField(max_length=255, blank=True)
    entite_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-date_action"]

    def __str__(self):
        return self.action


class SoldeConge(models.Model):
    # ==================================================
    # TABLE : SOLDE_CONGE
    # Solde disponible/utilise et protection contre les valeurs negatives
    # ==================================================
    employe = models.OneToOneField(Employe, on_delete=models.CASCADE, related_name="solde_conge")
    jours_disponibles = models.DecimalField(max_digits=6, decimal_places=2, default=22)
    jours_utilises = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        # TRAITEMENT SOLDE CONGE — le solde et les jours utilises ne peuvent pas etre negatifs.
        if self.jours_disponibles < 0 or self.jours_utilises < 0:
            raise ValidationError("Le solde de conges ne peut pas etre negatif.")


class MouvementSoldeConge(models.Model):
    solde = models.ForeignKey(SoldeConge, on_delete=models.CASCADE, related_name="mouvements")
    demande = models.ForeignKey(DemandeConge, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_solde")
    type_mouvement = models.CharField(max_length=40)
    jours = models.DecimalField(max_digits=6, decimal_places=2)
    solde_avant = models.DecimalField(max_digits=6, decimal_places=2)
    solde_apres = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.TextField(blank=True)
    date_mouvement = models.DateTimeField(default=timezone.now)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)


class ParametrePointage(models.Model):
    heure_debut_officielle = models.TimeField(default="09:00")
    heure_fin_officielle = models.TimeField(default="18:00")
    tolerance_retard_minutes = models.PositiveSmallIntegerField(default=10)
    heures_minimum_jour = models.DecimalField(max_digits=4, decimal_places=2, default=8)
    points_presence_normale = models.IntegerField(default=10)
    penalite_retard = models.IntegerField(default=5)
    penalite_sortie_anticipee = models.IntegerField(default=5)
    bonus_heures_supplementaires = models.IntegerField(default=3)
    actif = models.BooleanField(default=True)


class Pointage(models.Model):
    # ==================================================
    # TABLE : POINTAGE
    # Gestion entree/sortie, heures travaillees et points
    # ==================================================
    STATUTS = [
        ("present", "Present"),
        ("retard", "Retard"),
        ("sortie_anticipee", "Sortie anticipee"),
        ("incomplet", "Incomplet"),
        ("absent", "Absent"),
    ]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="pointages")
    shift = models.ForeignKey("PlanningShift", on_delete=models.SET_NULL, null=True, blank=True, related_name="pointages")
    date = models.DateField(default=timezone.localdate)
    heure_entree = models.DateTimeField(null=True, blank=True)
    heure_sortie = models.DateTimeField(null=True, blank=True)
    total_heures = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    statut = models.CharField(max_length=40, choices=STATUTS, default="incomplet")
    points_calcules = models.IntegerField(default=0)
    commentaire = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-heure_entree"]
        constraints = [models.UniqueConstraint(fields=["employe", "date"], name="unique_pointage_employe_date")]

    def clean(self):
        # TRAITEMENT POINTAGE — interdit une heure de sortie avant l'heure d'entree.
        if self.heure_entree and self.heure_sortie and self.heure_sortie < self.heure_entree:
            raise ValidationError("La sortie ne peut pas etre avant l'entree.")


class PlanningShift(models.Model):
    # ==================================================
    # TABLE : PLANNING_SHIFT
    # Planification des shifts, postes ouverts et conflits de disponibilite
    # ==================================================
    STATUTS = [
        ("brouillon", "Brouillon"),
        ("publie", "Publie"),
        ("ouvert", "Shift ouvert"),
        ("termine", "Termine"),
        ("annule", "Annule"),
    ]
    PLAN_TYPES = [
        ("normal", "Plan normal"),
        ("permanent", "Plan permanent"),
    ]
    RECURRENCE_RULES = [
        ("none", "Aucune"),
        ("weekdays", "Jours ouvrables"),
        ("daily", "Tous les jours"),
        ("weekly", "Hebdomadaire"),
        ("biweekly", "Toutes les deux semaines"),
        ("monthly", "Mensuelle"),
    ]
    employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts")
    departement = models.ForeignKey(Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts")
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts")
    titre = models.CharField(max_length=160, default="Shift")
    lieu = models.CharField(max_length=255, blank=True, default="Casablanca")
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField(null=True, blank=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES, default="normal")
    recurrence_rule = models.CharField(max_length=20, choices=RECURRENCE_RULES, default="none")
    permanent_end_time = models.TimeField(null=True, blank=True)
    pause_minutes = models.PositiveSmallIntegerField(default=0)
    pause_debut = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=30, choices=STATUTS, default="brouillon")
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="shifts_crees")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_debut", "employe__nom"]

    def __str__(self):
        assigned_to = self.employe.nom_complet if self.employe else "Non assigne"
        return f"{self.titre} - {assigned_to}"

    @property
    def duree_heures(self):
        if not self.date_debut:
            return 0
        end = self.date_fin
        if self.plan_type == "permanent" and not end and self.permanent_end_time:
            end = timezone.make_aware(timezone.datetime.combine(self.date_debut.date(), self.permanent_end_time))
            if end <= self.date_debut:
                end += timezone.timedelta(days=1)
        if not end:
            return 0
        seconds = (end - self.date_debut).total_seconds()
        return max(0, round((seconds / 3600) - (self.pause_minutes / 60), 2))

    @property
    def effective_end_time(self):
        if self.date_fin:
            return timezone.localtime(self.date_fin).time()
        if self.permanent_end_time:
            return self.permanent_end_time
        return None

    def clean(self):
        super().clean()
        if self.plan_type not in dict(self.PLAN_TYPES):
            raise ValidationError({"plan_type": "Type de planning invalide."})
        if self.recurrence_rule not in dict(self.RECURRENCE_RULES):
            raise ValidationError({"recurrence_rule": "Regle de recurrence invalide."})
        if self.plan_type == "normal" and self.recurrence_rule != "none":
            raise ValidationError({"recurrence_rule": "Les repetitions sont disponibles pour les plans permanents. Creez des shifts separes pour un planning normal recurrent."})
        if self.plan_type == "normal":
            self.permanent_end_time = None
        if self.plan_type == "permanent" and self.recurrence_rule == "none":
            self.recurrence_rule = "weekdays"
        if self.date_debut and not self.pk and self.plan_type == "normal" and self.statut not in {"annule", "termine"} and self.date_debut < timezone.now():
            raise ValidationError({"date_debut": "Le debut du shift ne peut pas etre dans le passe."})
        if self.plan_type == "normal" and not self.date_fin:
            raise ValidationError({"date_fin": "La fin du shift est obligatoire pour un planning normal."})
        if self.plan_type == "permanent" and not (self.date_fin or self.permanent_end_time):
            raise ValidationError({"permanent_end_time": "Indiquez l'heure de fin standard du plan permanent."})
        effective_end = self.date_fin
        if self.plan_type == "permanent" and not effective_end and self.permanent_end_time and self.date_debut:
            effective_end = timezone.make_aware(timezone.datetime.combine(self.date_debut.date(), self.permanent_end_time))
            if effective_end <= self.date_debut:
                effective_end += timezone.timedelta(days=1)
        if self.date_debut and effective_end and effective_end <= self.date_debut:
            raise ValidationError({"date_fin": "Overnight shifts are not supported yet. Please create two separate shifts or choose a valid same-day time range."})
        if self.date_debut and effective_end and self.pause_minutes:
            shift_minutes = (effective_end - self.date_debut).total_seconds() / 60
            if self.pause_minutes >= shift_minutes:
                raise ValidationError({"pause_minutes": "La pause doit etre plus courte que le shift."})
        if self.pause_debut:
            if not self.pause_minutes:
                raise ValidationError({"pause_debut": "Une heure de debut de pause exige une duree de pause."})
            if self.date_debut and self.pause_debut < self.date_debut:
                raise ValidationError({"pause_debut": "La pause doit commencer apres le debut du shift."})
            if effective_end and self.pause_debut + timezone.timedelta(minutes=self.pause_minutes) > effective_end:
                raise ValidationError({"pause_debut": "La pause doit se terminer avant la fin du shift."})
        if self.statut == "publie" and not self.employe:
            self.statut = "ouvert"
        if self.employe and self.plan_type == "permanent" and self.statut != "annule":
            existing = PlanningShift.objects.filter(employe=self.employe, plan_type="permanent").exclude(statut="annule")
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("Cet employe a deja un plan permanent actif.")
        if self.employe and self.date_debut and effective_end and self.statut != "annule" and self.plan_type == "normal":
            overlaps = PlanningShift.objects.filter(
                employe=self.employe,
                date_debut__lt=effective_end,
                date_fin__gt=self.date_debut,
                plan_type="normal",
            ).exclude(statut="annule")
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("Ce shift chevauche deja un autre planning de cet employe.")
            leave_conflict = DemandeConge.objects.filter(
                employe=self.employe,
                statut=StatutDemande.VALIDEE,
                date_debut__lte=self.date_fin.date(),
                date_fin__gte=self.date_debut.date(),
            ).exists()
            if leave_conflict:
                raise ValidationError("Cet employe a deja un conge valide sur cette periode.")


class TacheEquipe(models.Model):
    # ==================================================
    # TABLE : TACHE_EQUIPE
    # Assignation de taches operationnelles aux equipes ou employes
    # ==================================================
    STATUTS = [
        ("brouillon", "Brouillon"),
        ("a_faire", "Assignee"),
        ("ouverte", "Ouverte"),
        ("acceptee", "Acceptee"),
        ("en_cours", "En cours"),
        ("soumise", "En attente d'approbation"),
        ("terminee", "Terminee"),
        ("changements", "Changements demandes"),
        ("rejetee", "Rejetee"),
        ("annulee", "Annulee"),
        ("archivee", "Archivee"),
    ]
    PRIORITES = [("basse", "Basse"), ("normale", "Normale"), ("haute", "Haute"), ("urgente", "Urgente")]
    ASSIGNMENT_MODES = [("direct", "Un employe"), ("team", "Toute l'equipe"), ("open", "Tache ouverte")]
    TAILLES = [("petite", "Petite"), ("moyenne", "Moyenne"), ("grande", "Grande")]
    titre = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches")
    accepte_par = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches_acceptees")
    manager = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches_manager")
    departement = models.ForeignKey(Departement, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches")
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches")
    shift = models.ForeignKey(PlanningShift, on_delete=models.SET_NULL, null=True, blank=True, related_name="taches")
    priorite = models.CharField(max_length=20, choices=PRIORITES, default="normale")
    mode_affectation = models.CharField(max_length=20, choices=ASSIGNMENT_MODES, default="direct")
    taille = models.CharField(max_length=20, choices=TAILLES, default="moyenne")
    statut = models.CharField(max_length=30, choices=STATUTS, default="a_faire")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    date_limite = models.DateTimeField(null=True, blank=True)
    auto_assign_at = models.DateTimeField(null=True, blank=True)
    max_acceptations = models.PositiveSmallIntegerField(default=1)
    message_completion = models.TextField(blank=True)
    feedback_manager = models.TextField(blank=True)
    points_suggeres = models.PositiveIntegerField(default=0)
    points_attribues = models.PositiveIntegerField(default=0)
    points_attribues_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="points_taches_attribues")
    points_attribues_at = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="taches_crees")
    terminee_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="taches_terminees")
    date_creation = models.DateTimeField(default=timezone.now)
    date_completion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["statut", "date_limite", "-date_creation"]

    def __str__(self):
        return self.titre

    def clean(self):
        if not (self.titre or "").strip():
            raise ValidationError("Le titre de la tache est obligatoire.")
        if not (self.description or "").strip():
            raise ValidationError("La description de la tache est obligatoire.")
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin doit etre apres le debut."})
        if self.date_limite and not self.pk and self.statut not in {"terminee", "annulee"} and self.date_limite < timezone.now():
            raise ValidationError({"date_limite": "La date limite ne peut pas etre dans le passe."})
        if self.date_limite and self.date_limite < self.date_creation:
            raise ValidationError({"date_limite": "La date limite ne peut pas etre avant la creation."})
        if self.mode_affectation == "direct" and not self.employe:
            raise ValidationError({"employe": "Choisissez un employe ou utilisez une tache ouverte."})
        if self.mode_affectation == "open" and self.employe and self.statut == "ouverte":
            raise ValidationError({"employe": "Une tache ouverte ne doit pas etre assignee au depart."})
        if self.points_attribues and self.points_attribues > 30:
            raise ValidationError({"points_attribues": "Le maximum par tache est de 30 points."})

    @property
    def assignee(self):
        return self.employe or self.accepte_par

    @property
    def is_overdue(self):
        return bool(self.date_limite and self.statut not in {"terminee", "annulee", "archivee"} and self.date_limite < timezone.now())


class ComptePoints(models.Model):
    # ==================================================
    # TABLE : COMPTE_POINTS
    # Solde de points actuel de l'employe
    # ==================================================
    employe = models.OneToOneField(Employe, on_delete=models.CASCADE, related_name="compte_points")
    solde_points = models.IntegerField(default=0)

    def clean(self):
        # TRAITEMENT POINTS — empeche un solde de points negatif.
        if self.solde_points < 0:
            raise ValidationError("Le solde de points ne peut pas etre negatif.")


class TransactionPoints(models.Model):
    # ==================================================
    # TABLE : TRANSACTION_POINTS
    # Historique des gains, deductions et corrections de points
    # ==================================================
    TYPES = [("gain", "Gain"), ("deduction", "Deduction"), ("achat", "Achat"), ("correction", "Correction"), ("remboursement", "Remboursement")]
    SOURCES = [("pointage", "Pointage"), ("boutique", "Boutique"), ("conge", "Conge"), ("formation", "Formation"), ("manuel", "Manuel"), ("reclamation", "Reclamation"), ("tache", "Tache")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="transactions_points")
    type_transaction = models.CharField(max_length=30, choices=TYPES)
    source = models.CharField(max_length=30, choices=SOURCES)
    points = models.IntegerField()
    solde_avant = models.IntegerField()
    solde_apres = models.IntegerField()
    description = models.TextField()
    date_transaction = models.DateTimeField(default=timezone.now)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    objet_lie = models.CharField(max_length=120, blank=True)


class AjustementPointsManuel(models.Model):
    TYPES = [("ajout", "Ajout"), ("retrait", "Retrait"), ("correction", "Correction"), ("remboursement", "Remboursement")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="ajustements_points")
    type_adjustement = models.CharField(max_length=30, choices=TYPES)
    nombre_points = models.PositiveIntegerField()
    motif_obligatoire = models.TextField()
    reclamation_liee = models.ForeignKey("ReclamationRH", on_delete=models.SET_NULL, null=True, blank=True)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="ajustements_crees")
    date_creation = models.DateTimeField(default=timezone.now)

    def clean(self):
        if self.nombre_points <= 0:
            raise ValidationError("Le nombre de points doit etre superieur a 0.")
        if not (self.motif_obligatoire or "").strip():
            raise ValidationError("Le motif est obligatoire.")


class Formation(models.Model):
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    categorie = models.CharField(max_length=120, blank=True)
    duree_estimee_heures = models.PositiveSmallIntegerField(default=1)
    points_recompense = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(default=timezone.now)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.titre


class AffectationFormation(models.Model):
    # ==================================================
    # TABLE : AFFECTATION_FORMATION
    # Suivi des formations assignees et attribution unique des points
    # ==================================================
    STATUTS = [("assignee", "Assignee"), ("en_cours", "En cours"), ("terminee", "Terminee"), ("en_retard", "En retard"), ("annulee", "Annulee")]
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name="affectations")
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="formations_assignees")
    assigne_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    date_affectation = models.DateField(default=timezone.localdate)
    date_limite = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=30, choices=STATUTS, default="assignee")
    date_completion = models.DateField(null=True, blank=True)
    points_attribues = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["formation", "employe"], condition=models.Q(statut__in=["assignee", "en_cours"]), name="unique_formation_active_employe")]

    def clean(self):
        # TRAITEMENT DATE FORMATION — la limite et la completion ne peuvent pas preceder l'affectation.
        if self.date_limite and self.date_limite < self.date_affectation:
            raise ValidationError({"date_limite": "La date limite ne peut pas etre avant l'affectation."})
        if self.date_completion and self.date_completion < self.date_affectation:
            raise ValidationError({"date_completion": "La completion ne peut pas etre avant l'affectation."})


class ConversationRH(models.Model):
    STATUTS = [
        ("ouverte", "En cours"),
        ("en_attente", "En attente RH"),
        ("attente_employe", "En attente employe"),
        ("cloturee", "Cloturee"),
    ]
    PRIORITES = [("basse", "Basse"), ("normale", "Normale"), ("haute", "Haute"), ("urgente", "Urgente")]
    CATEGORIES = [
        ("general", "Question generale"),
        ("administratif", "Administratif"),
        ("paie", "Paie"),
        ("conge", "Conges et absences"),
        ("documents", "Documents RH"),
        ("autre", "Autre"),
    ]
    CLOSE_REASONS = [
        ("resolved", "Issue resolved"),
        ("handled", "Request handled"),
        ("duplicate", "Duplicate request"),
        ("insufficient_info", "Not enough information provided"),
        ("not_hr", "Not HR-related"),
        ("invalid", "Invalid or non-actionable request"),
        ("no_response", "Closed after no response"),
        ("other", "Other"),
    ]
    sujet = models.CharField(max_length=255)
    numero_ticket = models.PositiveIntegerField(null=True, blank=True, unique=True)
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="conversations_rh")
    participants = models.ManyToManyField(Employe, blank=True, related_name="tickets_rh_participation")
    responsable_rh = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField(max_length=30, choices=STATUTS, default="ouverte")
    categorie = models.CharField(max_length=40, choices=CATEGORIES, default="general")
    priorite = models.CharField(max_length=20, choices=PRIORITES, default="normale")
    cloture_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets_rh_clotures")
    date_cloture = models.DateTimeField(null=True, blank=True)
    motif_cloture = models.CharField(max_length=40, choices=CLOSE_REASONS, blank=True)
    detail_cloture = models.TextField(blank=True)
    note_support = models.PositiveSmallIntegerField(null=True, blank=True)
    note_commentaire = models.TextField(blank=True)
    note_par = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets_rh_notes")
    date_note = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(default=timezone.now)
    date_derniere_reponse = models.DateTimeField(default=timezone.now)

    @property
    def is_closed(self):
        return self.statut == "cloturee"

    @property
    def is_claimed(self):
        return bool(self.responsable_rh_id)

    def clean(self):
        if self.note_support is not None and not 1 <= self.note_support <= 5:
            raise ValidationError({"note_support": "La note doit etre comprise entre 1 et 5."})


class MessageRH(models.Model):
    conversation = models.ForeignKey(ConversationRH, on_delete=models.CASCADE, related_name="messages")
    expediteur = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.CASCADE, related_name="messages_envoyes")
    destinataire = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="messages_recus")
    contenu = models.TextField(blank=True)
    piece_jointe = models.FileField(upload_to="uploads/messages_rh/", null=True, blank=True)
    nom_piece_jointe = models.CharField(max_length=255, blank=True)
    date_envoi = models.DateTimeField(default=timezone.now)
    lu = models.BooleanField(default=False)

    def clean(self):
        # TRAITEMENT MESSAGE RH — accepte un texte, une piece jointe, ou les deux.
        if not (self.contenu or "").strip() and not self.piece_jointe:
            raise ValidationError("Ajoutez un message ou une piece jointe.")


class SupportRHReward(models.Model):
    STATUTS = [("pending", "Pending manager approval"), ("approved", "Approved"), ("rejected", "Rejected"), ("awarded", "Points awarded")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="recompenses_support_rh")
    mois = models.DateField()
    total_etoiles = models.PositiveIntegerField(default=0)
    rang = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=20, choices=STATUTS, default="pending")
    genere_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="recompenses_support_generees")
    approuve_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="recompenses_support_approuvees")
    date_generation = models.DateTimeField(default=timezone.now)
    date_decision = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["employe", "mois"], name="unique_support_reward_employee_month")]
        ordering = ["mois", "rang", "-total_etoiles"]


class Actualite(models.Model):
    AUDIENCES = [("tous", "Tous"), ("departement", "Departement"), ("role", "Role")]
    STATUTS = [("brouillon", "Brouillon"), ("publiee", "Publiee"), ("archivee", "Archivee")]
    titre = models.CharField(max_length=255)
    contenu = models.TextField()
    auteur = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    audience = models.CharField(max_length=30, choices=AUDIENCES, default="tous")
    departement = models.ForeignKey(Departement, on_delete=models.SET_NULL, null=True, blank=True)
    role_cible = models.CharField(max_length=40, blank=True)
    statut = models.CharField(max_length=30, choices=STATUTS, default="brouillon")
    date_publication = models.DateTimeField(null=True, blank=True)
    date_evenement = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to="uploads/actualites/", null=True, blank=True)

    def clean(self):
        if not (self.titre or "").strip() or not (self.contenu or "").strip():
            raise ValidationError("Le titre et le contenu sont obligatoires.")
        if self.date_publication and self.date_evenement and self.date_evenement < self.date_publication.date():
            raise ValidationError({"date_evenement": "La date d'evenement ne peut pas etre avant la publication."})


class CategorieProduit(models.Model):
    nom = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.nom


class Produit(models.Model):
    nom = models.CharField(max_length=255)
    categorie = models.ForeignKey(CategorieProduit, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="uploads/produits/", null=True, blank=True)
    cout_points = models.PositiveIntegerField(default=0)
    stock_disponible = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.nom


class AffectationMateriel(models.Model):
    STATUTS = [("attribue", "Attribue"), ("livre", "Livre"), ("retourne", "Retourne"), ("perdu", "Perdu"), ("remplace", "Remplace")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="materiels")
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)
    attribue_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    date_attribution = models.DateTimeField(default=timezone.now)
    statut = models.CharField(max_length=30, choices=STATUTS, default="attribue")
    commentaire = models.TextField(blank=True)


class CommandeProduit(models.Model):
    # ==================================================
    # TABLE : COMMANDE_PRODUIT
    # Commandes boutique, cout en points, stock et validation
    # ==================================================
    STATUTS = [("en_attente", "En attente"), ("approuvee", "Approuvee"), ("refusee", "Refusee"), ("livree", "Livree"), ("annulee", "Annulee")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="commandes_produits")
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)
    cout_total_points = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=30, choices=STATUTS, default="en_attente")
    date_commande = models.DateTimeField(default=timezone.now)
    date_validation = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    motif_refus = models.TextField(blank=True)
    points_deduits = models.BooleanField(default=False)

    def clean(self):
        # TRAITEMENT STOCK/DATE — quantite positive, produit actif, validation apres commande.
        if self.quantite <= 0:
            raise ValidationError({"quantite": "La quantite doit etre superieure a 0."})
        if not self.produit.actif:
            raise ValidationError("Ce produit n'est pas actif.")
        if self.date_validation and self.date_validation < self.date_commande:
            raise ValidationError("La date de livraison/validation ne peut pas etre avant la commande.")


class Remuneration(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="remunerations")
    salaire_base = models.DecimalField(max_digits=12, decimal_places=2)
    prime = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    devise = models.CharField(max_length=8, default="MAD")
    date_effet = models.DateField(default=timezone.localdate)
    actif = models.BooleanField(default=True)
    cree_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.salaire_base is not None and self.salaire_base < 0:
            errors["salaire_base"] = "Le salaire de base ne peut pas etre negatif."
        if self.prime is not None and self.prime < 0:
            errors["prime"] = "La prime ne peut pas etre negative."
        if errors:
            raise ValidationError(errors)


class ReclamationRH(models.Model):
    # ==================================================
    # TABLE : RECLAMATION_RH
    # Reclamations employes, reponse RH et compensation en points
    # ==================================================
    TYPES = [("points", "Points"), ("pointage", "Pointage"), ("conge", "Conge"), ("materiel", "Materiel"), ("salaire", "Salaire"), ("document", "Document"), ("autre", "Autre")]
    STATUTS = [("ouverte", "Ouverte"), ("en_cours", "En cours"), ("acceptee", "Acceptee"), ("refusee", "Refusee"), ("cloturee", "Cloturee")]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="reclamations")
    sujet = models.CharField(max_length=255)
    description = models.TextField()
    type_reclamation = models.CharField(max_length=30, choices=TYPES)
    statut = models.CharField(max_length=30, choices=STATUTS, default="ouverte")
    date_creation = models.DateTimeField(default=timezone.now)
    date_traitement = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey("accounts.UtilisateurProfile", on_delete=models.SET_NULL, null=True, blank=True)
    reponse_rh = models.TextField(blank=True)
    points_accordes = models.PositiveIntegerField(default=0)
    action_points_appliquee = models.BooleanField(default=False)

    def clean(self):
        # TRAITEMENT RECLAMATION — sujet et description obligatoires.
        if not (self.sujet or "").strip() or not (self.description or "").strip():
            raise ValidationError("Le sujet et la description sont obligatoires.")
        if self.date_traitement and self.date_creation and self.date_traitement < self.date_creation:
            raise ValidationError({"date_traitement": "La date de traitement ne peut pas etre avant la creation."})
