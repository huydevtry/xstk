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
        const flagMatch = src.match(/flagcdn\.com\/(?:[a-z0-9]+\/)?([a-z0-9-]+)\.(?:png|webp|jpg|jpeg|svg)/i);
        if (flagMatch) return escapeHtml(`https://flagcdn.com/w320/${flagMatch[1].toLowerCase()}.webp`);
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

    function renderAvatarWithClasses(author, sizeClass = "h-10 w-10", textClass = "text-xs", extraClass = "") {
        const avatarSrc = safeImageSrc(author?.avatar_url);
        const common = `${sizeClass} rounded-full border border-slate-200 flex-shrink-0 ${extraClass}`.trim();
        if (avatarSrc) {
            return `<img src="${avatarSrc}" alt="" class="${common} object-cover">`;
        }
        return `<span class="flex ${common} items-center justify-center ${textClass} font-black text-white" style="background:${safeCssColor(author?.avatar_color)}">${escapeHtml(author?.initials || "??")}</span>`;
    }

    function renderAvatar(author) {
        return renderAvatarWithClasses(author);
    }

    function renderMatchSummary(match) {
        if (!match?.id) return "";
        const homeIcon = safeImageSrc(match.home_icon)
            ? `<img src="${safeImageSrc(match.home_icon)}" alt="" class="h-4 w-6 rounded-none border border-slate-200 bg-white object-contain">`
            : `<span class="inline-flex h-4 w-6 items-center justify-center rounded-none border border-slate-200 bg-slate-100 text-[9px] font-black text-slate-500">${escapeHtml(String(match.home_team || "?").slice(0, 1).toUpperCase())}</span>`;
        const awayIcon = safeImageSrc(match.away_icon)
            ? `<img src="${safeImageSrc(match.away_icon)}" alt="" class="h-4 w-6 rounded-none border border-slate-200 bg-white object-contain">`
            : `<span class="inline-flex h-4 w-6 items-center justify-center rounded-none border border-slate-200 bg-slate-100 text-[9px] font-black text-slate-500">${escapeHtml(String(match.away_team || "?").slice(0, 1).toUpperCase())}</span>`;
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

    function renderComment(comment) {
        const author = comment?.author || {};
        const authorName = escapeHtml(author.display_name || author.name || "Người dùng");
        return `
            <div class="flex gap-2">
                ${renderAvatarWithClasses(author, "h-8 w-8", "text-[10px]")}
                <div class="min-w-0 flex-1 rounded-2xl bg-slate-50 px-3 py-2">
                    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span class="text-xs font-bold text-slate-900">${authorName}</span>
                        <span class="text-[10px] text-slate-400">${escapeHtml(formatTime(comment?.created_at))}</span>
                    </div>
                    <div class="mt-1 whitespace-pre-wrap break-words text-sm leading-5 text-slate-700">${escapeHtml(comment?.content || "")}</div>
                </div>
            </div>
        `;
    }

    function renderReactionResult(result) {
        if (!result?.outcome) return "";
        if (result.outcome === "win" || result.outcome === "half_win") {
            const icon = result.outcome === "half_win" ? "➗" : "✅";
            return `
                <div class="mt-3 inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                    ${icon} ${escapeHtml(result.outcome_label || "Thắng")} ${result.points_earned !== null && result.points_earned !== undefined ? escapeHtml(formatCoins(result.points_earned)) : ""}
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
        if (result.outcome === "half_lose") {
            return `
                <div class="mt-3 inline-flex items-center rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-xs font-bold text-orange-700">
                    ➗ ${escapeHtml(result.outcome_label || "Thua nửa")} ${result.points_earned !== null && result.points_earned !== undefined ? escapeHtml(formatCoins(result.points_earned)) : ""}
                </div>
            `;
        }
        return `
            <div class="mt-3 inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-bold text-rose-700">
                ❌ ${escapeHtml(result.outcome_label || "Thua")}
            </div>
        `;
    }

    function renderMedia(media) {
        const src = safeImageSrc(media?.url);
        if (!src) return "";
        const providerLabel = media?.provider === "giphy"
            ? `<div class="mt-2 text-right text-[11px] text-slate-400">Powered by <a href="https://giphy.com/" target="_blank" rel="noreferrer" class="font-semibold text-slate-500 hover:text-slate-700">GIPHY</a></div>`
            : "";
        const alt = media?.kind === "gif" ? "Ảnh GIF trong bài đăng" : "Ảnh trong bài đăng";
        return `
            <div class="mt-3">
                <div class="overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
                    <img src="${src}" alt="${escapeHtml(alt)}" loading="lazy" class="max-h-[520px] w-full object-contain">
                </div>
                ${providerLabel}
            </div>
        `;
    }

    function buildAuthorHref(author, options) {
        const hrefBuilder = options?.authorHrefBuilder;
        if (typeof hrefBuilder !== "function" || !author?.id) return null;
        return hrefBuilder(author);
    }

    function renderLikedUserRow(user) {
        const name = escapeHtml(user?.display_name || user?.name || "Người dùng");
        return `
            <div class="flex min-w-0 items-center gap-2">
                ${renderAvatarWithClasses(user, "h-7 w-7", "text-[9px]")}
                <span class="truncate text-xs font-semibold text-slate-700">${name}</span>
            </div>
        `;
    }

    function renderLikeAvatarStack(likedUsers, likeCount) {
        if (!likeCount) return "";
        const users = Array.isArray(likedUsers) ? likedUsers : [];
        const previewUsers = users.slice(0, 6);
        const hiddenCount = Math.max(0, likeCount - previewUsers.length);
        const fullList = users.map(renderLikedUserRow).join("");
        const hiddenBubble = hiddenCount > 0
            ? `
                <div class="group relative -ml-1.5 inline-flex">
                    <span class="flex h-6 min-w-6 items-center justify-center rounded-full border-2 border-white bg-slate-100 px-1.5 text-[10px] font-black text-slate-600 shadow-sm">
                        +${hiddenCount}
                    </span>
                    <div class="absolute bottom-full left-0 z-30 mb-2 hidden w-64 rounded-2xl border border-slate-200 bg-white p-3 shadow-xl group-hover:block">
                        <div class="mb-2 text-[11px] font-bold uppercase text-slate-400">${likeCount} người đã thích</div>
                        <div class="max-h-60 space-y-2 overflow-y-auto">
                            ${fullList}
                        </div>
                    </div>
                </div>
            `
            : "";

        return `
            <div class="flex min-w-0 items-center gap-2" data-timeline-likes>
                <div class="flex min-w-0 items-center pl-1.5">
                    ${previewUsers.map(user => `
                        <div class="-ml-1.5" title="${escapeHtml(user?.display_name || user?.name || "Người dùng")}">
                            ${renderAvatarWithClasses(user, "h-6 w-6", "text-[8px]", "border-2 border-white shadow-sm")}
                        </div>
                    `).join("")}
                    ${hiddenBubble}
                </div>
                <span class="truncate text-xs font-semibold text-slate-500">${likeCount} lượt thích</span>
            </div>
        `;
    }

    function renderInteractions(item, options = {}) {
        if (!options.enableInteractions) return "";
        const postId = item?.id ?? item?.post_id;
        if (!postId) return "";
        const likeCount = Number(item?.like_count || 0);
        const commentCount = Number(item?.comment_count || 0);
        const viewerLiked = Boolean(item?.viewer_liked);
        const likedUsers = Array.isArray(item?.liked_users) ? item.liked_users : [];
        const comments = Array.isArray(item?.comments) ? item.comments : [];
        const likeClasses = viewerLiked
            ? "border-rose-200 bg-rose-50 text-rose-600"
            : "border-slate-200 bg-white text-slate-500 hover:border-rose-200 hover:text-rose-500";

        return `
            <div class="mt-4 border-t border-slate-100 pt-3" data-timeline-interactions>
                <div class="flex items-center justify-between gap-3">
                    <div class="flex min-w-0 items-center gap-2">
                        <button
                            type="button"
                            class="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border text-lg leading-none transition ${likeClasses}"
                            data-timeline-action="like"
                            data-post-id="${escapeHtml(postId)}"
                            aria-pressed="${viewerLiked ? "true" : "false"}"
                            aria-label="${viewerLiked ? "Bỏ thích" : "Thích"}"
                            title="${viewerLiked ? "Bỏ thích" : "Thích"}"
                        >
                            <span aria-hidden="true">${viewerLiked ? "♥" : "♡"}</span>
                        </button>
                        ${renderLikeAvatarStack(likedUsers, likeCount)}
                    </div>
                    <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-500">
                        ${commentCount} bình luận
                    </span>
                </div>
                <div class="mt-3 space-y-2" data-timeline-comments>
                    ${comments.map(renderComment).join("")}
                </div>
                <form class="mt-3 flex gap-2" data-timeline-action="comment-form" data-post-id="${escapeHtml(postId)}">
                    <input
                        name="content"
                        type="text"
                        maxlength="280"
                        autocomplete="off"
                        class="min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-300"
                        placeholder="Viết bình luận..."
                    >
                    <button type="submit" class="rounded-2xl bg-slate-900 px-3 py-2 text-xs font-bold text-white transition hover:bg-slate-700">
                        Gửi
                    </button>
                </form>
            </div>
        `;
    }

    function createTimelineItemHtml(item, options = {}) {
        const author = item?.author || {};
        const authorHref = buildAuthorHref(author, options);
        const authorName = escapeHtml(author.display_name || author.name || "Người dùng");
        const authorNode = authorHref
            ? `<a href="${escapeHtml(authorHref)}" class="inline-flex min-w-0 items-center gap-3 hover:opacity-90">${renderAvatar(author)}<div class="min-w-0"><div class="truncate text-sm font-semibold text-slate-900">${authorName}</div><div class="text-[11px] text-slate-400">${escapeHtml(formatTime(item?.created_at))}</div></div></a>`
            : `<div class="inline-flex min-w-0 items-center gap-3">${renderAvatar(author)}<div class="min-w-0"><div class="truncate text-sm font-semibold text-slate-900">${authorName}</div><div class="text-[11px] text-slate-400">${escapeHtml(formatTime(item?.created_at))}</div></div></div>`;

        const content = String(item?.content || "");
        const contentNode = content
            ? `<p class="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">${escapeHtml(content)}</p>`
            : "";

        return `
            <article class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm" data-timeline-post-id="${escapeHtml(item?.id ?? "")}">
                <div class="flex items-start justify-between gap-3">
                    ${authorNode}
                </div>
                ${contentNode}
                ${renderMedia(item?.media)}
                ${item?.post_type === "match_reaction" ? renderReactionResult(item?.reaction_result) : ""}
                ${renderMatchSummary(item?.match)}
                ${renderInteractions(item, options)}
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

    function prepend(container, items, options = {}) {
        if (!container) return;
        container.insertAdjacentHTML("afterbegin", (items || []).map(item => createTimelineItemHtml(item, options)).join(""));
    }

    window.TimelineFeed = {
        render,
        append,
        prepend,
        createTimelineItemHtml,
        renderInteractions,
    };
})();
