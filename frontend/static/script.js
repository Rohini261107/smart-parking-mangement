document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".toast-stack .alert").forEach(function (toast) {
        const dismiss = function () {
            toast.classList.add("toast-dismissed");
            window.setTimeout(function () { toast.remove(); }, 220);
        };
        const close = toast.querySelector(".toast-close");
        if (close) close.addEventListener("click", dismiss);
        window.setTimeout(dismiss, 6000);
    });

    const dashboardDate = document.querySelector("[data-dashboard-date]");
    const dashboardTime = document.querySelector("[data-dashboard-time]");
    if (dashboardDate || dashboardTime) {
        const updateDashboardClock = function () {
            const now = new Date();
            if (dashboardDate) {
                dashboardDate.textContent = new Intl.DateTimeFormat(undefined, {
                    weekday: "short", day: "numeric", month: "short", year: "numeric"
                }).format(now);
            }
            if (dashboardTime) {
                dashboardTime.textContent = new Intl.DateTimeFormat(undefined, {
                    hour: "2-digit", minute: "2-digit"
                }).format(now);
            }
        };
        updateDashboardClock();
        window.setInterval(updateDashboardClock, 60000);
    }

    const parkingBays = document.querySelectorAll("[data-parking-bay]");
    const detailTitle = document.querySelector("[data-detail-title]");
    const detailCopy = document.querySelector("[data-detail-copy]");
    const detailAction = document.querySelector("[data-detail-action]");
    const entryUrl = document.querySelector("[data-entry-url]");
    parkingBays.forEach(function (bay) {
        bay.addEventListener("click", function () {
            if (!detailTitle || !detailCopy || !detailAction) return;
            const slotId = bay.dataset.slotId;
            const status = bay.dataset.slotStatus;
            const readableStatus = status.charAt(0).toUpperCase() + status.slice(1);
            detailTitle.textContent = slotId + " · " + readableStatus;
            detailCopy.textContent = status === "available"
                ? "This space is available. Continue to vehicle entry to park here."
                : status === "booked"
                    ? "This space has an active reservation."
                    : "This space is currently occupied.";
            if (status === "available" && entryUrl) {
                detailAction.href = entryUrl.dataset.entryUrl + "?slot=" + encodeURIComponent(slotId);
                detailAction.textContent = "Choose this slot";
                detailAction.hidden = false;
            } else {
                detailAction.hidden = true;
            }
        });
    });

    const dashboardSearch = document.querySelector("[data-dashboard-search]");
    if (dashboardSearch) {
        dashboardSearch.addEventListener("input", function () {
            const query = dashboardSearch.value.trim().toLowerCase();
            parkingBays.forEach(function (bay) {
                bay.hidden = query !== "" && !bay.dataset.slotId.toLowerCase().includes(query);
            });
            document.querySelectorAll(".dashboard-table tbody tr").forEach(function (row) {
                row.hidden = query !== "" && !row.textContent.toLowerCase().includes(query);
            });
        });
    }

    const menuToggle = document.getElementById("menu-toggle");
    const sidebar = document.getElementById("app-sidebar");
    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
        document.addEventListener("click", function (event) {
            if (window.innerWidth <= 720 && sidebar.classList.contains("open") &&
                !sidebar.contains(event.target) && !menuToggle.contains(event.target)) {
                sidebar.classList.remove("open");
            }
        });
    }

    document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
        button.addEventListener("click", function () {
            const field = document.getElementById(button.dataset.togglePassword);
            if (!field) return;
            const show = field.type === "password";
            field.type = show ? "text" : "password";
            button.textContent = show ? "Hide" : "Show";
        });
    });

    const exitConfirmation = document.querySelector("[data-confirm-exit]");
    if (exitConfirmation) {
        exitConfirmation.addEventListener("submit", function (event) {
            if (!window.confirm("Confirm vehicle exit? Your entry payment is already complete.")) {
                event.preventDefault();
            }
        });
    }

    const reportPrint = document.querySelector("[data-print-page]");
    if (reportPrint) {
        reportPrint.addEventListener("click", function () {
            window.print();
        });
    }

    const printButton = document.getElementById("print-receipt");
    if (printButton) {
        printButton.addEventListener("click", function () {
            window.print();
        });
    }

    const entryForm = document.getElementById("entry-form");
    if (entryForm) {
        entryForm.addEventListener("submit", function (event) {
            const number = document.getElementById("vehicle_number").value.trim();
            const type = document.getElementById("vehicle_type").value;
            const error = document.getElementById("entry-error");

            if (!number || !type) {
                event.preventDefault();
                error.textContent = !number
                    ? "Please enter vehicle number."
                    : "Please select vehicle type.";
                error.hidden = false;
            }
        });
    }

    const exitForm = document.getElementById("exit-form");
    if (exitForm) {
        exitForm.addEventListener("submit", function (event) {
            const number = document.getElementById("vehicle_number").value.trim();
            const error = document.getElementById("exit-error");

            if (!number) {
                event.preventDefault();
                error.textContent = "Please enter vehicle number.";
                error.hidden = false;
                return;
            }

            if (!window.confirm("Confirm vehicle exit and calculate the parking fee?")) {
                event.preventDefault();
            }
        });
    }

    const bookingForm = document.getElementById("booking-form");
    if (bookingForm) {
        bookingForm.addEventListener("submit", function (event) {
            const number = document.getElementById("vehicle_number").value.trim();
            const type = document.getElementById("vehicle_type").value;
            const slot = document.getElementById("slot_id").value;
            const error = document.getElementById("booking-error");

            if (!number || !type || !slot) {
                event.preventDefault();
                if (!number) {
                    error.textContent = "Please enter vehicle number.";
                } else if (!type) {
                    error.textContent = "Please select vehicle type.";
                } else {
                    error.textContent = "Please select a parking slot.";
                }
                error.hidden = false;
            }
        });
    }
});
