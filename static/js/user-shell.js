(function () {
    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, ch => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;",
        }[ch]));
    }

    function safeImageSrc(value) {
        const src = String(value ?? "").trim();
        if (!src) return "";
        if (src.startsWith("/") || /^https?:\/\//i.test(src)) return escapeHtml(src);
        return "";
    }

    function safeCssColor(value) {
        const color = String(value ?? "").trim();
        return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
    }

    function renderMiniAvatar(user) {
        const avatarSrc = safeImageSrc(user?.avatar_url);
        if (avatarSrc) {
            return `<img src="${avatarSrc}" alt="" class="h-5 w-5 rounded-full border border-sky-300 object-cover flex-shrink-0">`;
        }
        return `<span class="flex h-5 w-5 items-center justify-center rounded-full border border-sky-300 text-[9px] font-black text-white flex-shrink-0" style="background:${safeCssColor(user?.avatar_color)}">${escapeHtml(user?.initials || "??")}</span>`;
    }

    function renderUserInfo(host, user, options = {}) {
        if (!host || !user) return;
        const displayName = user.display_name || String(user.email || "").split("@")[0] || "User";
        const pointsElementId = options.pointsElementId || "";
        const pointsMarkup = pointsElementId
            ? `<span class="font-bold text-[#D3af37]" id="${escapeHtml(pointsElementId)}">${Number(user.total_points || 0).toLocaleString()}</span><span class="text-[#D3af37]">d</span>`
            : `<span class="font-bold text-[#D3af37]">${Number(user.total_points || 0).toLocaleString()}</span><span class="text-[#D3af37]">d</span>`;
        host.title = user.email || "";
        host.innerHTML = `
            <span class="inline-flex max-w-full items-center gap-2">
                ${renderMiniAvatar(user)}
                <span class="max-w-[8rem] truncate font-semibold text-slate-900">${escapeHtml(displayName)}</span>
                <span class="text-slate-300">|</span>
                ${pointsMarkup}
            </span>`;
    }

    function renderAuthError(host, message = "Lỗi kết nối Auth") {
        if (!host) return;
        host.innerHTML = `<span class="font-medium text-red-400">${escapeHtml(message)}</span>`;
    }

    window.UserShell = {
        renderUserInfo,
        renderAuthError,
    };
})();
