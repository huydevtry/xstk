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
