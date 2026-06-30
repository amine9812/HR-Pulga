document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".login-form-panel form").forEach(function (form) {
        form.addEventListener("submit", function () {
            const submit = form.querySelector("button[type='submit']");
            if (!submit || submit.disabled) return;
            submit.dataset.originalText = submit.textContent;
            submit.disabled = true;
            submit.textContent = "Traitement...";
        });
    });
});
