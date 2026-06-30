# Carte des tables et de leur gestion dans le code

Convention : le nom SQL probable suit le format Django `app_modele` en minuscules.

## Table / Modele : UtilisateurProfile

Nom du modele Django : UtilisateurProfile  
Table SQL probable : accounts_utilisateurprofile  
App Django : accounts  
Fichier modele : accounts/models.py  
Fichiers formulaires lies : accounts/forms.py pour login ; pas de formulaire profile metier.  
Fichiers vues lies : accounts/views.py, hr/permissions.py, hr/views.py, core/views.py  
Templates lies : templates/auth/login.html, templates/base.html  
Champs principaux : user, role, actif, employe  
Relations principales : OneToOne vers User, OneToOne vers Employe, notifications, actions, messages, ajustements.  
Fonction metier : profil applicatif qui porte le role ADMIN, RESPONSABLE_RH, RESPONSABLE_HIERARCHIQUE ou EMPLOYE.  
Validations : role par choices, actif controle a la connexion.  
Permissions : hr/permissions.py role_required(), has_any_role().  
Actions CRUD : creation dans les commands seed ; consultation indirecte par vues.  
Traitements speciaux : notifications non lues dans accounts/context_processors.py, controle profil actif dans accounts/views.py.

## Table / Modele : Departement

Table SQL probable : hr_departement  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py DepartementForm  
Fichiers vues lies : hr/views.py departements_list(), departement_save(), departement_delete()  
Templates lies : templates/departements/list.html, templates/departements/form.html  
Admin : hr/admin.py  
Champs principaux : libelle, description, created_at, updated_at  
Relations principales : Service, Employe, Actualite  
Fonction metier : structure RH de regroupement des employes et services.  
Validations : libelle minimum 2 caracteres et unique insensible a la casse dans DepartementForm.clean_libelle().  
Permissions : vues departements protegees ADMIN/RH.  
Actions CRUD : sauvegarde via save_model_form(), suppression via departement_delete().  
Traitements speciaux : filtre d'employes, formations par departement, statistiques paie par departement.

## Table / Modele : Service

Table SQL probable : hr_service  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py ServiceForm  
Fichiers vues lies : hr/views.py service_save(), service_delete(), departements_list()  
Templates lies : templates/departements/list.html  
Admin : hr/admin.py  
Champs principaux : libelle, description, departement, created_at, updated_at  
Relations principales : ForeignKey Departement, Employe  
Fonction metier : sous-structure d'un departement.  
Validations : libelle minimum 2 caracteres dans ServiceForm.  
Permissions : ADMIN/RH.  
Actions CRUD : save_model_form(), service_delete().  
Traitements speciaux : rattachement employe/service dans EmployeForm et GestionPosteForm.

## Table / Modele : Poste

Table SQL probable : hr_poste  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py PosteForm  
Fichiers vues lies : hr/views.py poste_save(), poste_delete(), position_management(), position_edit()  
Templates lies : templates/departements/list.html, templates/employes/positions.html, templates/employes/position_form.html, templates/employes/hierarchy.html  
Admin : hr/admin.py  
Champs principaux : libelle, description, niveau, rang_hierarchique, est_direction, est_manager  
Relations principales : Employe  
Fonction metier : definit le poste, le niveau et le rang dans l'organigramme.  
Validations : libelle minimum 2 caracteres dans PosteForm.  
Permissions : ADMIN/RH pour creation/modification.  
Actions CRUD : save_model_form(), poste_delete().  
Traitements speciaux : build_hierarchy_tree() utilise rang_hierarchique, est_direction et est_manager.

## Table / Modele : Employe

Table SQL probable : hr_employe  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py EmployeForm, GestionPosteForm  
Fichiers vues lies : hr/views.py employes_list(), employe_detail(), employe_save(), employe_archive(), position_edit(), accessible_employees()  
Templates lies : templates/employes/list.html, detail.html, form.html, positions.html, hierarchy.html, tree_node.html  
Admin : hr/admin.py EmployeAdmin  
Tests lies : hr/tests.py FormValidationTests, WorkflowSecurityTests, NewHrFeatureAbuseTests  
Champs principaux : matricule, nom, prenom, email, telephone, dates, departement, service, poste, responsable, actif, photo  
Relations principales : Departement, Service, Poste, self responsable, DemandeConge, Document, Pointage, SoldeConge, ComptePoints, ReclamationRH, UtilisateurProfile  
Fonction metier : profil RH central d'un salarie.  
Validations : formulaire employe ; modele Employe.clean() pour hierarchie.  
Permissions : accessible_employees(), can_view_employees(), role_required sur creation/modification.  
Actions CRUD : liste/detail/creation/modification/archive/photo.  
Traitements speciaux : anciennete_annees, hierarchie, responsables directs, documents, conges, pointage, points.

## Table / Modele : DemandeConge

Table SQL probable : hr_demandeconge  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py DemandeCongeForm  
Fichiers vues lies : hr/views.py conges_list(), conge_submit(), conge_validate(), conge_refuse(), conge_cancel(), conges_for_profile()  
Services lies : hr/services.py deduire_solde_conge(), rembourser_solde_conge()  
Templates lies : templates/conges/list.html, templates/conges/form.html  
Admin : hr/admin.py  
Tests lies : hr/tests.py leave_form, leave_balance  
Champs principaux : type, date_debut, date_fin, motif, statut, employe, traitee_par, date_traitement, commentaire_reponse  
Relations principales : Employe, SoldeConge via service, MouvementSoldeConge, Document justificatif indirect  
Fonction metier : demandes de conge et absence.  
Validations : dates dans DemandeCongeForm.clean() et DemandeConge.clean(), solde et chevauchement dans formulaire.  
Permissions : conges_for_profile(), can_process_conge().  
Actions CRUD : creation, validation, refus, annulation.  
Traitements speciaux : deduction/remboursement de solde, notification, audit.

## Table / Modele : DemandeAdministrative

Table SQL probable : hr_demandeadministrative  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : hr/forms.py DemandeAdministrativeForm  
Fichiers vues lies : hr/views.py demandes_list(), demande_submit(), demande_process(), demandes_for_profile()  
Templates lies : templates/demandes/list.html, templates/demandes/form.html  
Admin : hr/admin.py  
Tests lies : hr/tests.py test_finalized_admin_request_cannot_be_processed_again  
Champs principaux : type_demande, description, statut, date_creation, employe, traitee_par, date_traitement, reponse  
Relations principales : Employe, Document  
Fonction metier : workflow de demandes RH administratives.  
Validations : type et description dans DemandeAdministrativeForm.  
Permissions : employe voit ses demandes, RH/Admin voient tout et traitent.  
Actions CRUD : soumission, traitement statut/reponse.  
Traitements speciaux : blocage d'une demande finalisee, piece jointe, notification, audit.

## Table / Modele : Document

Table SQL probable : hr_document  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : upload gere dans hr/views.py, pas de ModelForm dedie.  
Fichiers vues lies : document_upload(), document_download(), document_delete(), accessible_documents(), create_document()  
Templates lies : templates/documents/list.html, templates/documents/table.html  
Admin : hr/admin.py  
Tests lies : test_document_upload_rejects_disallowed_extension  
Champs principaux : fichier, nom_fichier, nom_original, categorie, chemin_fichier, date_ajout, taille, employe, demande_admin, uploade_par  
Relations principales : Employe, DemandeAdministrative, User  
Fonction metier : stockage des justificatifs et documents RH.  
Validations : extension et taille dans validate_uploaded_file().  
Permissions : accessible_documents() et controle dans document_download()/document_delete().  
Actions CRUD : upload, telechargement, suppression.  
Traitements speciaux : securite URL directe, taille max 5 Mo, extensions autorisees.

## Table / Modele : Notification

Table SQL probable : hr_notification  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : notifications_list(), notification_read(), notifications_read_all()  
Services lies : notify(), notify_employee(), notify_role(), notify_rh_and_admin()  
Templates lies : templates/notifications/list.html, templates/base.html  
Admin : hr/admin.py  
Champs principaux : message, date_envoi, lue, destinataire, lien  
Relations principales : UtilisateurProfile  
Fonction metier : alertes utilisateur.  
Validations : destinataire obligatoire.  
Permissions : notification_read filtre par destinataire.  
Actions CRUD : creation service, lecture individuelle, lecture globale.  
Traitements speciaux : compteur de notifications non lues dans accounts/context_processors.py.

## Table / Modele : HistoriqueAction

Table SQL probable : hr_historiqueaction  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : audit_history()  
Services lies : audit(), audit_profile()  
Templates lies : templates/audit/list.html  
Admin : hr/admin.py  
Tests lies : test_audit_filters_load  
Champs principaux : action, details, date_action, utilisateur, entite_concernee, entite_id  
Relations principales : UtilisateurProfile  
Fonction metier : journal d'audit.  
Validations : champs simples.  
Permissions : consultation ADMIN/RH.  
Actions CRUD : creation par services, consultation filtree.  
Traitements speciaux : filtres role/action/module/date.

## Table / Modele : SoldeConge

Table SQL probable : hr_soldeconge  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : dashboard(), conge_validate(), conge_cancel() indirectement  
Services lies : deduire_solde_conge(), rembourser_solde_conge()  
Templates lies : templates/dashboard/index.html  
Tests lies : test_leave_balance_blocks_excess_and_deducts_when_validated  
Champs principaux : employe, jours_disponibles, jours_utilises  
Relations principales : OneToOne Employe, MouvementSoldeConge  
Fonction metier : solde actuel de conges.  
Validations : SoldeConge.clean() interdit negatif.  
Permissions : manipule par workflows conges.  
Actions CRUD : get_or_create dans services/dashboard.  
Traitements speciaux : deduction et remboursement transactionnels.

## Table / Modele : MouvementSoldeConge

Table SQL probable : hr_mouvementsoldeconge  
App Django : hr  
Fichier modele : hr/models.py  
Services lies : deduire_solde_conge(), rembourser_solde_conge()  
Champs principaux : solde, demande, type_mouvement, jours, solde_avant, solde_apres, description, date_mouvement, cree_par  
Relations principales : SoldeConge, DemandeConge, UtilisateurProfile  
Fonction metier : historique du solde de conges.  
Validations : cree par services apres controle du solde.  
Permissions : pas de vue dediee trouvee.  
Actions CRUD : creation automatique.  
Traitements speciaux : preuve de deduction/remboursement.

## Table / Modele : ParametrePointage

Table SQL probable : hr_parametrepointage  
App Django : hr  
Fichier modele : hr/models.py  
Services lies : parametre_pointage_actif(), pointer_sortie()  
Champs principaux : heure_debut_officielle, heure_fin_officielle, tolerance_retard_minutes, heures_minimum_jour, points_presence_normale, penalite_retard, penalite_sortie_anticipee, bonus_heures_supplementaires, actif  
Relations principales : Pointage via service.  
Fonction metier : parametrage du calcul presence/points.  
Validations : types Django ; pas de formulaire dedie trouve.  
Permissions : pas d'ecran CRUD trouve.  
Actions CRUD : creation automatique si absent.  
Traitements speciaux : regles de retard, sortie anticipee et bonus.

## Table / Modele : Pointage

Table SQL probable : hr_pointage  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : attendance_view(), attendance_checkin(), attendance_checkout()  
Services lies : pointer_entree(), pointer_sortie()  
Templates lies : templates/pointage/index.html, templates/dashboard/index.html  
Tests lies : test_checkout_before_checkin_blocked  
Champs principaux : employe, date, heure_entree, heure_sortie, total_heures, statut, points_calcules  
Relations principales : Employe, TransactionPoints indirecte  
Fonction metier : presence entree/sortie quotidienne.  
Validations : sortie apres entree ; contrainte unique employe/date.  
Permissions : attendance_view filtre selon role.  
Actions CRUD : entree, sortie, consultation.  
Traitements speciaux : calcul heures, retard, sortie anticipee, points.

## Table / Modele : ComptePoints

Table SQL probable : hr_comptepoints  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : shop(), attendance_view(), manual_points(), dashboard()  
Services lies : appliquer_transaction_points()  
Templates lies : templates/pointage/index.html, templates/boutique/index.html, templates/dashboard/index.html  
Tests lies : test_points_balance_never_negative, test_hr_can_add_points_with_reason  
Champs principaux : employe, solde_points  
Relations principales : OneToOne Employe, TransactionPoints  
Fonction metier : solde actuel de points.  
Validations : ComptePoints.clean() interdit negatif.  
Permissions : modifications via services et vues proteges.  
Actions CRUD : get_or_create dans services/vues.  
Traitements speciaux : verrou select_for_update dans appliquer_transaction_points().

## Table / Modele : TransactionPoints

Table SQL probable : hr_transactionpoints  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : shop() historique boutique, manual_points() indirect  
Services lies : appliquer_transaction_points()  
Templates lies : templates/boutique/index.html  
Tests lies : formation_completion_awards_points_once, points_balance_never_negative  
Champs principaux : employe, type_transaction, source, points, solde_avant, solde_apres, description, date_transaction, cree_par, objet_lie  
Relations principales : Employe, UtilisateurProfile  
Fonction metier : historique complet des points.  
Validations : cree via service central.  
Permissions : consultation selon vue ; creation service.  
Actions CRUD : creation automatique.  
Traitements speciaux : audit de chaque transaction.

## Table / Modele : AjustementPointsManuel

Table SQL probable : hr_ajustementpointsmanuel  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : AjustementPointsManuelForm  
Fichiers vues lies : manual_points()  
Templates lies : templates/points/manual.html  
Champs principaux : employe, type_adjustement, nombre_points, motif_obligatoire, reclamation_liee, cree_par, date_creation  
Relations principales : Employe, ReclamationRH, UtilisateurProfile  
Fonction metier : trace de correction manuelle.  
Validations : nombre positif et motif obligatoire.  
Permissions : ADMIN/RH seulement, auto-ajustement RH bloque.  
Actions CRUD : creation dans manual_points().  
Traitements speciaux : declenche TransactionPoints et notification.

## Table / Modele : Formation

Table SQL probable : hr_formation  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : FormationForm, AffectationFormationForm  
Fichiers vues lies : formations_admin(), formation_create()  
Templates lies : templates/formations/admin.html  
Champs principaux : titre, description, categorie, duree_estimee_heures, points_recompense, actif  
Relations principales : AffectationFormation  
Fonction metier : catalogue de formations.  
Validations : titre obligatoire/minimum dans FormationForm.  
Permissions : creation ADMIN/RH.  
Actions CRUD : creation et liste.  
Traitements speciaux : points_recompense utilises a la completion.

## Table / Modele : AffectationFormation

Table SQL probable : hr_affectationformation  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : AffectationFormationForm  
Fichiers vues lies : formations_admin(), my_trainings(), training_status(), formation_assignment_status()  
Templates lies : templates/formations/admin.html, templates/formations/me.html  
Tests lies : deadline, completion points once, employee cannot complete another training  
Champs principaux : formation, employe, assigne_par, date_affectation, date_limite, statut, date_completion, points_attribues  
Relations principales : Formation, Employe, UtilisateurProfile  
Fonction metier : suivi individuel d'une formation.  
Validations : dates coherentes, cible obligatoire, contrainte unique formation/employe active.  
Permissions : RH/Admin affectent ; employe modifie seulement sa propre formation.  
Actions CRUD : affectation, statut, completion.  
Traitements speciaux : attribution unique des points.

## Table / Modele : ConversationRH

Table SQL probable : hr_conversationrh  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : ConversationRHForm  
Fichiers vues lies : rh_messages(), rh_conversation_create(), rh_conversation_detail(), conversations_for_profile()  
Templates lies : templates/messages_rh/list.html, templates/messages_rh/detail.html  
Tests lies : test_hr_sees_all_conversations_employee_only_own  
Champs principaux : sujet, employe, responsable_rh, statut, date_creation, date_derniere_reponse  
Relations principales : Employe, UtilisateurProfile, MessageRH  
Fonction metier : fil de contact employe-RH.  
Validations : sujet minimum dans ConversationRHForm.  
Permissions : RH/Admin voient tout, employe voit ses conversations.  
Actions CRUD : creation conversation, detail, reponses.  
Traitements speciaux : notification RH/Admin ou employe apres message.

## Table / Modele : MessageRH

Table SQL probable : hr_messagerh  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : MessageRHForm  
Fichiers vues lies : rh_conversation_create(), rh_conversation_detail()  
Templates lies : templates/messages_rh/detail.html  
Champs principaux : conversation, expediteur, destinataire, contenu, date_envoi, lu  
Relations principales : ConversationRH, UtilisateurProfile  
Fonction metier : messages d'une conversation RH.  
Validations : contenu non vide dans formulaire et modele.  
Permissions : via conversation filtree.  
Actions CRUD : creation message.  
Traitements speciaux : date_derniere_reponse mise a jour.

## Table / Modele : Actualite

Table SQL probable : hr_actualite  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : ActualiteForm  
Fichiers vues lies : news_list(), news_create()  
Templates lies : templates/actualites/list.html  
Champs principaux : titre, contenu, auteur, audience, departement, role_cible, statut, date_publication, date_evenement, image  
Relations principales : UtilisateurProfile, Departement  
Fonction metier : actualites internes et evenements.  
Validations : titre/contenu obligatoires, evenement pas avant publication.  
Permissions : RH/Admin creent ; employes voient publiees.  
Actions CRUD : creation/publication, liste.  
Traitements speciaux : date_publication auto si statut publiee.

## Table / Modele : CategorieProduit

Table SQL probable : hr_categorieproduit  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : shop() via produits ; management commands seed  
Champs principaux : nom  
Relations principales : Produit  
Fonction metier : categorie de produits boutique.  
Validations : nom unique.  
Permissions : pas de vue CRUD dediee trouvee.  
Actions CRUD : seed/demo, admin Django non enregistre dans admin.py actuel.  
Traitements speciaux : classification boutique.

## Table / Modele : Produit

Table SQL probable : hr_produit  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : ProduitForm, CommandeProduitForm  
Fichiers vues lies : shop(), product_create()  
Services lies : approuver_commande(), refuser_ou_annuler_commande(), livrer_commande()  
Templates lies : templates/boutique/index.html  
Tests lies : shop_purchase_deducts_once_and_refund_possible  
Champs principaux : nom, categorie, description, image, cout_points, stock_disponible, actif  
Relations principales : CategorieProduit, CommandeProduit, AffectationMateriel  
Fonction metier : article de boutique materiel.  
Validations : type PositiveInteger pour cout/stock ; produit actif controle en commande.  
Permissions : creation ADMIN/RH.  
Actions CRUD : creation produit, liste boutique.  
Traitements speciaux : stock diminue/rembourse par services.

## Table / Modele : AffectationMateriel

Table SQL probable : hr_affectationmateriel  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers vues lies : shop() consultation, livrer_commande() creation  
Templates lies : templates/boutique/index.html  
Champs principaux : employe, produit, quantite, attribue_par, date_attribution, statut, commentaire  
Relations principales : Employe, Produit, UtilisateurProfile  
Fonction metier : materiel remis a un employe.  
Validations : quantite positive par champ PositiveIntegerField.  
Permissions : RH/Admin voient toutes les affectations, employe voit les siennes.  
Actions CRUD : creation automatique lors de livraison.  
Traitements speciaux : preuve de livraison materiel.

## Table / Modele : CommandeProduit

Table SQL probable : hr_commandeproduit  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : CommandeProduitForm  
Fichiers vues lies : shop(), order_process()  
Services lies : approuver_commande(), refuser_ou_annuler_commande(), livrer_commande()  
Templates lies : templates/boutique/index.html  
Tests lies : shop_purchase_deducts_once_and_refund_possible  
Champs principaux : employe, produit, quantite, cout_total_points, statut, date_commande, date_validation, valide_par, motif_refus, points_deduits  
Relations principales : Employe, Produit, UtilisateurProfile  
Fonction metier : commande boutique par points.  
Validations : quantite positive, produit actif, date_validation apres date_commande.  
Permissions : employe cree, RH/Admin traitent.  
Actions CRUD : creation en attente, approbation, refus/annulation, livraison.  
Traitements speciaux : deduction/remboursement points, stock, points_deduits.

## Table / Modele : Remuneration

Table SQL probable : hr_remuneration  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : RemunerationForm  
Fichiers vues lies : payroll_analytics(), salary_edit()  
Templates lies : templates/paie/analytics.html, templates/paie/form.html  
Tests lies : salary_and_position_permissions_protected  
Champs principaux : employe, salaire_base, prime, devise, date_effet, actif, cree_par  
Relations principales : Employe, UtilisateurProfile  
Fonction metier : salaire et primes.  
Validations : types Decimal ; pas de validation metier supplementaire trouvee.  
Permissions : analytics ADMIN/RH, modification ADMIN uniquement.  
Actions CRUD : modification salaire ; creation surtout seed/demo.  
Traitements speciaux : statistiques min/max/moyenne/mediane et filtres.

## Table / Modele : ReclamationRH

Table SQL probable : hr_reclamationrh  
App Django : hr  
Fichier modele : hr/models.py  
Fichiers formulaires lies : ReclamationRHForm, TraitementReclamationForm  
Fichiers vues lies : reclamations(), reclamation_create(), reclamation_process()  
Templates lies : templates/reclamations/list.html, templates/reclamations/table.html  
Tests lies : employee_sees_only_own_reclamations  
Champs principaux : employe, sujet, description, type_reclamation, statut, date_creation, date_traitement, traite_par, reponse_rh, points_accordes, action_points_appliquee  
Relations principales : Employe, UtilisateurProfile, AjustementPointsManuel  
Fonction metier : reclamations RH avec eventuelle compensation en points.  
Validations : sujet/description obligatoires ; points/reponse dans TraitementReclamationForm.  
Permissions : employe voit ses reclamations, RH/Admin voient et traitent tout.  
Actions CRUD : creation employe, traitement RH.  
Traitements speciaux : action_points_appliquee evite double ajout de points, notification, audit.

