# Traitements manquants ou a renforcer

| Module | Traitement attendu | Statut | Risque | Recommandation |
| --- | --- | --- | --- | --- |
| Employes | Matricule unique | OK | Aucun risque majeur | Garder `EmployeForm.clean_matricule()` |
| Employes | Email employe unique | OK | Aucun risque majeur | Garder `EmployeForm.clean_email()` |
| Employes | Date de naissance future | OK | Donnees incoherentes | Garder `EmployeForm.clean_date_naissance()` |
| Employes | Date d'embauche future | OK | Anciennete incoherente | Garder `EmployeForm.clean_date_embauche()` |
| Hierarchie | Interdire manager = soi-meme | OK | Boucle directe | Garder `Employe.clean()` et `GestionPosteForm.clean_responsable()` |
| Hierarchie | Interdire boucle hierarchique | OK | Arbre impossible a afficher | Garder `Employe.clean()` |
| Hierarchie | Mise a jour arbre automatique | OK | Organigramme obsolète | L'arbre est recalcule par `build_hierarchy_tree()` |
| Hierarchie | Notification apres changement de poste | OK | Employe non informe | Garder `position_edit()` |
| Hierarchie | Audit apres changement de poste | OK | Pas de trace | Garder `audit(..., CHANGEMENT_POSTE, ...)` |
| Conges | Date de debut dans le passe | OK | Demandes retroactives non controlees | Garder `DemandeCongeForm.clean()` et `DemandeConge.clean()` |
| Conges | Date de fin avant date de debut | OK | Duree negative | Garder validations formulaire + modele |
| Conges | Duree nulle | OK | Une meme date donne 1 jour | Aucun changement necessaire si duree inclusive voulue |
| Conges | Chevauchement de conges | OK | Deux conges actifs sur la meme periode | Garder requete overlap dans `DemandeCongeForm.clean()` |
| Conges | Verification du solde avant demande | OK | Demande impossible creee | Garder `DemandeCongeForm.clean()` |
| Conges | Deduction apres acceptation | OK | Solde non mis a jour | Garder `deduire_solde_conge()` |
| Conges | Absence de deduction apres refus | OK | Solde perdu a tort | `conge_refuse()` ne deduit pas |
| Conges | Remboursement apres annulation | OK | Solde perdu definitivement | Garder `conge_cancel()` et `rembourser_solde_conge()` |
| Conges | Impossibilite de solde negatif | OK | Solde negatif | Garder `SoldeConge.clean()` et verification service |
| Conges | Achat de jours avec points | MANQUANT | Le jury peut demander si cela existe | Ajouter un workflow dedie si souhaite |
| Conges | Validation modele date_traitement >= date_creation | PARTIEL | Date incoherente si manipulation hors vue | Ajouter `clean()` sur DemandeConge/DemandeAdministrative/ReclamationRH |
| Points | Transaction centralisee | OK | Calculs disperses | Garder `appliquer_transaction_points()` |
| Points | Interdire solde negatif | OK | Solde points negatif | Garder verification service + `ComptePoints.clean()` |
| Points | Historique des transactions | OK | Pas de tracabilite | Garder `TransactionPoints` |
| Points | Correction manuelle RH/Admin | OK | Employe s'ajoute des points | Garder `@role_required` sur `manual_points()` |
| Points | RH non admin ajuste ses propres points | OK | Auto-avantage RH | Garder controle dans `manual_points()` |
| Points | Interdiction double ajout formation | OK | Points doublonnes | Garder `points_attribues` |
| Points | Interdiction double ajout reclamation | OK | Compensation doublonnee | Garder `action_points_appliquee` |
| Points | Interdiction double deduction boutique | OK | Points deduits deux fois | Garder controle statut en_attente dans `approuver_commande()` |
| Pointage | Entree sans doublon | OK | Deux pointages jour meme | Garder `pointer_entree()` et contrainte unique |
| Pointage | Sortie impossible sans entree | OK | Sortie orpheline | Garder `pointer_sortie()` |
| Pointage | Sortie avant entree | OK | Total heures negatif | Garder `Pointage.clean()` et controle service |
| Pointage | Calcul total heures | OK | Presence non calculee | Garder `pointer_sortie()` |
| Pointage | Retard | OK | Penalite non appliquee | Garder `ParametrePointage` + `pointer_sortie()` |
| Pointage | Sortie anticipee | OK | Penalite non appliquee | Garder `pointer_sortie()` |
| Pointage | Bonus heures supplementaires | OK | Bonus non attribue | Garder `pointer_sortie()` |
| Pointage | Pointage incomplet | OK | Statut ambigu | Entree cree statut `incomplet` |
| Pointage | Consultation globale RH/Admin | OK | Acces trop large ou trop limite | Garder filtre `attendance_view()` |
| Boutique | Produit actif/inactif | OK | Commande produit inactif | Garder `CommandeProduitForm.__init__()` et `CommandeProduit.clean()` |
| Boutique | Stock disponible | OK | Commande impossible | Garder `CommandeProduitForm.clean()` et `approuver_commande()` |
| Boutique | Stock jamais negatif | OK | Stock negatif | Garder verification avant deduction |
| Boutique | Solde points suffisant | OK | Achat sans points | Garder formulaire + transaction points |
| Boutique | Commande en attente | OK | Workflow saute | Creation dans `shop()` avec statut par defaut |
| Boutique | Approbation | OK | Pas de deduction stock/points | Garder `approuver_commande()` |
| Boutique | Refus/annulation | OK | Pas de remboursement | Garder `refuser_ou_annuler_commande()` |
| Boutique | Livraison | OK | Livraison non tracee | Garder `livrer_commande()` |
| Boutique | Date livraison avant commande | PARTIEL | Date incoherente si hors vue | Appeler `full_clean()` dans `livrer_commande()` |
| Boutique | Affectation directe par RH/Admin | PARTIEL | Pas d'ecran direct hors livraison | Ajouter vue d'affectation directe si besoin |
| Formations | Creation formation | OK | Catalogue incomplet | Garder `formation_create()` |
| Formations | Affectation a employe | OK | Formation non assignee | Garder `AffectationFormationForm` |
| Formations | Affectation a departement | OK | Cible groupe impossible | Garder `formations_admin()` |
| Formations | Statut formation | OK | Suivi absent | Garder `training_status()` et `formation_assignment_status()` |
| Formations | Points apres completion | OK | Recompense absente | Garder `points_attribues` |
| Formations | Date limite invalide | OK | Deadline incoherente | Garder validations formulaire/modele |
| Formations | Journal/logs | PARTIEL | Le template affiche les affectations, audit incomplet creation | Ajouter audit dans `formation_create()` |
| Reclamations | Creation par employe | OK | Auteur falsifie | `reclamation_create()` utilise profil connecte |
| Reclamations | Employe voit ses reclamations | OK | Fuite donnees | Garder filtre `reclamations()` |
| Reclamations | RH/Admin voit tout | OK | Traitement impossible | Garder filtre par role |
| Reclamations | Reponse RH obligatoire | OK | Traitement sans explication | Garder `TraitementReclamationForm.clean()` |
| Reclamations | Acceptation avec points | OK | Compensation impossible | Garder `reclamation_process()` |
| Reclamations | Points pas deux fois | OK | Double compensation | Garder `action_points_appliquee` |
| Reclamations | Notification apres traitement | OK | Employe non informe | Garder `notify_employee()` |
| Reclamations | Audit apres traitement | OK | Pas de trace | Garder `audit(... TRAITEMENT_RECLAMATION ...)` |
| Messages RH | Creation conversation | OK | Contact RH impossible | Garder `rh_conversation_create()` |
| Messages RH | Message vide interdit | OK | Conversations polluees | Garder `MessageRHForm.clean_contenu()` et `MessageRH.clean()` |
| Messages RH | Employe voit ses conversations | OK | Fuite donnees | Garder `conversations_for_profile()` |
| Messages RH | RH/Admin voit toutes | OK | Support RH limite | Garder `conversations_for_profile()` |
| Messages RH | Statut lu/non lu | PARTIEL | Messages non lus pas vraiment exploites | Ajouter marquage `lu=True` dans detail |
| Messages RH | Cloture conversation | MANQUANT | Conversation impossible a fermer via UI | Ajouter vue `conversation_close()` |
| Messages RH | Notification apres reponse | OK | Destinataire non informe | Garder `rh_conversation_detail()` |
| Paie | Consultation salaire | OK | Acces non controle | Garder `payroll_analytics()` ADMIN/RH |
| Paie | Modification salaire | OK | Modification non autorisee | Garder `salary_edit()` ADMIN |
| Paie | Employe interdit | OK | Fuite salaire | Test existant et role_required |
| Paie | Stats min/max/moyenne/mediane | OK | Analyse incomplete | Garder aggregations |
| Paie | Filtre departement/poste | PARTIEL | Poste calcule mais filtre poste non expose | Ajouter filtre poste si demande |
| Paie | Audit apres modification salaire | OK | Pas de trace modification | Garder audit salaire |
| Documents | Upload document | OK | Document absent | Garder `document_upload()` |
| Documents | Extension autorisee | OK | Upload dangereux | Garder FileExtensionValidator |
| Documents | Taille fichier | OK | Fichier trop lourd | Garder `MAX_UPLOAD_SIZE` |
| Documents | Employe voit ses documents | OK | Fuite document | Garder `accessible_documents()` |
| Documents | RH/Admin voit documents autorises | OK | Gestion impossible | Garder `accessible_documents()` |
| Documents | Suppression document | OK | Fichier non supprimable | Garder `document_delete()` |
| Documents | Archivage document | MANQUANT | Suppression definitive sans archivage | Ajouter champ `archive` si necessaire |
| Documents | Securite telechargement | OK | Acces par URL directe | Garder controle dans `document_download()` |
| Notifications | Creation individuelle | OK | Aucun suivi utilisateur | Garder `notify()` |
| Notifications | Creation groupe/role | OK | RH/Admin non notifies | Garder `notify_role()` |
| Notifications | Non lue | OK | Etat absent | Champ `lue=False` par defaut |
| Notifications | Marquer comme lu | OK | Compteur incorrect | Garder `notification_read()` |
| Notifications | Marquer tout comme lu | OK | Trop d'actions manuelles | Garder `notifications_read_all()` |
| Notifications | Employe voit seulement les siennes | OK | Fuite notifications | Garder `user_profile.notifications` |
| Notifications | Historique livraison | PARTIEL | Pas de statut livraison detaille | Ajouter table de livraison si besoin avance |
| Permissions | Pages employes protegees | OK | Acces anonyme | `login_required` et `can_view_employees()` |
| Permissions | Pages RH/Admin protegees | OK | Acces employe | `role_required()` |
| Permissions | Protection URL directe | OK | Contournement template | Decorateurs et filtres queryset |
| Permissions | Protection template | OK | Boutons visibles a tort | Conditions dans templates |
| Audit | Creation historique action | OK | Pas de trace | `audit()` et `audit_profile()` |
| Audit | Filtres historique | OK | Recherche difficile | `audit_history()` |
| Audit | Toutes actions importantes loggees | PARTIEL | Quelques creations non journalisees | Ajouter audit a `formation_create()` et `product_create()` |

