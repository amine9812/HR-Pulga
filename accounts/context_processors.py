def current_profile(request):
    profile = None
    notifications_non_lues = 0
    nav_module = ""
    nav_item = ""
    active_tab = ""
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile:
            notifications_non_lues = profile.notifications.filter(lue=False).count()
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else ""
    employe_urls = {
        "employes_list": "employes_list",
        "employe_create": "employes_list",
        "employe_detail": "employes_list",
        "employe_update": "employes_list",
        "hierarchy_tree": "hierarchy_tree",
        "position_management": "position_management",
        "position_edit": "position_management",
        "formations_admin": "formations_admin",
        "formation_create": "formations_admin",
        "formation_assignment_status": "formations_admin",
        "payroll_analytics": "payroll_analytics",
        "salary_edit": "payroll_analytics",
        "my_trainings": "my_trainings",
        "training_status": "my_trainings",
    }
    departement_urls = {
        "departements_list",
        "departement_create",
        "departement_update",
        "departement_save",
        "service_save",
        "poste_save",
        "departement_delete",
        "service_delete",
        "poste_delete",
    }
    task_urls = {"team_tasks", "task_create", "task_status"}
    planning_urls = {
        "planning",
        "planning_create",
        "planning_status",
        "planning_api_shifts",
        "planning_api_shift_detail",
        "planning_api_move",
        "planning_api_resize",
        "planning_api_bulk",
        "planning_api_copy",
        "planning_api_conflicts",
        "planning_api_summary",
        "planning_api_available_employees",
        "planning_api_assistant",
    }
    rh_ticket_urls = {
        "rh_messages",
        "rh_conversation_create",
        "rh_conversation_detail",
        "rh_conversation_close",
        "rh_conversation_accept",
        "rh_conversation_rename",
        "rh_conversation_participant",
        "rh_conversation_rate",
        "rh_message_attachment",
        "rh_support_rewards_generate",
        "rh_support_reward_decision",
    }
    admin_urls = {"admin_dashboard", "admin_account_request_decision", "admin_user_update", "admin_settings_save", "audit_history"}
    if url_name in employe_urls:
        nav_module = "employes"
        nav_item = employe_urls[url_name]
    elif url_name in departement_urls:
        nav_module = "departements"
        active_tab = request.GET.get("tab", "departements")
        nav_item = f"departements_{active_tab if active_tab in {'departements', 'services', 'postes'} else 'departements'}"
    elif url_name in task_urls:
        nav_module = "team_tasks"
        active_tab = request.GET.get("tab", "overview")
        allowed_task_tabs = {"overview", "create", "open", "mine", "team", "approval", "points", "archive"}
        manager_task_tabs = {"create", "team", "approval", "points"}
        if active_tab in manager_task_tabs and (not profile or profile.role not in {"ADMIN", "RESPONSABLE_RH", "RESPONSABLE_HIERARCHIQUE"}):
            active_tab = "overview"
        nav_item = f"team_tasks_{active_tab if active_tab in allowed_task_tabs else 'overview'}"
    elif url_name in planning_urls:
        nav_module = "planning"
        active_tab = request.GET.get("tab", "overview")
        allowed_planning_tabs = {"overview", "calendar", "daily", "weekly", "biweekly", "monthly", "timesheets", "shifts", "attendance", "leave", "tasks", "approvals", "reports", "settings"}
        nav_item = f"planning_{active_tab if active_tab in allowed_planning_tabs else 'overview'}"
    elif url_name in rh_ticket_urls:
        nav_module = "rh_support"
        active_tab = request.GET.get("tab", "available")
        allowed_support_tabs = {"available", "handled", "new", "closed", "ranking", "rewards"}
        if active_tab in {"ranking", "rewards"} and (not profile or profile.role not in {"ADMIN", "RESPONSABLE_RH", "RESPONSABLE_HIERARCHIQUE"}):
            active_tab = "available"
        nav_item = f"rh_support_{active_tab if active_tab in allowed_support_tabs else 'available'}"
    elif url_name in admin_urls:
        nav_module = "administration"
        active_tab = request.GET.get("tab", "overview")
        allowed_admin_tabs = {"overview", "account_requests", "users", "permissions", "edit_requests", "audit", "settings", "security", "notifications", "data", "reports"}
        nav_item = f"administration_{active_tab if active_tab in allowed_admin_tabs else 'overview'}"
    return {
        "utilisateur_connecte": profile,
        "notifications_non_lues": notifications_non_lues,
        "nav_module": nav_module,
        "nav_item": nav_item,
    }
