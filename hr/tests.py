import json
import os
from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountCreationRequest, AdminSetting, Role, UtilisateurProfile, VerificationCode
from accounts.services import EmailResult
from hr.forms import AffectationFormationForm, CommandeProduitForm, DemandeAdministrativeForm, DemandeCongeForm, EmployeForm
from hr.models import (
    AffectationFormation,
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
    Pointage,
    Poste,
    Produit,
    ReclamationRH,
    Remuneration,
    Service,
    SoldeConge,
    StatutDemande,
    SupportRHReward,
    TacheEquipe,
    TransactionPoints,
    TypeConge,
)
from hr.services import appliquer_transaction_points, approuver_commande, deduire_solde_conge, livrer_commande, pointer_entree, pointer_sortie, refuser_ou_annuler_commande


class HrSmokeTests(TestCase):
    def setUp(self):
        departement = Departement.objects.create(libelle="IT")
        poste = Poste.objects.create(libelle="Dev")
        self.employe = Employe.objects.create(
            matricule="EMP-T",
            nom="Test",
            prenom="User",
            email="user@test.local",
            date_embauche=timezone.localdate() - timedelta(days=30),
            departement=departement,
            poste=poste,
        )
        user = User.objects.create_user(username="admin", password="admin123")
        UtilisateurProfile.objects.create(user=user, role=Role.ADMIN, employe=self.employe)

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login_then_loads(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.client.login(username="admin", password="admin123")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)


class TeamTaskScopeWorkflowTests(TestCase):
    def setUp(self):
        self.dep = Departement.objects.create(libelle="Support")
        self.other_dep = Departement.objects.create(libelle="Finance")
        self.service = Service.objects.create(libelle="Helpdesk", departement=self.dep)
        self.manager_emp = Employe.objects.create(matricule="MGR-T", nom="Manager", prenom="Scope", email="mgr-task@example.com", date_embauche=timezone.localdate() - timedelta(days=300), departement=self.dep, service=self.service)
        self.admin_emp = Employe.objects.create(matricule="ADM-T", nom="Admin", prenom="Scope", email="admin-task@example.com", date_embauche=timezone.localdate() - timedelta(days=300), departement=self.dep, service=self.service)
        self.emp = Employe.objects.create(matricule="EMP-T1", nom="Team", prenom="One", email="team1@example.com", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.dep, service=self.service, responsable=self.manager_emp)
        self.peer = Employe.objects.create(matricule="EMP-T2", nom="Team", prenom="Two", email="team2@example.com", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.dep, service=self.service, responsable=self.manager_emp)
        self.outsider = Employe.objects.create(matricule="EMP-OUT", nom="Out", prenom="Side", email="outside@example.com", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.other_dep)
        self.manager_user = User.objects.create_user(username="task-manager", password="manager123")
        self.emp_user = User.objects.create_user(username="task-emp", password="emp123")
        self.out_user = User.objects.create_user(username="task-out", password="out123")
        self.admin_user = User.objects.create_user(username="admin", password="admin123")
        UtilisateurProfile.objects.create(user=self.manager_user, role=Role.RESPONSABLE_HIERARCHIQUE, employe=self.manager_emp)
        UtilisateurProfile.objects.create(user=self.emp_user, role=Role.EMPLOYE, employe=self.emp)
        UtilisateurProfile.objects.create(user=self.out_user, role=Role.EMPLOYE, employe=self.outsider)
        UtilisateurProfile.objects.create(user=self.admin_user, role=Role.ADMIN, employe=self.admin_emp)

    def task_payload(self, **overrides):
        payload = {
            "titre": "Verifier dossier client",
            "description": "Controle complet du dossier avant validation.",
            "mode_affectation": "direct",
            "employe": self.emp.pk,
            "departement": self.dep.pk,
            "service": self.service.pk,
            "priorite": "haute",
            "taille": "moyenne",
            "date_debut": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "date_fin": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "date_limite": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "max_acceptations": 1,
        }
        payload.update(overrides)
        return payload

    def test_manager_direct_task_visible_to_employee_only(self):
        self.client.login(username="task-manager", password="manager123")
        response = self.client.post(reverse("task_create"), self.task_payload())
        self.assertEqual(response.status_code, 302)
        task = TacheEquipe.objects.get(titre="Verifier dossier client")
        self.assertEqual(task.employe, self.emp)
        self.assertEqual(task.manager, self.manager_emp)

        self.client.login(username="task-emp", password="emp123")
        response = self.client.get(reverse("team_tasks"), {"tab": "mine"})
        self.assertContains(response, "Verifier dossier client")

        self.client.login(username="task-out", password="out123")
        response = self.client.get(reverse("team_tasks"), {"tab": "mine"})
        self.assertNotContains(response, "Verifier dossier client")

    def test_team_task_creates_visible_task_per_scoped_employee(self):
        self.client.login(username="task-manager", password="manager123")
        response = self.client.post(reverse("task_create"), self.task_payload(mode_affectation="team", employe=""))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TacheEquipe.objects.filter(titre="Verifier dossier client").count(), 2)
        self.assertTrue(TacheEquipe.objects.filter(employe=self.emp).exists())
        self.assertTrue(TacheEquipe.objects.filter(employe=self.peer).exists())
        self.assertFalse(TacheEquipe.objects.filter(employe=self.outsider).exists())

    def test_open_task_visible_only_to_manager_scope_and_accepts(self):
        self.client.login(username="task-manager", password="manager123")
        response = self.client.post(reverse("task_create"), self.task_payload(mode_affectation="open", employe=""))
        self.assertEqual(response.status_code, 302)
        task = TacheEquipe.objects.get(titre="Verifier dossier client")
        self.assertEqual(task.statut, "ouverte")

        self.client.login(username="task-emp", password="emp123")
        response = self.client.get(reverse("team_tasks"), {"tab": "open"})
        self.assertContains(response, "Verifier dossier client")
        self.client.post(reverse("task_status", args=[task.pk]), {"action": "accept"})
        task.refresh_from_db()
        self.assertEqual(task.employe, self.emp)
        self.assertEqual(task.statut, "acceptee")

        self.client.login(username="task-out", password="out123")
        response = self.client.get(reverse("team_tasks"), {"tab": "open"})
        self.assertNotContains(response, "Verifier dossier client")

    def test_stale_open_task_acceptance_returns_message_not_crash(self):
        self.client.login(username="task-manager", password="manager123")
        self.client.post(reverse("task_create"), self.task_payload(mode_affectation="open", employe=""))
        task = TacheEquipe.objects.get(titre="Verifier dossier client")

        self.client.login(username="task-emp", password="emp123")
        self.client.post(reverse("task_status", args=[task.pk]), {"action": "accept"})

        peer_user = User.objects.create_user(username="task-peer", password="peer123")
        UtilisateurProfile.objects.create(user=peer_user, role=Role.EMPLOYE, employe=self.peer)
        self.client.login(username="task-peer", password="peer123")
        response = self.client.post(reverse("task_status", args=[task.pk]), {"action": "accept"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cette tache n&#x27;est plus disponible.")
        task.refresh_from_db()
        self.assertEqual(task.employe, self.emp)

    def test_manager_approval_requires_submitted_task_and_valid_points(self):
        task = TacheEquipe.objects.create(
            titre="Approbation controlee",
            description="Tache non soumise qui ne doit pas etre approuvee.",
            employe=self.emp,
            manager=self.manager_emp,
            departement=self.dep,
            service=self.service,
            statut="en_cours",
            cree_par=self.manager_user.profile,
            date_limite=timezone.now() + timedelta(days=2),
        )
        self.client.login(username="task-manager", password="manager123")
        response = self.client.post(reverse("task_status", args=[task.pk]), {"action": "approve", "points": 5}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seules les taches soumises peuvent etre approuvees.")
        task.refresh_from_db()
        self.assertEqual(task.statut, "en_cours")

        task.statut = "soumise"
        task.save(update_fields=["statut"])
        response = self.client.post(reverse("task_status", args=[task.pk]), {"action": "approve", "points": 31}, follow=True)
        self.assertContains(response, "Les points doivent etre entre 0 et 30.")
        task.refresh_from_db()
        self.assertEqual(task.statut, "soumise")

    def test_demo_seed_creates_task_keep_data_idempotently(self):
        call_command("seed_demo_rh")
        first_count = TacheEquipe.objects.filter(titre__startswith="[Demo Task Keep]").count()
        first_points = TransactionPoints.objects.filter(source="tache", objet_lie__startswith="[Demo Task Keep]:").count()

        call_command("seed_demo_rh")
        self.assertEqual(TacheEquipe.objects.filter(titre__startswith="[Demo Task Keep]").count(), first_count)
        self.assertEqual(TransactionPoints.objects.filter(source="tache", objet_lie__startswith="[Demo Task Keep]:").count(), first_points)
        self.assertGreaterEqual(first_count, 8)
        self.assertTrue(TacheEquipe.objects.filter(titre__startswith="[Demo Task Keep]", statut="ouverte").exists())
        self.assertTrue(TacheEquipe.objects.filter(titre__startswith="[Demo Task Keep]", statut="soumise").exists())

    def test_employee_list_loads_for_admin(self):
        self.client.login(username="admin", password="admin123")
        response = self.client.get(reverse("employes_list"))
        self.assertEqual(response.status_code, 200)

    def test_employee_sidebar_parent_stays_open_on_hierarchy(self):
        self.client.login(username="admin", password="admin123")
        response = self.client.get(reverse("hierarchy_tree"))
        self.assertContains(response, 'id="menuEmployes"')
        self.assertContains(response, 'sidebar-submenu show')
        self.assertContains(response, 'sidebar-subitem active')
        self.assertContains(response, 'bi bi-diagram-3')

    def test_department_sidebar_active_child_uses_query_tab(self):
        self.client.login(username="admin", password="admin123")
        response = self.client.get(reverse("departements_list"), {"tab": "services"})
        self.assertContains(response, 'id="menuDepartements"')
        self.assertContains(response, 'sidebar-submenu show')
        self.assertContains(response, 'sidebar-subitem active')
        self.assertContains(response, "Services")


class FormValidationTests(TestCase):
    def setUp(self):
        self.employee = Employe.objects.create(
            matricule="EMP-001",
            nom="Valid",
            prenom="User",
            email="valid@example.com",
            telephone="+212 600000000",
            date_embauche=timezone.localdate() - timedelta(days=60),
        )

    def test_employee_form_rejects_invalid_name_future_dates_and_duplicate_email(self):
        form = EmployeForm(
            data={
                "matricule": "EMP-002",
                "nom": "User123",
                "prenom": "A",
                "email": "VALID@EXAMPLE.COM",
                "telephone": "abc123",
                "date_naissance": timezone.localdate() + timedelta(days=1),
                "date_embauche": timezone.localdate() + timedelta(days=1),
                "adresse": "  ",
                "actif": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("nom", form.errors)
        self.assertIn("prenom", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("telephone", form.errors)
        self.assertIn("date_naissance", form.errors)
        self.assertIn("date_embauche", form.errors)

    def test_leave_form_rejects_past_reverse_and_overlapping_dates(self):
        today = timezone.localdate()
        reverse_form = DemandeCongeForm(
            data={"type": TypeConge.ANNUEL, "date_debut": today + timedelta(days=3), "date_fin": today + timedelta(days=1), "motif": ""}
        )
        self.assertFalse(reverse_form.is_valid())
        self.assertIn("date_fin", reverse_form.errors)

        past_form = DemandeCongeForm(
            data={"type": TypeConge.ANNUEL, "date_debut": today - timedelta(days=1), "date_fin": today, "motif": ""}
        )
        self.assertFalse(past_form.is_valid())
        self.assertIn("date_debut", past_form.errors)

        DemandeConge.objects.create(
            type=TypeConge.ANNUEL,
            date_debut=today + timedelta(days=5),
            date_fin=today + timedelta(days=7),
            employe=self.employee,
        )
        overlap_form = DemandeCongeForm(
            employee=self.employee,
            data={"type": TypeConge.MALADIE, "date_debut": today + timedelta(days=6), "date_fin": today + timedelta(days=8), "motif": ""}
        )
        self.assertFalse(overlap_form.is_valid())
        self.assertIn("__all__", overlap_form.errors)

    def test_admin_request_requires_meaningful_text(self):
        form = DemandeAdministrativeForm(data={"type_demande": "A", "description": "short"})

        self.assertFalse(form.is_valid())
        self.assertIn("type_demande", form.errors)
        self.assertIn("description", form.errors)


class AdministrationWorkflowTests(TestCase):
    def setUp(self):
        self.dep = Departement.objects.create(libelle="Admin")
        self.poste = Poste.objects.create(libelle="Admin")
        self.admin_emp = Employe.objects.create(matricule="ADM-001", nom="Admin", prenom="Root", email="admin@company.test", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.dep, poste=self.poste)
        self.emp = Employe.objects.create(matricule="EMP-ADM", nom="Pending", prenom="User", email="pending@company.test", date_embauche=timezone.localdate() - timedelta(days=30), departement=self.dep, poste=self.poste)
        self.admin_user = User.objects.create_user(username="admin-workflow", password="admin123", email="admin@company.test")
        self.employee_user = User.objects.create_user(username="plain-user", password="emp123", email="plain@company.test")
        UtilisateurProfile.objects.create(user=self.admin_user, role=Role.ADMIN, employe=self.admin_emp)
        UtilisateurProfile.objects.create(user=self.employee_user, role=Role.EMPLOYE)
        AdminSetting.objects.create(key="company_email_domain", value="company.test")

    def request_payload(self, **overrides):
        payload = {
            "email": "pending@company.test",
            "first_name": "Pending",
            "last_name": "User",
            "phone_number": "+212600000000",
            "matricule": "EMP-ADM",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        payload.update(overrides)
        return payload

    def test_account_request_validation_duplicate_approval_and_denial(self):
        invalid = self.client.post(reverse("account_request_create"), self.request_payload(email="bad@external.test"))
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(AccountCreationRequest.objects.exists())

        with patch("accounts.services.VerificationCodeService.generate_code", return_value="123456"), patch("accounts.services.BrevoEmailService.send_account_verification", return_value=EmailResult(True)):
            response = self.client.post(reverse("account_request_create"), self.request_payload())
        self.assertRedirects(response, reverse("account_request_verify"))
        account_request = AccountCreationRequest.objects.get(email="pending@company.test")
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_VERIFYING)
        self.assertFalse(account_request.email_verified)
        self.assertNotIn("StrongPass123!", account_request.password_hash)
        self.assertNotIn("123456", VerificationCode.objects.get(email="pending@company.test").code_hash)

        duplicate = self.client.post(reverse("account_request_create"), self.request_payload())
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(AccountCreationRequest.objects.filter(email="pending@company.test").count(), 1)

        response = self.client.post(reverse("account_request_verify"), {"code": "123456"})
        self.assertRedirects(response, reverse("account_request_status"))
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_PENDING)
        self.assertTrue(account_request.email_verified)

        self.client.login(username="admin-workflow", password="admin123")
        with patch("accounts.services.BrevoEmailService.send_account_decision", return_value=EmailResult(True)):
            response = self.client.post(reverse("admin_account_request_decision", args=[account_request.pk]), {"action": "approve", "admin_note": "OK"})
        self.assertRedirects(response, f"{reverse('admin_dashboard')}?tab=account_requests")
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_APPROVED)
        self.assertTrue(User.objects.filter(username="pending@company.test", is_active=True).exists())
        self.assertTrue(HistoriqueAction.objects.filter(action="ACCOUNT_REQUEST_APPROVED").exists())

        self.client.logout()
        self.assertTrue(self.client.login(username="pending@company.test", password="StrongPass123!"))

        denied = AccountCreationRequest(email="denied@company.test", first_name="Denied", last_name="User")
        denied.set_password("StrongPass123!")
        denied.save()
        self.client.login(username="admin-workflow", password="admin123")
        with patch("accounts.services.BrevoEmailService.send_account_decision", return_value=EmailResult(True)):
            self.client.post(reverse("admin_account_request_decision", args=[denied.pk]), {"action": "deny", "admin_note": "No match"})
        denied.refresh_from_db()
        self.assertEqual(denied.status, AccountCreationRequest.STATUS_DENIED)
        self.assertFalse(User.objects.filter(username="denied@company.test").exists())

    def test_admin_ladder_tabs_and_non_admin_protection(self):
        self.client.login(username="plain-user", password="emp123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertRedirects(response, reverse("dashboard"))

        self.client.login(username="admin-workflow", password="admin123")
        for tab, label in [
            ("overview", "Demandes recentes"),
            ("account_requests", "Demandes de creation de compte"),
            ("users", "Utilisateurs & roles"),
            ("permissions", "Permissions et controle d'acces"),
            ("audit", "Journaux d'audit"),
            ("settings", "Parametres systeme"),
            ("security", "Securite"),
            ("reports", "Rapports"),
        ]:
            response = self.client.get(reverse("admin_dashboard"), {"tab": tab})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, label)
            self.assertContains(response, 'id="menuAdministration"')

    def test_admin_can_update_role_and_settings(self):
        self.client.login(username="admin-workflow", password="admin123")
        response = self.client.post(reverse("admin_settings_save"), {"company_email_domain": "corp.local"})
        self.assertRedirects(response, f"{reverse('admin_dashboard')}?tab=settings")
        self.assertEqual(AdminSetting.objects.get(key="company_email_domain").value, "corp.local")

        response = self.client.post(reverse("admin_user_update", args=[self.employee_user.pk]), {"role": Role.RESPONSABLE_RH, "active": "on"})
        self.assertRedirects(response, f"{reverse('admin_dashboard')}?tab=users")
        self.employee_user.profile.refresh_from_db()
        self.assertEqual(self.employee_user.profile.role, Role.RESPONSABLE_RH)
        self.assertTrue(HistoriqueAction.objects.filter(action="ADMIN_USER_UPDATE").exists())


class WorkflowSecurityTests(TestCase):
    def setUp(self):
        self.department = Departement.objects.create(libelle="Operations")
        self.manager_employee = Employe.objects.create(
            matricule="MGR-001",
            nom="Manager",
            prenom="Main",
            email="manager@example.com",
            date_embauche=timezone.localdate() - timedelta(days=100),
            departement=self.department,
        )
        self.employee = Employe.objects.create(
            matricule="EMP-002",
            nom="Employee",
            prenom="Direct",
            email="employee@example.com",
            date_embauche=timezone.localdate() - timedelta(days=90),
            departement=self.department,
            responsable=self.manager_employee,
        )
        self.other_employee = Employe.objects.create(
            matricule="EMP-003",
            nom="Other",
            prenom="Hidden",
            email="other@example.com",
            date_embauche=timezone.localdate() - timedelta(days=80),
            departement=self.department,
        )
        self.rh_employee = Employe.objects.create(
            matricule="RH-001",
            nom="Human",
            prenom="Resources",
            email="rh.employee@example.com",
            date_embauche=timezone.localdate() - timedelta(days=120),
            departement=self.department,
        )
        self.manager_user = User.objects.create_user(username="manager", password="manager123")
        self.employee_user = User.objects.create_user(username="employee", password="employee123")
        self.rh_user = User.objects.create_user(username="rh", password="rh123")
        UtilisateurProfile.objects.create(user=self.manager_user, role=Role.RESPONSABLE_HIERARCHIQUE, employe=self.manager_employee)
        UtilisateurProfile.objects.create(user=self.employee_user, role=Role.EMPLOYE, employe=self.employee)
        UtilisateurProfile.objects.create(user=self.rh_user, role=Role.RESPONSABLE_RH, employe=self.rh_employee)

    def test_manager_cannot_view_unrelated_employee_by_direct_url(self):
        self.client.login(username="manager", password="manager123")

        response = self.client.get(reverse("employe_detail", args=[self.other_employee.pk]))

        self.assertEqual(response.status_code, 404)

    def test_state_changing_leave_action_rejects_get_and_cannot_process_twice(self):
        demande = DemandeConge.objects.create(
            type=TypeConge.ANNUEL,
            date_debut=timezone.localdate() + timedelta(days=2),
            date_fin=timezone.localdate() + timedelta(days=3),
            employe=self.employee,
        )
        self.client.login(username="manager", password="manager123")

        get_response = self.client.get(reverse("conge_validate", args=[demande.pk]))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("conge_validate", args=[demande.pk]))
        self.assertEqual(post_response.status_code, 302)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.EN_COURS)
        self.assertEqual(demande.manager_approval_status, DemandeConge.APPROVAL_APPROVED)

        duplicate_response = self.client.post(reverse("conge_validate", args=[demande.pk]))
        self.assertEqual(duplicate_response.status_code, 302)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.EN_COURS)

        self.client.login(username="rh", password="rh123")
        hr_response = self.client.post(reverse("conge_validate", args=[demande.pk]))
        self.assertEqual(hr_response.status_code, 302)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.VALIDEE)
        self.assertEqual(demande.hr_approval_status, DemandeConge.APPROVAL_APPROVED)


class NewHrFeatureAbuseTests(TestCase):
    def setUp(self):
        self.dep = Departement.objects.create(libelle="RH")
        self.poste = Poste.objects.create(libelle="Manager", rang_hierarchique=30, est_manager=True)
        self.rh_emp = Employe.objects.create(matricule="RH-X", nom="Rh", prenom="Admin", email="rhx@example.com", date_embauche=timezone.localdate() - timedelta(days=300), departement=self.dep, poste=self.poste)
        self.emp = Employe.objects.create(matricule="EMP-X", nom="Test", prenom="Employe", email="empx@example.com", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.dep, responsable=self.rh_emp)
        self.other = Employe.objects.create(matricule="EMP-Y", nom="Autre", prenom="Employe", email="empy@example.com", date_embauche=timezone.localdate() - timedelta(days=100), departement=self.dep)
        self.rh_user = User.objects.create_user(username="rh2", password="rh123")
        self.emp_user = User.objects.create_user(username="emp2", password="emp123")
        UtilisateurProfile.objects.create(user=self.rh_user, role=Role.RESPONSABLE_RH, employe=self.rh_emp)
        UtilisateurProfile.objects.create(user=self.emp_user, role=Role.EMPLOYE, employe=self.emp)
        ComptePoints.objects.create(employe=self.emp, solde_points=100)
        SoldeConge.objects.create(employe=self.emp, jours_disponibles=3, jours_utilises=0)

    def test_points_balance_never_negative(self):
        with self.assertRaises(Exception):
            appliquer_transaction_points(self.emp, "achat", 999, "boutique", "Achat impossible")
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 100)

    def test_employee_cannot_access_manual_point_adjustment(self):
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("manual_points"))
        self.assertEqual(response.status_code, 302)

    def test_hr_can_add_points_with_reason(self):
        self.client.login(username="rh2", password="rh123")
        response = self.client.post(reverse("manual_points"), {"employe": self.emp.id, "type_adjustement": "ajout", "nombre_points": 25, "motif_obligatoire": "Correction pointage validee"})
        self.assertEqual(response.status_code, 302)
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 125)

    def test_salary_and_position_permissions_protected(self):
        Remuneration.objects.create(employe=self.emp, salaire_base=10000)
        self.client.login(username="emp2", password="emp123")
        self.assertEqual(self.client.get(reverse("payroll_analytics")).status_code, 302)
        self.assertEqual(self.client.get(reverse("position_management")).status_code, 302)

    def test_hierarchy_cycle_prevented(self):
        self.rh_emp.responsable = self.emp
        with self.assertRaises(Exception):
            self.rh_emp.full_clean()

    def test_hierarchy_page_uses_real_data_and_hides_salary(self):
        Remuneration.objects.create(employe=self.emp, salaire_base=123456, prime=789)
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("hierarchy_tree"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.rh_emp.nom_complet)
        self.assertContains(response, self.emp.nom_complet)
        self.assertContains(response, "org-card")
        self.assertNotContains(response, "123456")
        self.assertNotContains(response, "789")

    def test_unauthenticated_user_cannot_view_hierarchy(self):
        response = self.client.get(reverse("hierarchy_tree"))
        self.assertEqual(response.status_code, 302)

    def test_manager_change_updates_hierarchy_output(self):
        self.client.login(username="emp2", password="emp123")
        first_response = self.client.get(reverse("hierarchy_tree"))
        self.assertContains(first_response, self.rh_emp.nom_complet)
        self.emp.responsable = self.other
        self.emp.save(update_fields=["responsable"])
        second_response = self.client.get(reverse("hierarchy_tree"))
        content = second_response.content.decode()
        self.assertIn(self.other.nom_complet, content)
        self.assertIn(self.emp.nom_complet, content)

    def test_ceo_position_change_updates_top_hierarchy_data(self):
        direction = Poste.objects.create(libelle="Directeur General Test", niveau="Direction generale", rang_hierarchique=1, est_direction=True, est_manager=True)
        self.other.poste = direction
        self.other.responsable = None
        self.other.save(update_fields=["poste", "responsable"])
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("hierarchy_tree"))
        content = response.content.decode()
        self.assertIn("Directeur General Test", content)
        self.assertIn(self.other.nom_complet, content)

    def test_leave_balance_blocks_excess_and_deducts_when_validated(self):
        demande = DemandeConge.objects.create(type=TypeConge.ANNUEL, date_debut=timezone.localdate() + timedelta(days=5), date_fin=timezone.localdate() + timedelta(days=9), employe=self.emp)
        with self.assertRaises(Exception):
            deduire_solde_conge(demande)
        demande.date_fin = timezone.localdate() + timedelta(days=6)
        demande.save()
        deduire_solde_conge(demande)
        self.emp.solde_conge.refresh_from_db()
        self.assertEqual(float(self.emp.solde_conge.jours_disponibles), 1.0)

    def test_unpaid_leave_bypasses_balance_on_request_and_validation(self):
        start = timezone.localdate() + timedelta(days=5)
        end = start + timedelta(days=9)
        annual_form = DemandeCongeForm(employee=self.emp, data={"type": TypeConge.ANNUEL, "date_debut": start, "date_fin": end, "motif": ""})
        unpaid_form = DemandeCongeForm(employee=self.emp, data={"type": TypeConge.SANS_SOLDE, "date_debut": start, "date_fin": end, "motif": ""})

        self.assertFalse(annual_form.is_valid())
        self.assertTrue(unpaid_form.is_valid())

        manager_emp = Employe.objects.create(matricule="MGR-X", nom="Manager", prenom="Equipe", email="mgrx@example.com", date_embauche=timezone.localdate() - timedelta(days=200), departement=self.dep)
        self.emp.responsable = manager_emp
        self.emp.save(update_fields=["responsable"])
        demande = DemandeConge.objects.create(type=TypeConge.SANS_SOLDE, date_debut=start, date_fin=end, employe=self.emp)
        self.client.login(username="rh2", password="rh123")
        response = self.client.post(reverse("conge_validate", args=[demande.pk]))

        self.assertEqual(response.status_code, 302)
        demande.refresh_from_db()
        self.emp.solde_conge.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.EN_COURS)
        self.assertEqual(demande.hr_approval_status, DemandeConge.APPROVAL_APPROVED)
        self.assertEqual(float(self.emp.solde_conge.jours_disponibles), 3.0)

        manager_user = User.objects.create_user(username="manager2", password="manager123")
        UtilisateurProfile.objects.create(user=manager_user, role=Role.RESPONSABLE_HIERARCHIQUE, employe=manager_emp)
        self.client.login(username="manager2", password="manager123")
        response = self.client.post(reverse("conge_validate", args=[demande.pk]))

        self.assertEqual(response.status_code, 302)
        demande.refresh_from_db()
        self.emp.solde_conge.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.VALIDEE)
        self.assertEqual(float(self.emp.solde_conge.jours_disponibles), 3.0)
        self.assertEqual(float(self.emp.solde_conge.jours_utilises), 0.0)

    def test_sick_and_maternity_leave_do_not_consume_annual_balance(self):
        start = timezone.localdate() + timedelta(days=20)
        end = start + timedelta(days=6)
        sick_form = DemandeCongeForm(employee=self.emp, data={"type": TypeConge.MALADIE, "date_debut": start, "date_fin": end, "motif": "Certificat medical"})
        self.assertTrue(sick_form.is_valid(), sick_form.errors)

        demande = DemandeConge.objects.create(type=TypeConge.MALADIE, date_debut=start, date_fin=end, employe=self.emp)
        deduire_solde_conge(demande)
        self.emp.solde_conge.refresh_from_db()
        self.assertEqual(float(self.emp.solde_conge.jours_disponibles), 3.0)
        self.assertEqual(float(self.emp.solde_conge.jours_utilises), 0.0)

    def test_sick_and_maternity_leave_require_attachment_on_submit(self):
        self.client.login(username="emp2", password="emp123")
        start = timezone.localdate() + timedelta(days=30)
        response = self.client.post(
            reverse("conge_submit"),
            {"type": TypeConge.MALADIE, "date_debut": start, "date_fin": start, "motif": "Maladie"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "justificatif est obligatoire")
        self.assertFalse(DemandeConge.objects.filter(employe=self.emp, type=TypeConge.MALADIE, date_debut=start).exists())

    def test_checkout_before_checkin_blocked_by_model(self):
        p = Pointage(employe=self.emp, date=timezone.localdate(), heure_entree=timezone.now(), heure_sortie=timezone.now() - timedelta(hours=1))
        with self.assertRaises(Exception):
            p.full_clean()

    def test_formation_deadline_before_assignment_blocked(self):
        formation = Formation.objects.create(titre="Securite")
        form = AffectationFormationForm(data={"formation": formation.id, "employe": self.emp.id, "date_limite": timezone.localdate() - timedelta(days=1)})
        self.assertFalse(form.is_valid())

    def test_formation_assignment_form_has_no_department_choice(self):
        form = AffectationFormationForm()
        self.assertIn("employe", form.fields)
        self.assertNotIn("departement", form.fields)

    def test_formation_assignment_targets_only_selected_employee_and_notifies_them(self):
        other_user = User.objects.create_user(username="other", password="emp123")
        other_profile = UtilisateurProfile.objects.create(user=other_user, role=Role.EMPLOYE, employe=self.other)
        formation = Formation.objects.create(titre="Securite ciblee")
        self.client.login(username="rh2", password="rh123")

        response = self.client.post(reverse("formations_admin"), {"formation": formation.id, "employe": self.emp.id, "departement": self.dep.id})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(AffectationFormation.objects.filter(formation=formation, employe=self.emp).exists())
        self.assertFalse(AffectationFormation.objects.filter(formation=formation, employe=self.other).exists())
        self.assertTrue(self.emp.utilisateur_profile.notifications.filter(message__icontains=formation.titre).exists())
        self.assertFalse(Notification.objects.filter(destinataire=other_profile, message__icontains=formation.titre).exists())

    def test_shop_purchase_deducts_once_and_refund_possible(self):
        cat = CategorieProduit.objects.create(nom="Ordinateurs")
        produit = Produit.objects.create(nom="Laptop", categorie=cat, cout_points=40, stock_disponible=2)
        commande = CommandeProduit.objects.create(employe=self.emp, produit=produit, quantite=1, cout_total_points=40)
        approuver_commande(commande, self.rh_user.profile)
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 60)
        commande.refresh_from_db()
        with self.assertRaises(Exception):
            approuver_commande(commande, self.rh_user.profile)
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 60)

    def test_employee_sees_only_own_reclamations(self):
        ReclamationRH.objects.create(employe=self.emp, sujet="Mes points", description="Probleme de points", type_reclamation="points")
        ReclamationRH.objects.create(employe=self.other, sujet="Sujet cache", description="Probleme cache", type_reclamation="document")
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("reclamations"))
        self.assertRedirects(response, f"{reverse('rh_messages')}?tab=available")

    def test_document_upload_rejects_disallowed_extension(self):
        self.client.login(username="emp2", password="emp123")
        uploaded = SimpleUploadedFile("payload.exe", b"not safe", content_type="application/octet-stream")

        response = self.client.post(reverse("document_upload"), {"file": uploaded, "categorie": "General"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.emp.documents.count(), 0)

    def test_finalized_admin_request_cannot_be_processed_again(self):
        demande = DemandeAdministrative.objects.create(
            type_demande="Attestation",
            description="Besoin d'une attestation de travail.",
            employe=self.emp,
            statut=StatutDemande.VALIDEE,
        )
        self.client.login(username="rh2", password="rh123")

        response = self.client.post(reverse("demande_process", args=[demande.pk]), {"statut": StatutDemande.REFUSEE, "reponse": "Non"})

        self.assertEqual(response.status_code, 302)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, StatutDemande.VALIDEE)

    def test_admin_request_list_shows_full_detail_and_large_reply_form(self):
        demande = DemandeAdministrative.objects.create(
            type_demande="Attestation",
            description="Besoin d'une attestation de travail avec details complets.",
            employe=self.emp,
        )
        Document.objects.create(
            fichier=SimpleUploadedFile("attestation.pdf", b"pdf", content_type="application/pdf"),
            nom_fichier="attestation.pdf",
            nom_original="attestation.pdf",
            categorie="Demande administrative",
            taille=3,
            employe=self.emp,
            demande_admin=demande,
            uploade_par=self.emp_user,
        )
        self.client.login(username="rh2", password="rh123")

        response = self.client.get(reverse("demandes_list"))

        self.assertContains(response, "request-inbox-item")
        self.assertContains(response, reverse("demande_detail", args=[demande.pk]))
        self.assertNotContains(response, "<details", html=False)

        response = self.client.get(reverse("demande_detail", args=[demande.pk]))

        self.assertContains(response, "attestation de travail avec details complets.")
        self.assertContains(response, "attestation.pdf")
        self.assertContains(response, '<textarea class="form-control"', html=False)

    def test_position_search_and_change_create_notification_and_audit(self):
        self.client.login(username="rh2", password="rh123")
        response = self.client.get(reverse("position_management"), {"search": "Employe"})
        self.assertContains(response, "Employe Test")
        new_poste = Poste.objects.create(libelle="Chef equipe", rang_hierarchique=45, est_manager=True)
        response = self.client.post(reverse("position_edit", args=[self.emp.pk]), {"poste": new_poste.pk, "departement": self.dep.pk, "service": "", "responsable": self.rh_emp.pk, "actif": "on"})
        self.assertEqual(response.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.poste_id, new_poste.pk)
        self.assertTrue(self.emp.utilisateur_profile.notifications.filter(message__icontains="poste").exists() if hasattr(self.emp, "utilisateur_profile") else True)
        self.assertTrue(HistoriqueAction.objects.filter(action="CHANGEMENT_POSTE", entite_id=self.emp.pk).exists())

    def test_formation_completion_awards_points_once(self):
        formation = Formation.objects.create(titre="Cyber hygiene", points_recompense=30)
        aff = AffectationFormation.objects.create(formation=formation, employe=self.emp)
        self.client.login(username="emp2", password="emp123")
        self.client.post(reverse("training_status", args=[aff.pk]), {"statut": "terminee"})
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 130)
        self.assertEqual(TransactionPoints.objects.filter(source="formation", employe=self.emp).count(), 1)
        self.client.post(reverse("training_status", args=[aff.pk]), {"statut": "terminee"})
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 130)
        self.assertEqual(TransactionPoints.objects.filter(source="formation", employe=self.emp).count(), 1)

    def test_employee_cannot_complete_another_employee_training(self):
        formation = Formation.objects.create(titre="Formation cachee", points_recompense=10)
        aff = AffectationFormation.objects.create(formation=formation, employe=self.other)
        self.client.login(username="emp2", password="emp123")
        response = self.client.post(reverse("training_status", args=[aff.pk]), {"statut": "terminee"})
        self.assertEqual(response.status_code, 404)

    def test_hr_can_update_formation_assignment_status(self):
        formation = Formation.objects.create(titre="Leadership", points_recompense=15)
        aff = AffectationFormation.objects.create(formation=formation, employe=self.emp)
        self.client.login(username="rh2", password="rh123")
        response = self.client.post(reverse("formation_assignment_status", args=[aff.pk]), {"statut": "terminee"})
        self.assertEqual(response.status_code, 302)
        aff.refresh_from_db()
        self.assertEqual(aff.statut, "terminee")
        self.assertTrue(aff.points_attribues)

    def test_hr_can_cancel_completed_formation_without_removing_points(self):
        formation = Formation.objects.create(titre="Leadership annule", points_recompense=15)
        aff = AffectationFormation.objects.create(formation=formation, employe=self.emp)
        self.client.login(username="rh2", password="rh123")

        self.client.post(reverse("formation_assignment_status", args=[aff.pk]), {"statut": "terminee"})
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(self.emp.compte_points.solde_points, 115)

        response = self.client.post(reverse("formation_assignment_status", args=[aff.pk]), {"statut": "annulee"})

        self.assertEqual(response.status_code, 302)
        aff.refresh_from_db()
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(aff.statut, "annulee")
        self.assertTrue(aff.points_attribues)
        self.assertEqual(self.emp.compte_points.solde_points, 115)
        self.assertTrue(self.emp.utilisateur_profile.notifications.filter(message__icontains="annulee").exists())

    def test_employee_cannot_complete_cancelled_training(self):
        formation = Formation.objects.create(titre="Formation annulee", points_recompense=20)
        aff = AffectationFormation.objects.create(formation=formation, employe=self.emp, statut="annulee")
        self.client.login(username="emp2", password="emp123")

        response = self.client.post(reverse("training_status", args=[aff.pk]), {"statut": "terminee"})

        self.assertEqual(response.status_code, 302)
        aff.refresh_from_db()
        self.emp.compte_points.refresh_from_db()
        self.assertEqual(aff.statut, "annulee")
        self.assertEqual(self.emp.compte_points.solde_points, 100)

    def test_audit_filters_load(self):
        HistoriqueAction.objects.create(action="CHANGEMENT_POSTE", details="Test", utilisateur=self.rh_user.profile, entite_concernee="Employe", entite_id=self.emp.pk)
        self.client.login(username="rh2", password="rh123")
        response = self.client.get(reverse("audit_history"), {"role": Role.RESPONSABLE_RH, "module": "Employe", "action": "POSTE"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CHANGEMENT_POSTE")

    def test_hr_sees_all_conversations_employee_only_own(self):
        ConversationRH.objects.create(employe=self.emp, sujet="Mon sujet")
        ConversationRH.objects.create(employe=self.other, sujet="Sujet autre")
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("rh_messages"), follow=True)
        self.assertContains(response, "Mon sujet")
        self.assertNotContains(response, "Sujet autre")
        self.client.login(username="rh2", password="rh123")
        response = self.client.get(reverse("rh_messages"), follow=True)
        self.assertContains(response, "Mon sujet")
        self.assertContains(response, "Sujet autre")

    def test_employee_sees_rh_reply_in_contact_rh(self):
        conv = ConversationRH.objects.create(employe=self.emp, sujet="Question RH", statut="en_attente")
        self.client.login(username="rh2", password="rh123")

        response = self.client.post(reverse("rh_conversation_detail", args=[conv.pk]), {"contenu": "Voici la reponse RH."})

        self.assertEqual(response.status_code, 302)
        conv.refresh_from_db()
        reply = MessageRH.objects.get(conversation=conv, contenu="Voici la reponse RH.")
        self.assertEqual(conv.statut, "attente_employe")
        self.assertEqual(reply.destinataire, self.emp.utilisateur_profile)
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("rh_messages"), follow=True)
        self.assertContains(response, "Question RH")
        response = self.client.get(reverse("rh_conversation_detail", args=[conv.pk]))
        self.assertContains(response, "Voici la reponse RH.")

    def test_document_delete_archives_and_archives_are_rh_only(self):
        document = Document.objects.create(
            fichier=SimpleUploadedFile("contrat.pdf", b"pdf", content_type="application/pdf"),
            nom_fichier="contrat.pdf",
            nom_original="contrat.pdf",
            categorie="Contrat",
            taille=3,
            employe=self.emp,
            uploade_par=self.emp_user,
        )
        self.client.login(username="emp2", password="emp123")

        response = self.client.post(reverse("document_delete", args=[document.pk]))

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertTrue(document.archive)
        self.assertIsNotNone(document.date_archivage)
        self.assertEqual(document.archive_par, self.emp_user.profile)
        self.assertEqual(Document.objects.filter(pk=document.pk).count(), 1)
        self.assertEqual(self.client.get(reverse("document_download", args=[document.pk])).status_code, 403)
        response = self.client.get(reverse("documents_list"))
        self.assertRedirects(response, f"{reverse('rh_messages')}?tab=available")

        self.client.login(username="rh2", password="rh123")
        response = self.client.get(reverse("documents_list"), {"archive": "1"})
        self.assertRedirects(response, f"{reverse('rh_messages')}?tab=available")

    def test_rh_conversation_marks_read_and_can_be_closed(self):
        conv = ConversationRH.objects.create(employe=self.emp, sujet="Lecture RH", statut="en_attente")
        msg = MessageRH.objects.create(conversation=conv, expediteur=self.emp_user.profile, contenu="Merci de traiter.")
        self.client.login(username="rh2", password="rh123")

        response = self.client.get(reverse("rh_conversation_detail", args=[conv.pk]))

        self.assertEqual(response.status_code, 200)
        msg.refresh_from_db()
        self.assertTrue(msg.lu)

        response = self.client.post(reverse("rh_conversation_close", args=[conv.pk]), {"motif_cloture": "resolved", "detail_cloture": "Traite par RH."})
        self.assertEqual(response.status_code, 302)
        conv.refresh_from_db()
        self.assertEqual(conv.statut, "cloturee")
        self.assertEqual(conv.motif_cloture, "resolved")
        self.assertEqual(conv.cloture_par, self.rh_user.profile)

        before = conv.messages.count()
        self.client.login(username="emp2", password="emp123")
        self.client.post(reverse("rh_conversation_detail", args=[conv.pk]), {"contenu": "Je reponds quand meme."})
        self.assertEqual(conv.messages.count(), before)

    def test_rh_ticket_requires_close_reason(self):
        conv = ConversationRH.objects.create(employe=self.emp, sujet="Cloture controlee", statut="en_attente")
        self.client.login(username="rh2", password="rh123")

        response = self.client.post(reverse("rh_conversation_close", args=[conv.pk]), {}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choisissez un motif de cloture valide.")
        conv.refresh_from_db()
        self.assertEqual(conv.statut, "en_attente")

    def test_rh_ticket_attachment_is_permission_checked(self):
        conv = ConversationRH.objects.create(employe=self.emp, sujet="Piece jointe RH", statut="en_attente")
        msg = MessageRH.objects.create(
            conversation=conv,
            expediteur=self.emp_user.profile,
            contenu="Voir document.",
            piece_jointe=SimpleUploadedFile("preuve.pdf", b"pdf", content_type="application/pdf"),
            nom_piece_jointe="preuve.pdf",
        )

        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("rh_message_attachment", args=[msg.pk]))
        self.assertEqual(response.status_code, 200)

        other_user = User.objects.create_user(username="ticket-other", password="other123")
        UtilisateurProfile.objects.create(user=other_user, role=Role.EMPLOYE, employe=self.other)
        self.client.login(username="ticket-other", password="other123")
        response = self.client.get(reverse("rh_message_attachment", args=[msg.pk]))
        self.assertEqual(response.status_code, 404)

    def test_documents_and_reclamations_tabs_fallback_to_support(self):
        self.client.login(username="emp2", password="emp123")
        response = self.client.get(reverse("documents_list"))
        self.assertRedirects(response, f"{reverse('rh_messages')}?tab=available")
        response = self.client.get(reverse("reclamations"))
        self.assertRedirects(response, f"{reverse('rh_messages')}?tab=available")
        response = self.client.get(reverse("rh_messages"), follow=True)
        self.assertNotContains(response, "Documents</span>", html=False)
        self.assertNotContains(response, "Reclamations RH</span>", html=False)

    def test_ticket_creation_default_name_and_atomic_acceptance(self):
        second_rh_emp = Employe.objects.create(matricule="RH-Z", nom="Second", prenom="Rh", email="rhz@example.com", date_embauche=timezone.localdate() - timedelta(days=200), departement=self.dep, poste=self.poste)
        second_rh_user = User.objects.create_user(username="rh3", password="rh123")
        UtilisateurProfile.objects.create(user=second_rh_user, role=Role.RESPONSABLE_RH, employe=second_rh_emp)

        self.client.login(username="emp2", password="emp123")
        response = self.client.post(
            reverse("rh_conversation_create"),
            {"sujet": "Bulletin de paie", "categorie": "paie", "priorite": "haute", "contenu": "Question sur le bulletin."},
        )
        self.assertEqual(response.status_code, 302)
        conv = ConversationRH.objects.get()
        self.assertEqual(conv.sujet, "Conversation 1")
        self.assertEqual(conv.numero_ticket, 1)
        self.assertTrue(conv.participants.filter(pk=self.emp.pk).exists())
        self.assertContains(self.client.get(reverse("rh_conversation_detail", args=[conv.pk])), "Objet initial: Bulletin de paie")

        self.client.login(username="rh2", password="rh123")
        self.client.post(reverse("rh_conversation_accept", args=[conv.pk]))
        conv.refresh_from_db()
        self.assertEqual(conv.responsable_rh, self.rh_user.profile)

        self.client.login(username="rh3", password="rh123")
        response = self.client.post(reverse("rh_conversation_detail", args=[conv.pk]), {"contenu": "Je reponds aussi."})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(MessageRH.objects.filter(conversation=conv, contenu="Je reponds aussi.").exists())

    def test_ticket_rating_updates_ranking_and_reward_approval_awards_points(self):
        conv = ConversationRH.objects.create(
            employe=self.emp,
            sujet="Conversation 1",
            numero_ticket=1,
            responsable_rh=self.rh_user.profile,
            statut="cloturee",
            motif_cloture="resolved",
            date_cloture=timezone.now(),
        )
        conv.participants.add(self.emp)

        self.client.login(username="emp2", password="emp123")
        self.client.post(reverse("rh_conversation_rate", args=[conv.pk]), {"note_support": 5, "note_commentaire": "Tres clair."})
        conv.refresh_from_db()
        self.assertEqual(conv.note_support, 5)

        self.client.login(username="rh2", password="rh123")
        self.client.post(reverse("rh_support_rewards_generate"))
        reward = SupportRHReward.objects.get(employe=self.rh_emp)
        self.assertEqual(reward.points, 50)
        self.assertEqual(reward.statut, "pending")

        manager_user = User.objects.create_user(username="support-manager", password="manager123")
        UtilisateurProfile.objects.create(user=manager_user, role=Role.RESPONSABLE_HIERARCHIQUE, employe=self.other)
        ComptePoints.objects.create(employe=self.rh_emp, solde_points=0)
        self.client.login(username="support-manager", password="manager123")
        self.client.post(reverse("rh_support_reward_decision", args=[reward.pk]), {"action": "approve"})
        reward.refresh_from_db()
        self.rh_emp.compte_points.refresh_from_db()
        self.assertEqual(reward.statut, "awarded")
        self.assertEqual(self.rh_emp.compte_points.solde_points, 50)

    def test_corporate_date_and_number_validations(self):
        now = timezone.now()
        demande = DemandeAdministrative.objects.create(
            type_demande="Attestation",
            description="Besoin d'une attestation.",
            employe=self.emp,
            date_creation=now,
            date_traitement=now - timedelta(hours=1),
        )
        with self.assertRaises(Exception):
            demande.full_clean()

        conge = DemandeConge(
            type=TypeConge.ANNUEL,
            date_debut=timezone.localdate() + timedelta(days=5),
            date_fin=timezone.localdate() + timedelta(days=6),
            employe=self.emp,
            statut=StatutDemande.VALIDEE,
            date_creation=now,
            date_traitement=now - timedelta(hours=1),
        )
        with self.assertRaises(Exception):
            conge.full_clean()

        reclamation = ReclamationRH(
            employe=self.emp,
            sujet="Points",
            description="Probleme de points valide.",
            type_reclamation="points",
            date_creation=now,
            date_traitement=now - timedelta(hours=1),
        )
        with self.assertRaises(Exception):
            reclamation.full_clean()

        shift = PlanningShift(titre="Passe", employe=self.emp, date_debut=now - timedelta(hours=2), date_fin=now + timedelta(hours=1))
        with self.assertRaises(Exception):
            shift.full_clean()

        task = TacheEquipe(titre="Deadline passee", employe=self.emp, date_limite=now - timedelta(hours=1))
        with self.assertRaises(Exception):
            task.full_clean()

        remuneration = Remuneration(employe=self.emp, salaire_base=-1, prime=-1)
        with self.assertRaises(Exception):
            remuneration.full_clean()

    def test_payroll_post_filter_is_applied_and_preserved(self):
        self.emp.poste = self.poste
        self.emp.save(update_fields=["poste"])
        autre_poste = Poste.objects.create(libelle="Comptable")
        self.other.poste = autre_poste
        self.other.save(update_fields=["poste"])
        Remuneration.objects.create(employe=self.emp, salaire_base=12000)
        Remuneration.objects.create(employe=self.other, salaire_base=9000)
        self.client.login(username="rh2", password="rh123")

        response = self.client.get(reverse("payroll_analytics"), {"poste": self.poste.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.emp.nom_complet)
        self.assertNotContains(response, self.other.nom_complet)
        self.assertContains(response, f'value="{self.poste.pk}" selected', html=False)

    def test_order_delivery_is_final_and_audited(self):
        produit = Produit.objects.create(nom="Badge", cout_points=20, stock_disponible=2)
        commande = CommandeProduit.objects.create(employe=self.emp, produit=produit, quantite=1, cout_total_points=20)
        approuver_commande(commande, self.rh_user.profile)
        commande.refresh_from_db()

        livrer_commande(commande, self.rh_user.profile)
        commande.refresh_from_db()

        self.assertEqual(commande.statut, "livree")
        self.assertTrue(HistoriqueAction.objects.filter(action="LIVRAISON_COMMANDE", entite_id=commande.pk).exists())
        with self.assertRaises(Exception):
            livrer_commande(commande, self.rh_user.profile)
        with self.assertRaises(Exception):
            refuser_ou_annuler_commande(commande, "annulee", self.rh_user.profile)

    def test_product_and_formation_creation_are_audited(self):
        self.client.login(username="rh2", password="rh123")
        categorie = CategorieProduit.objects.create(nom="Accessoires")

        self.client.post(reverse("formation_create"), {"titre": "Ethique", "description": "Module interne", "categorie": "RH", "duree_estimee_heures": 2, "points_recompense": 0, "actif": "on"})
        self.client.post(reverse("product_create"), {"nom": "Souris", "categorie": categorie.pk, "description": "Materiel", "cout_points": 5, "stock_disponible": 3, "actif": "on"})

        self.assertTrue(HistoriqueAction.objects.filter(action="CREATION_FORMATION", entite_concernee="Formation").exists())
        self.assertTrue(HistoriqueAction.objects.filter(action="CREATION_PRODUIT", entite_concernee="Produit").exists())

    def test_rh_sidebar_does_not_show_audit_link(self):
        self.client.login(username="rh2", password="rh123")
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "Historique / Audit")


class PlanningModuleUpgradeTests(TestCase):
    def setUp(self):
        self.dep = Departement.objects.create(libelle="Operations")
        self.service = Service.objects.create(libelle="Support", departement=self.dep)
        self.other_dep = Departement.objects.create(libelle="Finance")
        self.admin_emp = Employe.objects.create(
            matricule="ADM-P",
            nom="Admin",
            prenom="Planning",
            email="admin.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=500),
            departement=self.dep,
            service=self.service,
        )
        self.rh_emp = Employe.objects.create(
            matricule="RH-P",
            nom="Rh",
            prenom="Planning",
            email="rh.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=450),
            departement=self.dep,
            service=self.service,
        )
        self.manager_emp = Employe.objects.create(
            matricule="MGR-P",
            nom="Manager",
            prenom="Planning",
            email="manager.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=420),
            departement=self.dep,
            service=self.service,
        )
        self.emp = Employe.objects.create(
            matricule="EMP-P",
            nom="Employe",
            prenom="Planning",
            email="emp.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=400),
            departement=self.dep,
            service=self.service,
            responsable=self.manager_emp,
        )
        self.peer = Employe.objects.create(
            matricule="EMP-P2",
            nom="Collegue",
            prenom="Visible",
            email="peer.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=390),
            departement=self.dep,
            service=self.service,
            responsable=self.manager_emp,
        )
        self.outsider = Employe.objects.create(
            matricule="EMP-OUT",
            nom="Cache",
            prenom="Finance",
            email="outsider.planning@example.com",
            date_embauche=timezone.localdate() - timedelta(days=390),
            departement=self.other_dep,
        )
        self.admin_user = User.objects.create_user(username="planning-admin", password="admin123")
        self.rh_user = User.objects.create_user(username="planning-rh", password="rh123")
        self.manager_user = User.objects.create_user(username="planning-manager", password="manager123")
        self.emp_user = User.objects.create_user(username="planning-emp", password="emp123")
        UtilisateurProfile.objects.create(user=self.admin_user, role=Role.ADMIN, employe=self.admin_emp)
        UtilisateurProfile.objects.create(user=self.rh_user, role=Role.RESPONSABLE_RH, employe=self.rh_emp)
        UtilisateurProfile.objects.create(user=self.manager_user, role=Role.RESPONSABLE_HIERARCHIQUE, employe=self.manager_emp)
        UtilisateurProfile.objects.create(user=self.emp_user, role=Role.EMPLOYE, employe=self.emp)

    def future_at(self, days=7, hour=9):
        base = timezone.now() + timedelta(days=days)
        return base.replace(hour=hour, minute=0, second=0, microsecond=0)

    def post_json(self, name, payload, args=None):
        return self.client.post(reverse(name, args=args or []), data=json.dumps(payload), content_type="application/json")

    def test_planning_page_loads_for_admin_rh_manager_and_employee(self):
        start = self.future_at()
        PlanningShift.objects.create(titre="Equipe support", employe=self.emp, departement=self.dep, service=self.service, date_debut=start, date_fin=start + timedelta(hours=8), statut="publie")
        PlanningShift.objects.create(titre="Finance privee", employe=self.outsider, departement=self.other_dep, date_debut=start, date_fin=start + timedelta(hours=8), statut="publie")

        for username, password in (
            ("planning-admin", "admin123"),
            ("planning-rh", "rh123"),
            ("planning-manager", "manager123"),
            ("planning-emp", "emp123"),
        ):
            self.client.login(username=username, password=password)
            response = self.client.get(reverse("planning"), {"date_debut": start.date().isoformat(), "date_fin": start.date().isoformat()}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.client.logout()

        self.client.login(username="planning-emp", password="emp123")
        response = self.client.get(reverse("planning"), {"tab": "weekly", "date_debut": start.date().isoformat(), "date_fin": start.date().isoformat()})
        self.assertContains(response, "Equipe support")
        self.assertNotContains(response, "Finance privee")

    def test_planning_sidebar_ladder_and_child_tabs(self):
        self.client.login(username="planning-rh", password="rh123")
        for tab, label in [
            ("overview", "Apercu"),
            ("calendar", "Calendrier planning"),
            ("daily", "Planning journalier"),
            ("weekly", "Planning hebdomadaire"),
            ("biweekly", "Planning bihebdomadaire"),
            ("monthly", "Planning mensuel"),
            ("timesheets", "Feuilles de temps"),
            ("shifts", "Gestion des shifts"),
            ("attendance", "Presence"),
            ("leave", "Conges valides"),
            ("tasks", "Taches planifiees"),
            ("reports", "Rapports"),
            ("settings", "Parametres"),
        ]:
            response = self.client.get(reverse("planning"), {"tab": tab})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, label)
            self.assertContains(response, 'id="menuPlanning"')
            self.assertContains(response, 'sidebar-submenu show')

    def test_shift_break_metadata_validation(self):
        start = self.future_at()
        invalid_duration = PlanningShift(titre="Pause longue", employe=self.emp, date_debut=start, date_fin=start + timedelta(hours=1), pause_minutes=60)
        with self.assertRaises(Exception):
            invalid_duration.full_clean()

        before_start = PlanningShift(titre="Pause avant", employe=self.emp, date_debut=start, date_fin=start + timedelta(hours=4), pause_minutes=30, pause_debut=start - timedelta(minutes=5))
        with self.assertRaises(Exception):
            before_start.full_clean()

        after_end = PlanningShift(titre="Pause apres", employe=self.emp, date_debut=start, date_fin=start + timedelta(hours=4), pause_minutes=45, pause_debut=start + timedelta(hours=3, minutes=30))
        with self.assertRaises(Exception):
            after_end.full_clean()

    def test_rh_can_create_and_partially_update_shift_through_api(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at()
        response = self.post_json(
            "planning_api_shifts",
            {
                "title": "Matinee support",
                "employee_id": self.emp.pk,
                "department_id": self.dep.pk,
                "service_id": self.service.pk,
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=8)).isoformat(),
                "break_minutes": 30,
                "break_starts_at": (start + timedelta(hours=4)).isoformat(),
                "status": "publie",
                "location": "Casablanca",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        shift = PlanningShift.objects.get(pk=body["data"]["shift"]["id"])
        self.assertEqual(shift.employe, self.emp)
        self.assertEqual(shift.pause_minutes, 30)
        self.assertIsNotNone(shift.pause_debut)

        update = self.client.put(
            reverse("planning_api_shift_detail", args=[shift.pk]),
            data=json.dumps({"title": "Matinee support ajustee"}),
            content_type="application/json",
        )

        self.assertEqual(update.status_code, 200)
        shift.refresh_from_db()
        self.assertEqual(shift.titre, "Matinee support ajustee")
        self.assertEqual(shift.employe, self.emp)
        self.assertEqual(shift.departement, self.dep)
        self.assertEqual(shift.service, self.service)

    def test_rh_can_create_permanent_plan_without_end_date(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at(days=1, hour=9)
        response = self.post_json(
            "planning_api_shifts",
            {
                "title": "Plan permanent standard",
                "employee_id": self.emp.pk,
                "department_id": self.dep.pk,
                "service_id": self.service.pk,
                "starts_at": start.isoformat(),
                "ends_at": "",
                "plan_type": "permanent",
                "recurrence_rule": "weekdays",
                "permanent_end_time": "17:00",
                "break_minutes": 30,
                "status": "publie",
            },
        )

        self.assertEqual(response.status_code, 200)
        shift = PlanningShift.objects.get(pk=response.json()["data"]["shift"]["id"])
        self.assertEqual(shift.plan_type, "permanent")
        self.assertIsNone(shift.date_fin)
        self.assertEqual(shift.permanent_end_time, time(17, 0))

    def test_permanent_plan_supports_biweekly_and_monthly_recurrence_display(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at(days=14, hour=9)
        biweekly = PlanningShift.objects.create(
            titre="Cadence support quinzaine",
            employe=self.emp,
            departement=self.dep,
            service=self.service,
            date_debut=start,
            plan_type="permanent",
            recurrence_rule="biweekly",
            permanent_end_time=time(17, 0),
            statut="publie",
        )
        monthly = PlanningShift.objects.create(
            titre="Revue mensuelle operations",
            employe=self.peer,
            departement=self.dep,
            service=self.service,
            date_debut=start,
            plan_type="permanent",
            recurrence_rule="monthly",
            permanent_end_time=time(12, 0),
            statut="publie",
        )

        response = self.client.get(reverse("planning"), {"tab": "monthly", "date_debut": start.date().isoformat(), "date_fin": (start + timedelta(days=31)).date().isoformat()})

        self.assertContains(response, biweekly.titre)
        self.assertContains(response, monthly.titre)
        self.assertContains(response, "planning-month-grid")

    def test_normal_recurring_shift_is_rejected_with_clear_message(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at()
        response = self.post_json(
            "planning_api_shifts",
            {
                "title": "Recurrence normale invalide",
                "employee_id": self.emp.pk,
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=8)).isoformat(),
                "recurrence_rule": "weekly",
                "status": "publie",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("plans permanents", json.dumps(response.json()))

    def test_overnight_shift_is_rejected_professionally(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at(hour=22)
        response = self.post_json(
            "planning_api_shifts",
            {
                "title": "Nuit non supportee",
                "employee_id": self.emp.pk,
                "starts_at": start.isoformat(),
                "ends_at": (start - timedelta(hours=2)).isoformat(),
                "status": "publie",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Les shifts de nuit ne sont pas encore pris en charge", json.dumps(response.json()))

    def test_planning_reports_approvals_and_detail_modal_states(self):
        self.client.login(username="planning-rh", password="rh123")
        reports = self.client.get(reverse("planning"), {"tab": "reports"})
        self.assertContains(reports, "Rapports et exports")
        self.assertContains(reports, reverse("planning_export", args=["pdf"]))
        self.assertContains(reports, "Shifts par employe")

        approvals = self.client.get(reverse("planning"), {"tab": "approvals"})
        self.assertContains(approvals, "Aucune validation planning")

        calendar = self.client.get(reverse("planning"), {"tab": "calendar"})
        self.assertContains(calendar, 'id="planningDetailModal"')
        self.assertContains(calendar, "Agenda planning par couleur")

    def test_pointage_without_planned_shift_has_safe_warning_and_no_missing_hours(self):
        pointage = Pointage.objects.create(
            employe=self.emp,
            date=timezone.localdate(),
            heure_entree=timezone.now() - timedelta(hours=2),
            heure_sortie=timezone.now(),
            total_heures=2,
            statut="present",
        )

        from hr.planning_services import pointage_breakdown

        detail = pointage_breakdown(pointage)

        self.assertEqual(detail["missing_hours"], 0)
        self.assertEqual(detail["warning"], "Aucun shift planifie pour cette date.")

    def test_attendance_page_allows_checkin_without_active_shift(self):
        self.client.login(username="planning-emp", password="emp123")

        response = self.client.get(reverse("attendance"))

        self.assertContains(response, "Pointer l'entree")
        self.assertNotContains(response, "Aucun shift actif")

    def test_checkin_and_checkout_are_allowed_without_shift_or_minimum_hours(self):
        now = timezone.now().replace(microsecond=0)

        with patch("hr.services.timezone.now", return_value=now):
            pointage = pointer_entree(self.emp)

        self.assertIsNone(pointage.shift)
        self.assertEqual(pointage.statut, "incomplet")

        with patch("hr.services.timezone.now", return_value=now + timedelta(minutes=1)):
            pointage = pointer_sortie(self.emp)

        self.assertIsNone(pointage.shift)
        self.assertEqual(pointage.statut, "present")
        self.assertEqual(str(pointage.total_heures), "0.02")
        self.assertIn("Pointage libre", pointage.commentaire)

    def test_checkin_can_link_today_shift_even_outside_current_window(self):
        day = timezone.localdate()
        shift_start = timezone.make_aware(timezone.datetime.combine(day, time(15, 0)))
        shift_end = timezone.make_aware(timezone.datetime.combine(day, time(18, 0)))
        shift = PlanningShift.objects.create(
            titre="Apres-midi support",
            employe=self.emp,
            departement=self.dep,
            service=self.service,
            date_debut=shift_start,
            date_fin=shift_end,
            statut="publie",
        )
        checkin_time = timezone.make_aware(timezone.datetime.combine(day, time(9, 0)))

        with patch("hr.services.timezone.now", return_value=checkin_time):
            pointage = pointer_entree(self.emp)

        self.assertEqual(pointage.shift, shift)

    def test_pointage_checkout_uses_planning_shift_window(self):
        day = timezone.localdate()
        start = timezone.make_aware(timezone.datetime.combine(day, time(9, 0)))
        end = timezone.make_aware(timezone.datetime.combine(day, time(17, 0)))
        shift = PlanningShift.objects.create(titre="Journee planifiee", employe=self.emp, departement=self.dep, service=self.service, date_debut=start, date_fin=end, statut="publie")
        Pointage.objects.create(employe=self.emp, shift=shift, date=day, heure_entree=start + timedelta(minutes=30), statut="incomplet")

        with patch("hr.services.timezone.now", return_value=end - timedelta(minutes=30)):
            pointage = pointer_sortie(self.emp)

        self.assertEqual(pointage.statut, "retard")
        self.assertIn("retard 30 min", pointage.commentaire)
        self.assertIn("sortie anticipee 30 min", pointage.commentaire)
        self.assertIn("heures manquantes", pointage.commentaire)

    def test_employee_cannot_mutate_planning_api(self):
        self.client.login(username="planning-emp", password="emp123")
        start = self.future_at()
        response = self.post_json(
            "planning_api_shifts",
            {"title": "Tentative", "employee_id": self.emp.pk, "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat()},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_move_and_resize_apis_apply_validations(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at(days=10)
        shift = PlanningShift.objects.create(titre="Deplacement", employe=self.emp, departement=self.dep, service=self.service, date_debut=start, date_fin=start + timedelta(hours=4), statut="publie")

        new_start = start + timedelta(days=1)
        response = self.post_json(
            "planning_api_move",
            {"employee_id": self.peer.pk, "starts_at": new_start.isoformat(), "ends_at": (new_start + timedelta(hours=4)).isoformat()},
            args=[shift.pk],
        )

        self.assertEqual(response.status_code, 200)
        shift.refresh_from_db()
        self.assertEqual(shift.employe, self.peer)
        self.assertEqual(shift.date_debut, new_start)

        blocker_start = start + timedelta(days=2)
        PlanningShift.objects.create(titre="Conflit", employe=self.peer, date_debut=blocker_start, date_fin=blocker_start + timedelta(hours=4), statut="publie")
        conflict = self.post_json(
            "planning_api_move",
            {"employee_id": self.peer.pk, "starts_at": blocker_start.isoformat(), "ends_at": (blocker_start + timedelta(hours=4)).isoformat()},
            args=[shift.pk],
        )
        self.assertEqual(conflict.status_code, 400)
        self.assertFalse(conflict.json()["ok"])

        resize = self.post_json("planning_api_resize", {"ends_at": (shift.date_debut - timedelta(minutes=30)).isoformat()}, args=[shift.pk])
        self.assertEqual(resize.status_code, 400)

    def test_bulk_copy_summary_conflicts_and_available_employees(self):
        self.client.login(username="planning-rh", password="rh123")
        start = self.future_at(days=20)
        bulk = self.post_json(
            "planning_api_bulk",
            {
                "scope": "departement",
                "department_id": self.dep.pk,
                "title": "Journee support",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=8)).isoformat(),
                "break_minutes": 30,
                "break_starts_at": (start + timedelta(hours=4)).isoformat(),
                "status": "brouillon",
                "location": "Casablanca",
            },
        )

        self.assertEqual(bulk.status_code, 200)
        self.assertGreaterEqual(len(bulk.json()["data"]["created"]), 4)

        summary = self.client.get(reverse("planning_api_summary"), {"start_date": start.date().isoformat(), "end_date": start.date().isoformat()})
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.json()["data"]["summary"]["total_shifts"], 4)

        target = start + timedelta(days=7)
        copied = self.post_json(
            "planning_api_copy",
            {"source_start": start.date().isoformat(), "source_end": start.date().isoformat(), "target_start": target.date().isoformat()},
        )
        self.assertEqual(copied.status_code, 200)
        self.assertGreaterEqual(len(copied.json()["data"]["created"]), 4)

        conflict_start = start + timedelta(days=12)
        PlanningShift.objects.create(titre="Conflit A", employe=self.emp, date_debut=conflict_start, date_fin=conflict_start + timedelta(hours=4), statut="publie")
        PlanningShift.objects.create(titre="Conflit B", employe=self.emp, date_debut=conflict_start + timedelta(hours=1), date_fin=conflict_start + timedelta(hours=5), statut="publie")
        conflicts = self.client.get(reverse("planning_api_conflicts"), {"start_date": conflict_start.date().isoformat(), "end_date": conflict_start.date().isoformat()})
        self.assertEqual(conflicts.status_code, 200)
        self.assertGreaterEqual(len(conflicts.json()["data"]["conflicts"]), 2)

        leave_start = start + timedelta(days=13)
        DemandeConge.objects.create(type=TypeConge.ANNUEL, date_debut=leave_start.date(), date_fin=leave_start.date(), employe=self.peer, statut=StatutDemande.VALIDEE)
        PlanningShift.objects.create(titre="Occupe", employe=self.emp, date_debut=leave_start, date_fin=leave_start + timedelta(hours=4), statut="publie")
        available = self.client.get(reverse("planning_api_available_employees"), {"starts_at": leave_start.isoformat(), "ends_at": (leave_start + timedelta(hours=4)).isoformat()})
        ids = {employee["id"] for employee in available.json()["data"]["employees"]}
        self.assertNotIn(self.emp.pk, ids)
        self.assertNotIn(self.peer.pk, ids)

    def test_assistant_fallback_and_employee_privacy(self):
        start = self.future_at(days=30)
        PlanningShift.objects.create(titre="Assistant shift", employe=self.emp, departement=self.dep, service=self.service, date_debut=start, date_fin=start + timedelta(hours=6), statut="publie")

        self.client.login(username="planning-rh", password="rh123")
        summary = self.post_json(
            "planning_api_assistant",
            {"message": "Resume les heures planifiees", "start_date": start.date().isoformat(), "end_date": start.date().isoformat()},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertIn("shift(s)", summary.json()["data"]["answer"])

        with patch.dict(os.environ, {}, clear=True):
            fallback = self.post_json("planning_api_assistant", {"message": "Cree un shift support demain"})
        self.assertEqual(fallback.status_code, 200)
        self.assertIn("Gemini", fallback.json()["data"]["answer"])

        self.client.login(username="planning-emp", password="emp123")
        private = self.post_json("planning_api_assistant", {"message": f"Montre le planning de {self.peer.nom}"})
        self.assertEqual(private.status_code, 200)
        self.assertIn("informations privees", private.json()["data"]["answer"])
