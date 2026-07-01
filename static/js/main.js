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

    const chatWidget = document.querySelector(".ai-chat-widget");
    if (chatWidget) {
        const toggle = chatWidget.querySelector(".ai-chat-toggle");
        const panel = chatWidget.querySelector(".ai-chat-panel");
        const log = chatWidget.querySelector(".ai-chat-log");
        const form = chatWidget.querySelector(".ai-chat-form");
        const input = form?.querySelector("input[name='message']");
        const submitButton = form?.querySelector("button[type='submit']");
        const errorBox = chatWidget.querySelector(".ai-chat-error");
        const suggestions = chatWidget.querySelector(".ai-chat-suggestions");
        const clearButton = chatWidget.querySelector(".ai-chat-clear");
        const chatUrl = chatWidget.dataset.chatUrl;
        const storageKey = "rh.aiChat.session.v1";
        const requestTimeoutMs = 25000;
        let pendingRequest = false;
        let lastMessage = "";

        const csrfToken = function () {
            const inputToken = form?.querySelector("input[name='csrfmiddlewaretoken']");
            if (inputToken) return inputToken.value;
            const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
            return match ? decodeURIComponent(match[1]) : "";
        };
        const history = function () {
            try {
                return JSON.parse(sessionStorage.getItem(storageKey) || "[]");
            } catch (error) {
                return [];
            }
        };
        const saveHistory = function () {
            try {
                const items = Array.from(log.querySelectorAll(".ai-chat-message")).slice(-24).map(function (node) {
                    return { role: node.classList.contains("user") ? "user" : "assistant", text: node.dataset.text || node.textContent.trim() };
                });
                sessionStorage.setItem(storageKey, JSON.stringify(items));
            } catch (error) {
                // Session chat memory is optional; keep the widget usable.
            }
        };
        const addMessage = function (role, text, actions) {
            const node = document.createElement("div");
            node.className = `ai-chat-message ${role}`;
            node.dataset.text = text || "";
            node.textContent = text || "";
            if (actions && actions.length) {
                const actionRow = document.createElement("div");
                actionRow.className = "ai-chat-actions";
                actions.forEach(function (action) {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.textContent = action.label || "Ouvrir";
                    button.addEventListener("click", function () {
                        if (action.url) window.location.href = action.url;
                    });
                    actionRow.appendChild(button);
                });
                node.appendChild(actionRow);
            }
            log.appendChild(node);
            log.scrollTop = log.scrollHeight;
            saveHistory();
            return node;
        };
        const setBusy = function (busy) {
            pendingRequest = busy;
            if (input) input.disabled = busy;
            if (submitButton) submitButton.disabled = busy;
        };
        const setError = function (message, retryMessage) {
            if (!errorBox) return;
            errorBox.hidden = !message;
            errorBox.textContent = "";
            if (!message) return;
            const text = document.createElement("span");
            text.textContent = message;
            errorBox.appendChild(text);
            if (retryMessage) {
                const retry = document.createElement("button");
                retry.type = "button";
                retry.className = "ai-chat-retry";
                retry.textContent = "Reessayer";
                retry.addEventListener("click", function () {
                    if (!input || !form || pendingRequest) return;
                    input.value = retryMessage;
                    form.requestSubmit();
                });
                errorBox.appendChild(retry);
            }
        };
        history().forEach(function (item) {
            addMessage(item.role === "user" ? "user" : "assistant", item.text);
        });
        toggle?.addEventListener("click", function () {
            const isHidden = panel.hidden;
            panel.hidden = !isHidden;
            toggle.setAttribute("aria-expanded", String(isHidden));
            if (isHidden) input?.focus();
        });
        clearButton?.addEventListener("click", function () {
            sessionStorage.removeItem(storageKey);
            log.innerHTML = "";
            addMessage("assistant", "Conversation effacee. Je n'utiliserai que les informations accessibles a votre compte.");
            setError("");
        });
        suggestions?.addEventListener("click", function (event) {
            const button = event.target.closest("button");
            if (!button || !input || !form) return;
            input.value = button.textContent.trim();
            form.requestSubmit();
        });
        form?.addEventListener("submit", async function (event) {
            event.preventDefault();
            if (pendingRequest) {
                return;
            }
            const message = (input.value || "").trim();
            if (!message) {
                setError("Veuillez saisir un message.");
                return;
            }
            setError("");
            input.value = "";
            lastMessage = message;
            setBusy(true);
            addMessage("user", message);
            const loading = addMessage("assistant loading", "L'assistant verifie vos permissions et les donnees accessibles...");
            const controller = new AbortController();
            const timeoutId = window.setTimeout(function () {
                controller.abort();
            }, requestTimeoutMs);
            try {
                const response = await fetch(chatUrl, {
                    method: "POST",
                    headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
                    body: JSON.stringify({message}),
                    signal: controller.signal,
                });
                let payload = {};
                try {
                    payload = await response.json();
                } catch (error) {
                    payload = {};
                }
                loading.remove();
                window.clearTimeout(timeoutId);
                if (!response.ok || !payload.ok) {
                    if (payload.error === "session_expired" || response.status === 401) {
                        throw new Error(payload.message || "Votre session a expire. Veuillez vous reconnecter.");
                    }
                    throw new Error(payload.message || "Je ne peux pas joindre le service assistant pour le moment. Veuillez reessayer.");
                }
                addMessage("assistant", payload.data.answer, payload.data.actions || []);
            } catch (error) {
                loading.remove();
                window.clearTimeout(timeoutId);
                const messageText = error.name === "AbortError"
                    ? "L'assistant a mis trop de temps a repondre. Veuillez reessayer."
                    : (error.message || "L'envoi du message a echoue. Veuillez reessayer.");
                setError(messageText, lastMessage);
                addMessage("assistant", "Je ne peux pas joindre le service assistant pour le moment. Veuillez reessayer.");
            } finally {
                setBusy(false);
                input?.focus();
            }
        });
    }

});
