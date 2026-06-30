# Carte des traitements logiques de l'application RH

Ce document sert a repondre a la question: "Ou est traitee telle regle metier dans le code ?".  
Les traitements sont classes par module, avec les fichiers, classes/fonctions et une phrase simple pour la soutenance.

## Traitement : Validation des informations employe

Module : Employes  
Table : Employe  
Objectif : Refuser les matricules/emails en doublon, noms invalides, telephone invalide et dates futures.  
Scenarios impossibles traites : nom trop court, nom avec chiffres, email deja utilise, date de naissance future, date d'embauche future.  
Fichier : hr/forms.py  
Dossier : hr  
Classe/Fonction : EmployeForm.clean_matricule(), clean_nom(), clean_prenom(), clean_email(), clean_telephone(), clean_date_naissance(), clean_date_embauche()  
Type : validation formulaire  
Explication simple : Le formulaire nettoie les champs avant sauvegarde et ajoute des ValidationError si les donnees ne respectent pas les regles.  
Comment l'expliquer au jury : "Les donnees saisies pour un employe sont validees cote backend dans EmployeForm avant d'etre enregistrees."

## Traitement : Hierarchie impossible entre employes

Module : Employes / Hierarchie  
Table : Employe  
Objectif : Eviter qu'un employe soit son propre responsable ou qu'une boucle hierarchique soit creee.  
Scenarios impossibles traites : responsable = soi-meme, A responsable de B puis B responsable de A.  
Fichier : hr/models.py ; hr/forms.py  
Dossier : hr  
Classe/Fonction : Employe.clean(), GestionPosteForm.clean_responsable(), GestionPosteForm.clean()  
Type : validation modele + validation formulaire  
Explication simple : Le modele remonte la chaine des responsables et leve une ValidationError si l'employe reapparait dans sa propre hierarchie.  
Comment l'expliquer au jury : "La protection est dans le modele Employe, donc elle s'applique meme si on contourne le formulaire."

## Traitement : Affichage de l'arbre hierarchique

Module : Employes / Hierarchie  
Table : Employe, Poste, Departement, Service  
Objectif : Construire un arbre lisible selon responsable direct, rang hierarchique, poste et filtres.  
Scenarios impossibles traites : boucle pendant le rendu de l'arbre, affichage non structure.  
Fichier : hr/services.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : build_hierarchy_tree(), hierarchy_tree()  
Type : logique service + controle vue  
Explication simple : Le service charge les employes actifs, regroupe les enfants par responsable, ajoute les responsables visibles et construit les noeuds.  
Comment l'expliquer au jury : "L'arbre est genere dynamiquement depuis la relation Employe.responsable, pas dessine manuellement."

## Traitement : Gestion des postes et affectations

Module : Employes / Postes  
Table : Employe, Poste, Departement, Service  
Objectif : Permettre aux RH/Admin de changer poste, departement, service et responsable.  
Scenarios impossibles traites : employe RH non admin qui modifie sa propre affectation, boucle hierarchique via formulaire.  
Fichier : hr/views.py ; hr/forms.py  
Dossier : hr  
Classe/Fonction : position_management(), position_edit(), GestionPosteForm  
Type : controle vue + permission + validation formulaire  
Explication simple : La vue est protegee par role_required, puis le formulaire valide la hierarchie avant sauvegarde.  
Comment l'expliquer au jury : "Le changement de poste est reserve aux RH/Admin, valide par formulaire, notifie a l'employe et journalise."

## Traitement : Validation des dates de conge

Module : Conges et absences  
Table : DemandeConge  
Objectif : Refuser les conges dans le passe et les dates de fin avant les dates de debut.  
Scenarios impossibles traites : date_debut < aujourd'hui, date_fin < date_debut.  
Fichier : hr/forms.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : DemandeCongeForm.clean(), DemandeConge.clean()  
Type : validation formulaire + validation modele  
Explication simple : Le formulaire verifie les dates a la soumission, et le modele garde une deuxieme protection de coherence.  
Comment l'expliquer au jury : "Les dates de conge sont controlees cote serveur, dans le formulaire et dans le modele."

## Traitement : Duree nulle ou negative de conge

Module : Conges et absences  
Table : DemandeConge  
Objectif : Eviter une duree negative ; une duree nulle exacte n'existe pas avec des dates inclusives identiques.  
Scenarios impossibles traites : date_fin avant date_debut produit une duree negative.  
Fichier : hr/forms.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : DemandeCongeForm.clean(), DemandeConge.clean(), DemandeConge.duree_jours  
Type : validation formulaire + validation modele  
Explication simple : La duree est calculee par difference de dates + 1. Si fin < debut, la demande est refusee.  
Comment l'expliquer au jury : "Une date de debut egale a la date de fin donne 1 jour ; une duree negative est bloquee."

## Traitement : Solde de conges insuffisant

Module : Conges et absences  
Table : SoldeConge, DemandeConge  
Objectif : Empecher une demande ou validation depassant les jours disponibles.  
Scenarios impossibles traites : demander 5 jours avec un solde de 3 jours, valider une demande devenue impossible.  
Fichier : hr/forms.py ; hr/services.py  
Dossier : hr  
Classe/Fonction : DemandeCongeForm.clean(), deduire_solde_conge()  
Type : validation formulaire + logique service  
Explication simple : Le formulaire informe l'utilisateur avant creation ; le service reverifie au moment de la validation avec verrouillage select_for_update.  
Comment l'expliquer au jury : "Je controle le solde a deux niveaux: a la demande et juste avant la deduction effective."

## Traitement : Chevauchement de conges

Module : Conges et absences  
Table : DemandeConge  
Objectif : Empecher deux demandes actives sur la meme periode.  
Scenarios impossibles traites : demande du 10 au 12 alors qu'une demande du 11 au 14 est deja active.  
Fichier : hr/forms.py  
Dossier : hr  
Classe/Fonction : DemandeCongeForm.clean()  
Type : validation formulaire  
Explication simple : Le formulaire cherche les demandes du meme employe dont les dates se croisent, sauf refusees ou cloturees.  
Comment l'expliquer au jury : "Le chevauchement est detecte avec date_debut <= fin et date_fin >= debut."

## Traitement : Validation/refus d'un conge

Module : Conges et absences  
Table : DemandeConge, SoldeConge, MouvementSoldeConge  
Objectif : Seuls les acteurs autorises traitent une demande en attente ; validation deduit le solde, refus ne deduit rien.  
Scenarios impossibles traites : traitement par un employe non autorise, double traitement d'une demande.  
Fichier : hr/views.py ; hr/services.py  
Dossier : hr  
Classe/Fonction : can_process_conge(), conge_validate(), conge_refuse(), deduire_solde_conge()  
Type : permission + controle vue + logique service  
Explication simple : La vue verifie le role et le statut EN_ATTENTE, puis le service deduit le solde uniquement en validation.  
Comment l'expliquer au jury : "Le refus change seulement le statut ; la deduction est appelee uniquement dans conge_validate."

## Traitement : Annulation d'un conge et remboursement

Module : Conges et absences  
Table : DemandeConge, SoldeConge, MouvementSoldeConge  
Objectif : Permettre a l'employe d'annuler ses demandes en attente ou validees, avec remboursement si deja validee.  
Scenarios impossibles traites : annuler la demande d'un autre employe, annuler un statut non autorise.  
Fichier : hr/views.py ; hr/services.py  
Dossier : hr  
Classe/Fonction : conge_cancel(), rembourser_solde_conge()  
Type : controle vue + logique service  
Explication simple : La vue verifie que la demande appartient a l'utilisateur, puis rembourse seulement si l'ancien statut etait VALIDEE.  
Comment l'expliquer au jury : "L'annulation d'un conge valide recree un mouvement de solde inverse."

## Traitement : Creation et non-negativite du solde de conges

Module : Conges et absences  
Table : SoldeConge  
Objectif : Creer un solde par defaut si absent et interdire les valeurs negatives.  
Scenarios impossibles traites : solde disponible negatif, jours utilises negatifs.  
Fichier : hr/models.py ; hr/services.py ; core/views.py  
Dossier : hr, core  
Classe/Fonction : SoldeConge.clean(), deduire_solde_conge(), rembourser_solde_conge(), dashboard()  
Type : validation modele + logique service  
Explication simple : get_or_create cree le solde au besoin ; full_clean verifie les nombres.  
Comment l'expliquer au jury : "Le solde est protege dans le modele et manipule dans des services transactionnels."

## Traitement : Historique des mouvements de solde

Module : Conges et absences  
Table : MouvementSoldeConge  
Objectif : Garder trace de chaque deduction ou remboursement de jours.  
Scenarios impossibles traites : perte de trace du solde avant/apres une action.  
Fichier : hr/services.py  
Dossier : hr  
Classe/Fonction : deduire_solde_conge(), rembourser_solde_conge()  
Type : logique service + audit  
Explication simple : Chaque mouvement stocke type, jours, solde_avant, solde_apres, demande et auteur.  
Comment l'expliquer au jury : "Je peux expliquer l'evolution du solde grace a MouvementSoldeConge."

## Traitement : Transaction de points centralisee

Module : Points  
Table : ComptePoints, TransactionPoints  
Objectif : Centraliser gains, deductions, achats, remboursements et corrections.  
Scenarios impossibles traites : mouvement a zero point, employe absent, solde final negatif.  
Fichier : hr/services.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : appliquer_transaction_points(), ComptePoints.clean()  
Type : logique service + validation modele  
Explication simple : Le service verrouille le compte, calcule solde_avant/solde_apres, refuse le negatif et cree l'historique.  
Comment l'expliquer au jury : "Toutes les operations de points passent par appliquer_transaction_points."

## Traitement : Correction manuelle des points

Module : Points  
Table : AjustementPointsManuel, ComptePoints, TransactionPoints  
Objectif : Autoriser uniquement RH/Admin a corriger les points avec motif.  
Scenarios impossibles traites : employe qui accede a la page, RH qui ajuste ses propres points sauf admin, motif vide.  
Fichier : hr/views.py ; hr/forms.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : manual_points(), AjustementPointsManuelForm, AjustementPointsManuel.clean()  
Type : permission + validation modele + controle vue  
Explication simple : role_required bloque l'acces, la vue refuse l'auto-ajustement RH, le modele impose nombre positif et motif.  
Comment l'expliquer au jury : "Un employe ne peut pas s'ajouter des points ; la page est protegee par role."

## Traitement : Points apres pointage

Module : Pointage / Points  
Table : Pointage, ParametrePointage, TransactionPoints  
Objectif : Calculer les points de presence selon retard, sortie anticipee ou heures supplementaires.  
Scenarios impossibles traites : sortie sans entree, sortie avant entree, double pointage du jour.  
Fichier : hr/services.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : pointer_entree(), pointer_sortie(), Pointage.clean()  
Type : logique service + validation modele  
Explication simple : Le service calcule les heures, applique bonus/penalites depuis ParametrePointage, puis cree une transaction de points.  
Comment l'expliquer au jury : "Le pointage ne se contente pas d'enregistrer l'heure ; il calcule aussi les points."

## Traitement : Double pointage dans la meme journee

Module : Pointage / Presence  
Table : Pointage  
Objectif : Empecher deux entrees pour le meme employe le meme jour.  
Scenarios impossibles traites : pointer deux fois l'entree aujourd'hui.  
Fichier : hr/services.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : pointer_entree(), Pointage.Meta.constraints  
Type : logique service + contrainte modele/base  
Explication simple : Le service cherche un pointage existant, et la contrainte unique employe/date protege aussi la base.  
Comment l'expliquer au jury : "La regle est controlee dans le service et renforcee par une contrainte unique."

## Traitement : Consultation du pointage

Module : Pointage / Presence  
Table : Pointage, ComptePoints  
Objectif : Filtrer l'affichage selon le role.  
Scenarios impossibles traites : employe qui consulte les pointages de toute l'entreprise.  
Fichier : hr/views.py  
Dossier : hr  
Classe/Fonction : attendance_view()  
Type : permission + controle vue  
Explication simple : RH/Admin voient tout, manager voit lui-meme et son equipe, employe voit uniquement ses lignes.  
Comment l'expliquer au jury : "Les donnees de presence sont filtrees dans la vue avant le rendu."

## Traitement : Boutique - commande employee

Module : Boutique / Materiel  
Table : Produit, CommandeProduit, ComptePoints  
Objectif : Verifier produit actif, stock suffisant et points suffisants avant de creer une commande.  
Scenarios impossibles traites : commande d'un produit inactif, quantite <= 0, stock insuffisant, points insuffisants.  
Fichier : hr/forms.py ; hr/models.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : CommandeProduitForm.__init__(), clean_quantite(), clean(), CommandeProduit.clean(), shop()  
Type : validation formulaire + validation modele + controle vue  
Explication simple : Le formulaire ne propose que les produits actifs en stock et revérifie la quantite et le solde.  
Comment l'expliquer au jury : "La commande est creee en attente seulement apres validation stock et points."

## Traitement : Boutique - approbation, stock et deduction

Module : Boutique / Materiel  
Table : CommandeProduit, Produit, TransactionPoints  
Objectif : Deduir les points et le stock une seule fois a l'approbation.  
Scenarios impossibles traites : approbation d'une commande deja traitee, stock negatif, solde de points negatif.  
Fichier : hr/services.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : approuver_commande(), order_process()  
Type : logique service + controle vue  
Explication simple : Le service verrouille la commande, verifie statut en_attente et stock, appelle la transaction de points puis diminue le stock.  
Comment l'expliquer au jury : "La deduction des points et du stock se fait dans une transaction atomique."

## Traitement : Boutique - refus, annulation et remboursement

Module : Boutique / Materiel  
Table : CommandeProduit, Produit, TransactionPoints  
Objectif : Rembourser points et stock si une commande deja deduite est refusee ou annulee.  
Scenarios impossibles traites : remboursement sans deduction precedente, statut invalide.  
Fichier : hr/services.py  
Dossier : hr  
Classe/Fonction : refuser_ou_annuler_commande()  
Type : logique service  
Explication simple : Si points_deduits vaut True, le service cree une transaction de remboursement et remet le stock.  
Comment l'expliquer au jury : "Le booléen points_deduits evite de rembourser deux fois."

## Traitement : Boutique - livraison et affectation materiel

Module : Boutique / Materiel  
Table : CommandeProduit, AffectationMateriel  
Objectif : Livrer uniquement une commande approuvee et creer l'affectation materiel.  
Scenarios impossibles traites : livraison d'une commande en attente/refusee.  
Fichier : hr/services.py  
Dossier : hr  
Classe/Fonction : livrer_commande()  
Type : logique service  
Explication simple : La livraison change le statut et cree une ligne AffectationMateriel.  
Comment l'expliquer au jury : "La table AffectationMateriel prouve quel materiel a ete remis a quel employe."

## Traitement : Formations - creation et affectation

Module : Formations  
Table : Formation, AffectationFormation  
Objectif : Creer des formations et les affecter a des employes ou a tout un departement.  
Scenarios impossibles traites : affectation sans employe ni departement, doublon de formation active pour le meme employe.  
Fichier : hr/forms.py ; hr/models.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : FormationForm.clean_titre(), AffectationFormationForm.clean(), AffectationFormation.Meta.constraints, formations_admin()  
Type : validation formulaire + contrainte modele + controle vue  
Explication simple : Le formulaire impose une cible ; la contrainte unique evite deux affectations actives identiques.  
Comment l'expliquer au jury : "L'affectation peut etre individuelle ou par departement, avec controle de doublon."

## Traitement : Dates de formation

Module : Formations  
Table : AffectationFormation  
Objectif : Controler date limite et date completion.  
Scenarios impossibles traites : date limite dans le passe, date limite avant affectation, completion avant affectation.  
Fichier : hr/forms.py ; hr/models.py  
Dossier : hr  
Classe/Fonction : AffectationFormationForm.clean_date_limite(), AffectationFormation.clean()  
Type : validation formulaire + validation modele  
Explication simple : Le formulaire controle le passe ; le modele controle la coherence entre dates.  
Comment l'expliquer au jury : "Les dates de formation sont protegees a deux niveaux."

## Traitement : Formation terminee et points uniques

Module : Formations / Points  
Table : AffectationFormation, Formation, TransactionPoints  
Objectif : Ajouter les points de recompense une seule fois lorsque la formation est terminee.  
Scenarios impossibles traites : double attribution apres plusieurs clics sur "Terminer".  
Fichier : hr/views.py  
Dossier : hr  
Classe/Fonction : training_status(), formation_assignment_status()  
Type : controle vue + logique points  
Explication simple : La vue verifie points_attribues avant d'appeler appliquer_transaction_points, puis met points_attribues a True.  
Comment l'expliquer au jury : "Le champ points_attribues est le verrou fonctionnel contre le double gain."

## Traitement : Reclamation employee

Module : Reclamations RH  
Table : ReclamationRH  
Objectif : Permettre a un employe de creer une reclamation avec sujet, description et type.  
Scenarios impossibles traites : sujet/description vides.  
Fichier : hr/forms.py ; hr/models.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : ReclamationRHForm, ReclamationRH.clean(), reclamation_create()  
Type : validation modele + controle vue  
Explication simple : La vue rattache automatiquement la reclamation a l'employe connecte et notifie RH/Admin.  
Comment l'expliquer au jury : "L'employe ne choisit pas l'auteur de la reclamation ; le backend utilise son profil."

## Traitement : Visibilite des reclamations

Module : Reclamations RH  
Table : ReclamationRH  
Objectif : RH/Admin voient tout, employe voit seulement ses reclamations.  
Scenarios impossibles traites : employe qui consulte les reclamations d'un autre.  
Fichier : hr/views.py  
Dossier : hr  
Classe/Fonction : reclamations()  
Type : permission + controle vue  
Explication simple : La queryset est filtree par employe sauf pour ADMIN/RESPONSABLE_RH.  
Comment l'expliquer au jury : "La restriction se fait avant l'envoi des donnees au template."

## Traitement : Traitement RH d'une reclamation

Module : Reclamations RH / Points  
Table : ReclamationRH, TransactionPoints  
Objectif : Repondre, accepter, refuser, demander infos, cloturer, ou accorder des points.  
Scenarios impossibles traites : attribution de points sans nombre positif, reponse RH vide, double ajout de points.  
Fichier : hr/forms.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : TraitementReclamationForm.clean(), reclamation_process()  
Type : validation formulaire + permission + controle vue  
Explication simple : La vue est RH/Admin, met le statut, enregistre la reponse, et ajoute les points seulement si action_points_appliquee est False.  
Comment l'expliquer au jury : "Une reclamation acceptee avec points ne peut pas creditrer deux fois le compte."

## Traitement : Messages RH

Module : Messages RH  
Table : ConversationRH, MessageRH  
Objectif : Creer des conversations, envoyer des messages et filtrer l'acces.  
Scenarios impossibles traites : message vide, employe qui voit une conversation d'un autre.  
Fichier : hr/forms.py ; hr/models.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : ConversationRHForm.clean_sujet(), MessageRHForm.clean_contenu(), MessageRH.clean(), conversations_for_profile(), rh_conversation_detail()  
Type : validation formulaire + validation modele + permission  
Explication simple : Les conversations sont filtrees par role, et les messages vides sont refuses.  
Comment l'expliquer au jury : "Le message est controle dans le formulaire et aussi dans le modele."

## Traitement : Demandes administratives

Module : Demandes administratives  
Table : DemandeAdministrative, Document  
Objectif : Creer une demande, ajouter une piece jointe, traiter par RH/Admin.  
Scenarios impossibles traites : type trop court, description trop courte, retraitement d'une demande finalisee, statut invalide.  
Fichier : hr/forms.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : DemandeAdministrativeForm, demandes_for_profile(), demande_submit(), demande_process()  
Type : validation formulaire + permission + controle vue  
Explication simple : L'employe cree, RH/Admin traitent, la vue bloque une demande deja validee/refusee/cloturee.  
Comment l'expliquer au jury : "Le workflow administratif est protege contre le double traitement."

## Traitement : Documents - upload et securite

Module : Documents  
Table : Document  
Objectif : Controler les extensions, la taille et l'acces aux documents.  
Scenarios impossibles traites : fichier exe, fichier > 5 Mo, telechargement URL directe non autorise, suppression par utilisateur non autorise.  
Fichier : hr/views.py  
Dossier : hr  
Classe/Fonction : validate_uploaded_file(), create_document(), accessible_documents(), document_upload(), document_download(), document_delete()  
Type : controle vue + securite fichier + permission  
Explication simple : Les extensions autorisees sont pdf/doc/docx/jpg/jpeg/png, la taille max est 5 Mo, et les telechargements passent par accessible_documents.  
Comment l'expliquer au jury : "La securite document est cote backend, pas seulement dans l'interface."

## Traitement : Notifications

Module : Notifications  
Table : Notification  
Objectif : Creer des notifications individuelles ou par role, lister celles de l'utilisateur, marquer lu/tout lu.  
Scenarios impossibles traites : marquer comme lue une notification d'un autre utilisateur.  
Fichier : hr/services.py ; hr/views.py ; accounts/context_processors.py  
Dossier : hr, accounts  
Classe/Fonction : notify(), notify_employee(), notify_role(), notify_rh_and_admin(), notifications_list(), notification_read(), notifications_read_all(), current_profile()  
Type : logique service + controle vue  
Explication simple : Les notifications appartiennent a UtilisateurProfile ; la lecture d'une notification filtre par destinataire.  
Comment l'expliquer au jury : "Chaque utilisateur ne charge que ses propres notifications."

## Traitement : Paie et salaire

Module : Paie  
Table : Remuneration  
Objectif : Afficher statistiques salariales et autoriser la modification uniquement a ADMIN.  
Scenarios impossibles traites : employe accedant aux statistiques, RH non admin modifiant un salaire.  
Fichier : hr/views.py ; hr/forms.py  
Dossier : hr  
Classe/Fonction : payroll_analytics(), salary_edit(), RemunerationForm  
Type : permission + controle vue  
Explication simple : role_required limite les statistiques a ADMIN/RH et la modification a ADMIN. Les stats calculent min, max, moyenne, mediane, par departement et par poste.  
Comment l'expliquer au jury : "La paie est un module sensible, donc l'acces est strictement protege par decorateurs."

## Traitement : Actualites / newsletter

Module : Actualites  
Table : Actualite  
Objectif : Publier des actualites internes selon statut, audience et dates.  
Scenarios impossibles traites : titre ou contenu vide, date evenement avant publication.  
Fichier : hr/models.py ; hr/views.py  
Dossier : hr  
Classe/Fonction : Actualite.clean(), news_list(), news_create()  
Type : validation modele + permission  
Explication simple : Les employes voient les actualites publiees ; RH/Admin peuvent voir toutes les actualites et publier.  
Comment l'expliquer au jury : "La cohérence de publication est dans le modele Actualite."

## Traitement : Permissions par role

Module : Securite / Permissions  
Table : UtilisateurProfile  
Objectif : Controler les pages selon ADMIN, RESPONSABLE_RH, RESPONSABLE_HIERARCHIQUE, EMPLOYE.  
Scenarios impossibles traites : acces URL directe aux pages RH/Admin, employe sur correction points, employe sur paie.  
Fichier : hr/permissions.py ; hr/views.py ; templates/base.html  
Dossier : hr, templates  
Classe/Fonction : role_required(), can_manage_hr(), can_view_employees(), decorateurs @role_required, conditions templates  
Type : permission  
Explication simple : Le decorateur role_required bloque la vue meme si l'utilisateur tape l'URL.  
Comment l'expliquer au jury : "Les templates cachent des boutons, mais la vraie securite est dans les vues."

## Traitement : Audit / historique

Module : Audit  
Table : HistoriqueAction  
Objectif : Tracer les actions importantes avec utilisateur, role, module, objet, date et details.  
Scenarios impossibles traites : action critique sans trace lisible.  
Fichier : hr/services.py ; hr/views.py ; templates/audit/list.html  
Dossier : hr, templates  
Classe/Fonction : audit(), audit_profile(), audit_history()  
Type : logique service + controle vue  
Explication simple : Les services auditent les changements de poste, conges, points, commandes, documents, salaires, formations, reclamations.  
Comment l'expliquer au jury : "L'historique est centralise dans HistoriqueAction et consultable avec filtres."

## Traitement : Authentification et profil actif

Module : Comptes  
Table : UtilisateurProfile, User  
Objectif : Connecter seulement les utilisateurs valides avec profil actif.  
Scenarios impossibles traites : connexion avec profil desactive.  
Fichier : accounts/views.py  
Dossier : accounts  
Classe/Fonction : login_view()  
Type : controle vue  
Explication simple : authenticate verifie le mot de passe, puis la vue controle profile.actif avant login.  
Comment l'expliquer au jury : "Un compte desactive ne peut pas ouvrir une session."

## Traitement : Tableau de bord

Module : Dashboard  
Table : Employe, DemandeConge, DemandeAdministrative, Pointage, SoldeConge, ComptePoints, Formation, CommandeProduit, ConversationRH, Remuneration  
Objectif : Calculer les indicateurs RH et individuels.  
Scenarios impossibles traites : division par zero dans taux de traitement.  
Fichier : core/views.py  
Dossier : core  
Classe/Fonction : dashboard()  
Type : controle vue + statistiques  
Explication simple : La vue agrège les demandes, presences, retards, notifications, formations et soldes.  
Comment l'expliquer au jury : "Le dashboard consomme les tables principales et calcule des indicateurs de synthese."

## Traitements obligatoires absents ou partiels

### STATUT : MANQUANT — Achat de jours de conges avec points
Risque : Le jury peut demander si les points peuvent acheter des jours de conge ; aucun workflow dedie n'existe.  
Ou regarder : aucun traitement trouve dans hr/views.py, hr/forms.py, hr/services.py.

### STATUT : PARTIEL — Date de traitement avant date de creation
Risque : Les vues utilisent timezone.now() au traitement, donc c'est correct en pratique, mais il n'existe pas de validation modele generale qui interdit date_traitement < date_creation.  
Ou regarder : DemandeConge, DemandeAdministrative, ReclamationRH.

### STATUT : PARTIEL — Livraison avant commande
Risque : CommandeProduit.clean() verifie date_validation < date_commande, mais livrer_commande() ne fait pas full_clean() avant save.  
Ou regarder : hr/models.py CommandeProduit.clean(), hr/services.py livrer_commande().

### STATUT : PARTIEL — Double deduction de commande
Risque : approuver_commande bloque statut != en_attente, ce qui evite l'approbation double. La protection repose surtout sur le statut.  
Ou regarder : hr/services.py approuver_commande().

### STATUT : MANQUANT — Cloture formelle des conversations RH
Risque : Le modele a un statut cloturee, mais aucune vue dediee de cloture n'a ete trouvee.  
Ou regarder : ConversationRH.STATUTS, hr/views.py.

### STATUT : PARTIEL — Statut lu/non lu des messages RH
Risque : MessageRH.lu existe, mais aucune action de marquage lu claire n'a ete trouvee.  
Ou regarder : MessageRH.lu, rh_conversation_detail().

### STATUT : PARTIEL — Archivage document
Risque : Suppression physique disponible, mais pas d'archivage logique.  
Ou regarder : document_delete().

### STATUT : PARTIEL — Audit de certaines actions
Risque : Plusieurs actions sont auditees, mais la creation produit ou creation formation simple ne journalise pas toujours.  
Ou regarder : formation_create(), product_create().

