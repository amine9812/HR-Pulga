document.addEventListener("DOMContentLoaded", function () {
    const root = document.querySelector(".planning-workspace");
    if (!root) return;

    const shiftsUrl = root.dataset.shiftsUrl;
    const assistantUrl = root.dataset.assistantUrl;
    const form = document.getElementById("shiftEditorForm");
    const offcanvasEl = document.getElementById("shiftOffcanvas");
    const offcanvas = offcanvasEl && window.bootstrap ? bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl) : null;
    const errorBox = form ? form.querySelector(".planning-form-errors") : null;
    const cancelButton = form ? form.querySelector(".js-cancel-shift") : null;

    function csrfToken() {
        const input = document.querySelector("input[name='csrfmiddlewaretoken']");
        if (input) return input.value;
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function localDateTime(value) {
        if (!value) return "";
        const date = new Date(value);
        const pad = (n) => String(n).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function sameTimeOnDay(isoValue, dayValue) {
        const original = new Date(isoValue);
        const next = new Date(`${dayValue}T00:00:00`);
        next.setHours(original.getHours(), original.getMinutes(), 0, 0);
        return next;
    }

    function showErrors(payload) {
        if (!errorBox) return;
        const errors = payload.errors || {"__all__": [payload.message || "Action impossible."]};
        errorBox.hidden = false;
        errorBox.innerHTML = Object.values(errors).flat().map((error) => `<div class="alert alert-danger py-2 mb-2">${error}</div>`).join("");
    }

    async function api(url, method, body) {
        const response = await fetch(url, {
            method,
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
            },
            body: body ? JSON.stringify(body) : undefined,
        });
        const payload = await response.json();
        if (!payload.ok) throw payload;
        return payload;
    }

    function resetForm(defaults = {}) {
        if (!form) return;
        form.reset();
        form.shift_id.value = defaults.id || "";
        form.title.value = defaults.title || "Shift";
        form.employee_id.value = defaults.employee_id || "";
        form.department_id.value = defaults.department_id || "";
        form.service_id.value = defaults.service_id || "";
        form.plan_type.value = defaults.plan_type || "normal";
        form.recurrence_rule.value = defaults.recurrence_rule || "none";
        form.starts_at.value = defaults.starts_at || "";
        form.ends_at.value = defaults.ends_at || "";
        form.permanent_end_time.value = defaults.permanent_end_time || "";
        form.break_minutes.value = defaults.break_minutes || 0;
        form.break_starts_at.value = defaults.break_starts_at || "";
        form.status.value = defaults.status || "publie";
        form.location.value = defaults.location || "Casablanca";
        form.notes.value = defaults.notes || "";
        if (errorBox) {
            errorBox.hidden = true;
            errorBox.innerHTML = "";
        }
        if (cancelButton) cancelButton.hidden = !defaults.id;
    }

    function openNewShift(cell) {
        const day = cell?.dataset.day;
        const start = day ? new Date(`${day}T09:00:00`) : new Date();
        const end = new Date(start.getTime() + 8 * 60 * 60 * 1000);
        resetForm({
            employee_id: cell?.dataset.employeeId || "",
            starts_at: localDateTime(start),
            ends_at: localDateTime(end),
        });
        if (offcanvas) offcanvas.show();
    }

    async function openEditShift(id) {
        try {
            const payload = await api(`${shiftsUrl}/${id}`, "GET");
            const shift = payload.data.shift;
            resetForm({
                id: shift.id,
                title: shift.title,
                employee_id: shift.employee_id || "",
                department_id: shift.department_id || "",
                service_id: shift.service_id || "",
                plan_type: shift.plan_type || "normal",
                recurrence_rule: shift.recurrence_rule || "none",
                starts_at: localDateTime(shift.starts_at),
                ends_at: localDateTime(shift.ends_at),
                permanent_end_time: shift.permanent_end_time || "",
                break_minutes: shift.break_minutes || 0,
                break_starts_at: localDateTime(shift.break_starts_at),
                status: shift.status,
                location: shift.location,
                notes: shift.notes,
            });
            if (offcanvas) offcanvas.show();
        } catch (error) {
            window.alert(error.message || "Impossible de charger ce shift.");
        }
    }

    document.querySelectorAll(".js-new-shift").forEach((button) => {
        button.addEventListener("click", () => openNewShift(button.closest(".planning-grid-cell")));
    });

    document.querySelectorAll(".js-edit-shift").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            openEditShift(button.closest("[data-shift-id]").dataset.shiftId);
        });
    });

    if (form) {
        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            const id = form.shift_id.value;
            const body = {
                title: form.title.value,
                employee_id: form.employee_id.value,
                department_id: form.department_id.value,
                service_id: form.service_id.value,
                plan_type: form.plan_type.value,
                recurrence_rule: form.recurrence_rule.value,
                starts_at: form.starts_at.value,
                ends_at: form.ends_at.value,
                permanent_end_time: form.permanent_end_time.value,
                break_minutes: form.break_minutes.value,
                break_starts_at: form.break_starts_at.value,
                status: form.status.value,
                location: form.location.value,
                notes: form.notes.value,
            };
            try {
                await api(id ? `${shiftsUrl}/${id}` : shiftsUrl, id ? "PUT" : "POST", body);
                window.location.reload();
            } catch (error) {
                showErrors(error);
            }
        });
    }

    if (cancelButton) {
        cancelButton.addEventListener("click", async function () {
            const id = form.shift_id.value;
            if (!id || !window.confirm("Annuler ce shift ?")) return;
            try {
                await api(`${shiftsUrl}/${id}`, "DELETE");
                window.location.reload();
            } catch (error) {
                showErrors(error);
            }
        });
    }

    document.querySelectorAll(".planning-shift-block").forEach((shift) => {
        shift.addEventListener("dragstart", (event) => {
            event.dataTransfer.setData("text/plain", shift.dataset.shiftId);
            event.dataTransfer.effectAllowed = "move";
        });
        shift.addEventListener("dblclick", () => openEditShift(shift.dataset.shiftId));
    });

    document.querySelectorAll(".planning-grid-cell").forEach((cell) => {
        cell.addEventListener("dragover", (event) => {
            if (cell.dataset.employeeId) {
                event.preventDefault();
                cell.classList.add("drag-over");
            }
        });
        cell.addEventListener("dragleave", () => {
            cell.classList.remove("drag-over");
        });
        cell.addEventListener("drop", async (event) => {
            event.preventDefault();
            cell.classList.remove("drag-over");
            const id = event.dataTransfer.getData("text/plain");
            const block = document.querySelector(`[data-shift-id="${id}"]`);
            if (!id || !block) return;
            const oldStart = new Date(block.dataset.start);
            const oldEnd = new Date(block.dataset.end);
            if (!block.dataset.end || Number.isNaN(oldEnd.getTime())) {
                window.alert("Les plans permanents ne se deplacent pas par glisser-deposer.");
                return;
            }
            const newStart = sameTimeOnDay(block.dataset.start, cell.dataset.day);
            const duration = oldEnd.getTime() - oldStart.getTime();
            const newEnd = new Date(newStart.getTime() + duration);
            try {
                await api(`${shiftsUrl}/${id}/move`, "POST", {
                    employee_id: cell.dataset.employeeId,
                    starts_at: localDateTime(newStart),
                    ends_at: localDateTime(newEnd),
                });
                window.location.reload();
            } catch (error) {
                window.alert(error.message || "Deplacement impossible.");
            }
        });
    });

    document.querySelectorAll(".js-resize-shift").forEach((button) => {
        button.addEventListener("click", async (event) => {
            event.stopPropagation();
            const block = button.closest("[data-shift-id]");
            const id = block.dataset.shiftId;
            const end = new Date(block.dataset.end);
            end.setMinutes(end.getMinutes() + Number(button.dataset.minutes || 0));
            try {
                await api(`${shiftsUrl}/${id}/resize`, "POST", {ends_at: localDateTime(end)});
                window.location.reload();
            } catch (error) {
                window.alert(error.message || "Redimensionnement impossible.");
            }
        });
    });

    const assistantForm = document.getElementById("planningAssistantForm");
    const chatLog = document.getElementById("planningChatMessages");
    function addChatMessage(text, className) {
        if (!chatLog) return;
        const node = document.createElement("div");
        node.className = className;
        node.textContent = text;
        chatLog.appendChild(node);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    document.querySelectorAll(".js-assistant-prompt").forEach((button) => {
        button.addEventListener("click", () => {
            if (!assistantForm) return;
            assistantForm.message.value = button.textContent.trim();
            assistantForm.requestSubmit();
        });
    });

    if (assistantForm) {
        assistantForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            const message = assistantForm.message.value.trim();
            if (!message) return;
            addChatMessage(message, "user-message");
            assistantForm.message.value = "";
            addChatMessage("Analyse en cours...", "assistant-message is-loading");
            const loading = chatLog.querySelector(".is-loading");
            const params = new URLSearchParams(window.location.search);
            try {
                const payload = await api(assistantUrl, "POST", {
                    message,
                    start_date: params.get("date_debut") || "",
                    end_date: params.get("date_fin") || "",
                });
                if (loading) loading.remove();
                addChatMessage(payload.data.answer || payload.message || "Action traitee.", "assistant-message");
            } catch (error) {
                if (loading) loading.remove();
                addChatMessage(error.message || "Assistant indisponible.", "assistant-message is-error");
            }
        });
    }
});
