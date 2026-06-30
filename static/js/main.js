document.addEventListener("DOMContentLoaded", function () {
    const sidebarToggle = document.getElementById("sidebarToggle");
    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", function () {
            document.body.classList.toggle("sidebar-open");
        });
    }

    document.querySelectorAll(".flash-message").forEach(function (message) {
        setTimeout(function () {
            const alert = bootstrap.Alert.getOrCreateInstance(message);
            alert.close();
        }, 4000);
    });

    const debut = document.getElementById("dateDebut");
    const fin = document.getElementById("dateFin");
    const jours = document.getElementById("nombreJours");
    const calculerJours = function () {
        if (!debut || !fin || !jours || !debut.value || !fin.value) {
            return;
        }
        const start = new Date(debut.value);
        const end = new Date(fin.value);
        const diff = Math.floor((end - start) / 86400000) + 1;
        jours.textContent = diff > 0 ? diff + " jour(s)" : "Dates invalides";
        jours.classList.toggle("text-danger", diff <= 0);
    };
    if (debut && fin) {
        debut.addEventListener("change", calculerJours);
        fin.addEventListener("change", calculerJours);
        calculerJours();
    }

    document.querySelectorAll(".confirm-delete, .confirm-archive").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            const message = form.classList.contains("confirm-archive")
                ? "Confirmer l'archivage de cet element ?"
                : "Confirmer la suppression de cet element ?";
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    const sidebarNav = document.querySelector(".sidebar-nav");
    const sidebarGroups = Array.from(document.querySelectorAll(".sidebar-group"));
    const sidebarStateKeys = {
        expanded: "rh.sidebar.expandedGroups.v1",
        scrollTop: "rh.sidebar.scrollTop.v1",
    };
    const canUseSessionStorage = (function () {
        try {
            const probe = "__rh_sidebar_probe__";
            window.sessionStorage.setItem(probe, "1");
            window.sessionStorage.removeItem(probe);
            return true;
        } catch (error) {
            return false;
        }
    })();
    const getGroupKey = function (group) {
        const collapse = group ? group.querySelector(".collapse") : null;
        return collapse?.id || group?.getAttribute("data-group-route") || "";
    };
    const readExpandedGroups = function () {
        if (!canUseSessionStorage) {
            return new Set();
        }
        try {
            const parsed = JSON.parse(window.sessionStorage.getItem(sidebarStateKeys.expanded) || "[]");
            return new Set(Array.isArray(parsed) ? parsed.filter(function (value) {
                return typeof value === "string" && value.length > 0;
            }) : []);
        } catch (error) {
            return new Set();
        }
    };
    const writeExpandedGroups = function (expandedGroups) {
        if (!canUseSessionStorage) {
            return;
        }
        try {
            window.sessionStorage.setItem(sidebarStateKeys.expanded, JSON.stringify(Array.from(expandedGroups)));
        } catch (error) {
            // Navigation state is a convenience; ignore storage failures safely.
        }
    };
    const expandedGroups = readExpandedGroups();
    sidebarGroups.forEach(function (group) {
        const key = getGroupKey(group);
        const submenu = group.querySelector(".collapse");
        const parent = group.querySelector(".sidebar-parent");
        const hasActiveChild = Boolean(group.querySelector(".sidebar-subitem.active"));
        const isActiveSection = parent?.classList.contains("active") || hasActiveChild;
        if (key && isActiveSection) {
            expandedGroups.add(key);
        }
        if (key && expandedGroups.has(key) && submenu && parent) {
            submenu.classList.add("show");
            parent.setAttribute("aria-expanded", "true");
        }
    });
    writeExpandedGroups(expandedGroups);

    sidebarGroups.forEach(function (group) {
        const key = getGroupKey(group);
        const submenu = group.querySelector(".collapse");
        const parent = group.querySelector(".sidebar-parent");
        if (!key || !submenu || !parent) {
            return;
        }
        submenu.addEventListener("shown.bs.collapse", function () {
            expandedGroups.add(key);
            writeExpandedGroups(expandedGroups);
            parent.setAttribute("aria-expanded", "true");
        });
        submenu.addEventListener("hidden.bs.collapse", function () {
            expandedGroups.delete(key);
            writeExpandedGroups(expandedGroups);
            parent.setAttribute("aria-expanded", "false");
        });
    });

    const saveSidebarScroll = function () {
        if (!sidebarNav || !canUseSessionStorage) {
            return;
        }
        try {
            window.sessionStorage.setItem(sidebarStateKeys.scrollTop, String(Math.max(0, Math.round(sidebarNav.scrollTop || 0))));
        } catch (error) {
            // Keep navigation usable even if storage is unavailable or full.
        }
    };
    const restoreSidebarScroll = function () {
        if (!sidebarNav || !canUseSessionStorage || window.matchMedia("(max-width: 767.98px)").matches) {
            return;
        }
        try {
            const savedScroll = Number.parseInt(window.sessionStorage.getItem(sidebarStateKeys.scrollTop) || "0", 10);
            if (!Number.isFinite(savedScroll) || savedScroll < 0) {
                return;
            }
            const maxScroll = Math.max(0, sidebarNav.scrollHeight - sidebarNav.clientHeight);
            sidebarNav.scrollTop = Math.min(savedScroll, maxScroll);
        } catch (error) {
            sidebarNav.scrollTop = 0;
        }
    };
    if (sidebarNav) {
        requestAnimationFrame(restoreSidebarScroll);
        sidebarNav.addEventListener("scroll", saveSidebarScroll, { passive: true });
        document.querySelectorAll(".sidebar-nav a[href]").forEach(function (link) {
            link.addEventListener("click", saveSidebarScroll);
        });
        window.addEventListener("pagehide", saveSidebarScroll);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "hidden") {
                saveSidebarScroll();
            }
        });
    }

    const path = window.location.pathname;
    document.querySelectorAll(".sidebar-nav .nav-link").forEach(function (link) {
        const route = link.getAttribute("data-route");
        const isActiveRoute = route && (path === route || path.startsWith(route + "/"));
        if (isActiveRoute) {
            link.classList.add("active");
            const group = link.closest(".sidebar-group");
            const submenu = group ? group.querySelector(".collapse") : null;
            const parent = group ? group.querySelector(".sidebar-parent") : null;
            if (submenu && parent) {
                submenu.classList.add("show");
                parent.classList.add("active");
                parent.setAttribute("aria-expanded", "true");
            }
        }
    });
    sidebarGroups.forEach(function (group) {
        const groupRoute = group.getAttribute("data-group-route");
        const submenu = group.querySelector(".collapse");
        const parent = group.querySelector(".sidebar-parent");
        if (groupRoute && submenu && parent && (path === groupRoute || path.startsWith(groupRoute + "/"))) {
            submenu.classList.add("show");
            parent.classList.add("active");
            parent.setAttribute("aria-expanded", "true");
            const key = getGroupKey(group);
            if (key) {
                expandedGroups.add(key);
                writeExpandedGroups(expandedGroups);
            }
        }
    });

    document.querySelectorAll("input[type='file']").forEach(function (input) {
        input.addEventListener("change", function () {
            const label = input.closest(".file-field")?.querySelector(".selected-file");
            if (label) {
                label.textContent = input.files.length ? input.files[0].name : "Aucun fichier selectionne";
            }
        });
    });

    const planningScope = document.querySelector("select[name='scope']");
    if (planningScope) {
        const togglePlanningFields = function () {
            const scope = planningScope.value;
            const fields = {
                departement: document.querySelector("[name='departement']")?.closest("[class*='col-']"),
                service: document.querySelector("[name='service']")?.closest("[class*='col-']"),
                employes: document.querySelector("[name='employes']")?.closest("[class*='col-']"),
            };
            if (fields.departement) fields.departement.classList.toggle("is-soft-hidden", scope !== "departement" && scope !== "service");
            if (fields.service) fields.service.classList.toggle("is-soft-hidden", scope !== "service");
            if (fields.employes) fields.employes.classList.toggle("is-soft-hidden", scope !== "employees");
        };
        planningScope.addEventListener("change", togglePlanningFields);
        togglePlanningFields();
    }

});
