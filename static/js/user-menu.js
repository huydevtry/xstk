let deferredPrompt = null;

function isStandalonePwa() {
    return window.matchMedia?.("(display-mode: standalone)")?.matches
        || window.navigator.standalone === true;
}

function isIosDevice() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent || "")
        || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
}

function showInstallButton() {
    if (isStandalonePwa()) return;
    const installBtn = document.getElementById("pwa-install-btn");
    if (installBtn) {
        installBtn.classList.remove("hidden");
    }
}

function hideInstallButton() {
    const installBtn = document.getElementById("pwa-install-btn");
    if (installBtn) {
        installBtn.classList.add("hidden");
    }
}

function showManualInstallGuide() {
    alert(
        "Để cài ứng dụng lên màn hình chính:\n\n" +
        "1. Nhấn nút Share/Chia sẻ trên trình duyệt.\n" +
        "2. Chọn Add to Home Screen / Thêm vào Màn hình chính.\n" +
        "3. Nhấn Add / Thêm để hoàn tất."
    );
}

// Listen for the beforeinstallprompt event (fired by browsers supporting custom install prompts)
window.addEventListener("beforeinstallprompt", (e) => {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later
    deferredPrompt = e;
    showInstallButton();
});

// Hide the install button once the app has been successfully installed
window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    hideInstallButton();
});

document.addEventListener("DOMContentLoaded", () => {
    const containers = Array.from(document.querySelectorAll("[data-user-menu]"));
    if (!containers.length) return;

    const closeAllMenus = () => {
        containers.forEach(container => {
            const trigger = container.querySelector("[data-user-menu-trigger]");
            const panel = container.querySelector("[data-user-menu-panel]");
            trigger?.setAttribute("aria-expanded", "false");
            panel?.classList.add("hidden");
        });
    };

    containers.forEach(container => {
        const trigger = container.querySelector("[data-user-menu-trigger]");
        const panel = container.querySelector("[data-user-menu-panel]");
        if (!trigger || !panel) return;

        trigger.addEventListener("click", event => {
            event.preventDefault();
            const shouldOpen = panel.classList.contains("hidden");
            closeAllMenus();
            if (shouldOpen) {
                trigger.setAttribute("aria-expanded", "true");
                panel.classList.remove("hidden");
            }
        });

        panel.addEventListener("click", event => {
            const target = event.target;
            if (target instanceof Element && target.closest("a")) {
                closeAllMenus();
            }
        });
    });

    // Wire up PWA install button
    const installBtn = document.getElementById("pwa-install-btn");
    if (installBtn) {
        // Chrome/Android exposes beforeinstallprompt; iOS Safari needs manual Add to Home Screen steps.
        if (deferredPrompt || isIosDevice()) {
            showInstallButton();
        }

        installBtn.addEventListener("click", async () => {
            // Close the menu first for a clean UX
            closeAllMenus();
            if (!deferredPrompt) {
                showManualInstallGuide();
                return;
            }
            // Show the install prompt
            deferredPrompt.prompt();
            // Wait for the user to respond to the prompt
            const { outcome } = await deferredPrompt.userChoice;
            console.info(`[PWA] User choice outcome: ${outcome}`);
            // Clear the prompt (it can only be used once)
            deferredPrompt = null;
            // Hide the button
            hideInstallButton();
        });
    }

    document.addEventListener("click", event => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest("[data-user-menu]")) return;
        closeAllMenus();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") closeAllMenus();
    });
});
