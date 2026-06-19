(() => {
    const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>\"']/g, ch => ({
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

    function formatTime(value) {
        if (!value) return "Không rõ thời gian";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "Không rõ thời gian";
        return date.toLocaleString("vi-VN", {
            timeZone: APP_TIME_ZONE,
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function renderAvatar(author) {
        const avatarSrc = safeImageSrc(author?.avatar_url);
        if (avatarSrc) {
            return `<img src="${avatarSrc}" alt="" class="h-10 w-10 rounded-full border border-slate-200 object-cover flex-shrink-0">`;
        }
        return `<span class="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-xs font-black text-white flex-shrink-0" style="background:${safeCssColor(author?.avatar_color)}">${escapeHtml(author?.initials || "??")}</span>`;
    }

    function renderMatchSummary(match) {
        if (!match?.id) return "";
        const homeIcon = safeImageSrc(match.home_icon)
            ? `<img src="${safeImageSrc(match.home_icon)}" alt="" class="h-5 w-5 rounded-full border border-slate-200 object-cover">`
            : `<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-[9px] font-black text-slate-500">${escapeHtml(String(match.home_team || "?").slice(0, 1).toUpperCase())}</span>`;
        const awayIcon = safeImageSrc(match.away_icon)
            ? `<img src="${safeImageSrc(match.away_icon)}" alt="" class="h-5 w-5 rounded-full border border-slate-200 object-cover">`
            : `<span class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-[9px] font-black text-slate-500">${escapeHtml(String(match.away_team || "?").slice(0, 1).toUpperCase())}</span>`;
        const score = match.result_published || String(match.status || "").toLowerCase() === "finished"
            ? `${Number(match.home_score ?? 0)} - ${Number(match.away_score ?? 0)}`
            : "vs";
        return `
            <button
                type="button"
                class="mt-3 flex w-full items-center justify-between gap-3 rounded-2xl border border-sky-100 bg-sky-50 px-3 py-2 text-left transition hover:border-sky-200 hover:bg-sky-100"
                onclick="openMatchDetail(${Number(match.id)}, true)"
            >
                <div class="flex min-w-0 items-center gap-2">
                    ${homeIcon}
                    <span class="truncate text-xs font-semibold text-slate-700">${escapeHtml(match.home_team || "?")}</span>
                </div>
                <div class="flex-shrink-0 text-xs font-black text-sky-700">${escapeHtml(score)}</div>
                <div class="flex min-w-0 items-center justify-end gap-2">
                    <span class="truncate text-xs font-semibold text-slate-700">${escapeHtml(match.away_team || "?")}</span>
                    ${awayIcon}
                </div>
            </button>
        `;
    }

    function formatCoins(value) {
        return `${Number(value || 0).toLocaleString()}đ`;
    }

    function renderReactionResult(result) {
        if (!result?.outcome) return "";
        if (result.outcome === "win") {
            return `
                <div class="mt-3 inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                    ✅ ${escapeHtml(result.outcome_label || "Thắng")} +${escapeHtml(formatCoins(result.points_earned || 0))}
                </div>
            `;
        }
        if (result.outcome === "refund") {
            return `
                <div class="mt-3 inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">
                    ↺ ${escapeHtml(result.outcome_label || "Hoàn điểm")} ${escapeHtml(formatCoins(result.stake || 0))}
                </div>
            `;
        }
        return `
            <div class="mt-3 inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-bold text-rose-700">
                ❌ ${escapeHtml(result.outcome_label || "Thua")}
            </div>
        `;
    }

    function buildAuthorHref(author, options) {
        const hrefBuilder = options?.authorHrefBuilder;
        if (typeof hrefBuilder !== "function" || !author?.id) return null;
        return hrefBuilder(author);
    }

    function createTimelineItemHtml(item, options = {}) {
        const author = item?.author || {};
        const authorHref = buildAuthorHref(author, options);
        const authorName = escapeHtml(author.display_name || author.name || "Người dùng");
        const authorNode = authorHref
            ? `<a href="${escapeHtml(authorHref)}" class="inline-flex min-w-0 items-center gap-3 hover:opacity-90">${renderAvatar(author)}<div class="min-w-0"><div class="truncate text-sm font-semibold text-slate-900">${authorName}</div><div class="text-[11px] text-slate-400">${escapeHtml(formatTime(item?.created_at))}</div></div></a>`
            : `<div class="inline-flex min-w-0 items-center gap-3">${renderAvatar(author)}<div class="min-w-0"><div class="truncate text-sm font-semibold text-slate-900">${authorName}</div><div class="text-[11px] text-slate-400">${escapeHtml(formatTime(item?.created_at))}</div></div></div>`;

        const badge = item?.post_type === "match_reaction"
            ? `<span class="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-sky-700">Trình bày</span>`
            : `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-500">Lè nhè</span>`;

        return `
            <article class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="flex items-start justify-between gap-3">
                    ${authorNode}
                    ${badge}
                </div>
                <p class="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">${escapeHtml(item?.content || "")}</p>
                ${item?.post_type === "match_reaction" ? renderReactionResult(item?.reaction_result) : ""}
                ${renderMatchSummary(item?.match)}
            </article>
        `;
    }

    function render(container, items, options = {}) {
        if (!container) return;
        container.innerHTML = (items || []).map(item => createTimelineItemHtml(item, options)).join("");
    }

    function append(container, items, options = {}) {
        if (!container) return;
        container.insertAdjacentHTML("beforeend", (items || []).map(item => createTimelineItemHtml(item, options)).join(""));
    }

    window.TimelineFeed = {
        render,
        append,
        createTimelineItemHtml,
    };
})();
