(() => {
    const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";
    const COMMENT_COLLAPSE_LIMIT = 4;

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
            ? (match.display_score || `${Number(match.home_score ?? 0)} - ${Number(match.away_score ?? 0)}`)
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
        const hiddenComments = comments.length > COMMENT_COLLAPSE_LIMIT
            ? comments.slice(0, comments.length - COMMENT_COLLAPSE_LIMIT)
            : [];
        const visibleComments = comments.length > COMMENT_COLLAPSE_LIMIT
            ? comments.slice(-COMMENT_COLLAPSE_LIMIT)
            : comments;
        const likeClasses = viewerLiked
            ? "border-rose-200 bg-rose-50 text-rose-600"
            : "border-slate-200 bg-white text-slate-500 hover:border-rose-200 hover:text-rose-500";
        const collapseToggle = hiddenComments.length
            ? `
                <button
                    type="button"
                    class="text-xs font-semibold text-sky-600 transition hover:text-sky-700"
                    data-timeline-action="toggle-comments"
                    data-expanded="false"
                    data-show-label="Xem thêm ${hiddenComments.length} bình luận"
                    data-hide-label="Thu gọn bình luận"
                >
                    Xem thêm ${hiddenComments.length} bình luận
                </button>
            `
            : "";

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
                    ${collapseToggle}
                    ${hiddenComments.map(comment => `<div class="hidden" data-collapsed-comment>${renderComment(comment)}</div>`).join("")}
                    ${visibleComments.map(renderComment).join("")}
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

    document.addEventListener("click", event => {
        const toggle = event.target.closest("[data-timeline-action='toggle-comments']");
        if (!toggle) return;
        const commentsHost = toggle.closest("[data-timeline-comments]");
        if (!commentsHost) return;
        const expanded = toggle.dataset.expanded === "true";
        commentsHost.querySelectorAll("[data-collapsed-comment]").forEach(node => {
            node.classList.toggle("hidden", expanded);
        });
        toggle.dataset.expanded = expanded ? "false" : "true";
        toggle.textContent = expanded
            ? (toggle.dataset.showLabel || "Xem thêm bình luận")
            : (toggle.dataset.hideLabel || "Thu gọn bình luận");
    });

    function renderEditButton(item) {
        if (!item?.can_edit) return "";
        return `
            <button
                type="button"
                class="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 transition hover:border-sky-200 hover:bg-sky-50 hover:text-sky-600"
                data-timeline-action="edit"
                data-post-id="${escapeHtml(item?.id ?? "")}"
                aria-label="Sửa bài viết"
                title="Sửa bài viết"
            >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 7.125L16.875 4.5M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/>
                </svg>
            </button>
        `;
    }

    function renderAuthorBadge(badge) {
        if (!badge) return "";
        const colorClass = badge.color === "gold" ? "border-amber-200 bg-amber-50 text-amber-700" :
            badge.color === "purple" ? "border-violet-200 bg-violet-50 text-violet-700" :
            badge.color === "red" ? "border-rose-200 bg-rose-50 text-rose-700" :
            "border-slate-200 bg-slate-50 text-slate-700";
        return `<span class="inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${colorClass}">${escapeHtml(badge.emoji)} ${escapeHtml(badge.label)}</span>`;
    }

    function createTimelineItemHtml(item, options = {}) {
        const author = item?.author || {};
        const authorHref = buildAuthorHref(author, options);
        const authorName = escapeHtml(author.display_name || author.name || "Người dùng");
        const authorBadge = renderAuthorBadge(author.badge);
        const editedLabel = item?.is_edited
            ? `<span class="italic text-slate-400">Đã chỉnh sửa</span>`
            : "";
        const timeNode = `
            <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-slate-400">
                <span>${escapeHtml(formatTime(item?.created_at))}</span>
                ${editedLabel}
            </div>
        `;
        const authorMeta = `<div class="min-w-0"><div class="flex flex-wrap items-center gap-1.5"><div class="max-w-[11rem] truncate text-sm font-semibold text-slate-900">${authorName}</div>${authorBadge}</div>${timeNode}</div>`;
        const authorNode = authorHref
            ? `<a href="${escapeHtml(authorHref)}" class="inline-flex min-w-0 items-center gap-3 hover:opacity-90">${renderAvatar(author)}${authorMeta}</a>`
            : `<div class="inline-flex min-w-0 items-center gap-3">${renderAvatar(author)}${authorMeta}</div>`;

        const content = String(item?.content || "");
        const media = item?.media || null;
        const contentNode = content
            ? `<p class="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">${escapeHtml(content)}</p>`
            : "";

        return `
            <article
                class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
                data-timeline-post-id="${escapeHtml(item?.id ?? "")}"
                data-post-content="${escapeHtml(content)}"
                data-post-media-url="${escapeHtml(media?.url || "")}"
                data-post-media-content-type="${escapeHtml(media?.content_type || "")}"
                data-post-media-provider="${escapeHtml(media?.provider || "")}"
            >
                <div class="flex items-start justify-between gap-3">
                    ${authorNode}
                    ${renderEditButton(item)}
                </div>
                ${contentNode}
                ${renderMedia(media)}
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

    function initEditor(config = {}) {
        const container = document.getElementById(config.containerId);
        const modal = document.getElementById("timeline-edit-modal");
        const contentInput = document.getElementById("timeline-edit-content");
        const countEl = document.getElementById("timeline-edit-count");
        const fileInput = document.getElementById("timeline-edit-media-input");
        const chooseMediaBtn = document.getElementById("choose-timeline-edit-media");
        const removeMediaBtn = document.getElementById("remove-timeline-edit-media");
        const clearMediaBtn = document.getElementById("clear-timeline-edit-media");
        const previewWrap = document.getElementById("timeline-edit-media-preview-wrap");
        const previewImg = document.getElementById("timeline-edit-media-preview");
        const errorEl = document.getElementById("timeline-edit-error");
        const saveBtn = document.getElementById("timeline-edit-save");
        const cancelBtn = document.getElementById("timeline-edit-cancel");
        const closeBtn = document.getElementById("close-timeline-edit");
        if (!container || !modal || !contentInput || !countEl || !fileInput || !chooseMediaBtn || !removeMediaBtn || !clearMediaBtn || !previewWrap || !previewImg || !errorEl || !saveBtn || !cancelBtn || !closeBtn) {
            return;
        }

        const maxBytes = 8 * 1024 * 1024;
        const uploadTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
        let activeArticle = null;
        let activePostId = null;
        let originalMedia = null;
        let selectedFile = null;
        let selectedPreviewUrl = "";
        let selectedExternalUrl = "";
        let selectedExternalProvider = "";
        let removeMedia = false;

        function setError(message) {
            errorEl.textContent = message || "";
            errorEl.classList.toggle("hidden", !message);
        }

        function updateCount() {
            countEl.textContent = String(contentInput.value.length);
        }

        function revokePreview() {
            if (selectedPreviewUrl) URL.revokeObjectURL(selectedPreviewUrl);
            selectedPreviewUrl = "";
        }

        function currentPreviewUrl() {
            if (selectedPreviewUrl) return selectedPreviewUrl;
            if (selectedExternalUrl) return selectedExternalUrl;
            if (!removeMedia && originalMedia?.url) return originalMedia.url;
            return "";
        }

        function syncMediaPreview() {
            const previewUrl = currentPreviewUrl();
            if (previewUrl) {
                previewImg.src = previewUrl;
                previewWrap.classList.remove("hidden");
                removeMediaBtn.classList.remove("hidden");
            } else {
                previewImg.src = "";
                previewWrap.classList.add("hidden");
                removeMediaBtn.classList.add("hidden");
            }
            clearMediaBtn.classList.toggle("hidden", !selectedFile && !selectedExternalUrl && !removeMedia);
        }

        function resetReplacement() {
            revokePreview();
            selectedFile = null;
            selectedExternalUrl = "";
            selectedExternalProvider = "";
            removeMedia = false;
            fileInput.value = "";
            syncMediaPreview();
        }

        function openEditor(article) {
            activeArticle = article;
            activePostId = Number(article?.dataset?.timelinePostId || 0);
            originalMedia = article?.dataset?.postMediaUrl ? {
                url: article.dataset.postMediaUrl,
                content_type: article.dataset.postMediaContentType || "",
                provider: article.dataset.postMediaProvider || "",
            } : null;
            contentInput.value = article?.dataset?.postContent || "";
            resetReplacement();
            updateCount();
            setError("");
            modal.classList.remove("hidden");
            document.body.style.overflow = "hidden";
            window.setTimeout(() => contentInput.focus(), 40);
        }

        function closeEditor() {
            modal.classList.add("hidden");
            document.body.style.overflow = "";
            activeArticle = null;
            activePostId = null;
            originalMedia = null;
            resetReplacement();
            setError("");
        }

        function setMediaFile(file) {
            if (!file) return;
            if (!uploadTypes.has(file.type)) {
                setError("Chỉ chấp nhận ảnh JPG, PNG, WebP. GIF hãy chọn từ GIPHY.");
                return;
            }
            if (file.size > maxBytes) {
                setError("Ảnh quá lớn, tối đa 8MB.");
                return;
            }
            revokePreview();
            selectedFile = file;
            selectedExternalUrl = "";
            selectedExternalProvider = "";
            removeMedia = false;
            selectedPreviewUrl = URL.createObjectURL(file);
            setError("");
            syncMediaPreview();
        }

        function setExternalMedia(media) {
            const url = String(media?.url || "").trim();
            const provider = String(media?.provider || "").trim().toLowerCase();
            if (!url || provider !== "giphy") {
                setError("Không thể chọn GIF lúc này.");
                return;
            }
            revokePreview();
            selectedFile = null;
            selectedExternalUrl = url;
            selectedExternalProvider = provider;
            removeMedia = false;
            fileInput.value = "";
            setError("");
            syncMediaPreview();
        }

        function buildRequestOptions() {
            if (selectedFile) {
                const form = new FormData();
                form.append("content", contentInput.value);
                form.append("media", selectedFile);
                return { method: "PATCH", body: form };
            }
            const payload = { content: contentInput.value };
            if (selectedExternalUrl && selectedExternalProvider) {
                payload.external_media_url = selectedExternalUrl;
                payload.external_media_provider = selectedExternalProvider;
            } else if (removeMedia) {
                payload.remove_media = true;
            }
            return {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            };
        }

        async function submitEdit() {
            if (!activePostId || saveBtn.disabled) return;
            const hasMediaAfterSave = Boolean(selectedFile || selectedExternalUrl || (!removeMedia && originalMedia?.url));
            if (!contentInput.value.trim() && !hasMediaAfterSave) {
                setError("Bài viết phải có nội dung hoặc media.");
                return;
            }

            saveBtn.disabled = true;
            const oldText = saveBtn.textContent;
            saveBtn.textContent = "Đang lưu...";
            setError("");

            try {
                const response = await fetch(`/api/v1/me/statuses/${encodeURIComponent(activePostId)}`, {
                    ...buildRequestOptions(),
                    cache: "no-store",
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || `Lỗi ${response.status}`);
                if (data.status_post && activeArticle) {
                    const options = typeof config.getOptions === "function" ? config.getOptions() : {};
                    activeArticle.outerHTML = createTimelineItemHtml(data.status_post, options);
                }
                config.onPostUpdated?.(data);
                closeEditor();
            } catch (error) {
                setError(error.message || "Không thể lưu bài viết.");
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = oldText;
            }
        }

        container.addEventListener("click", event => {
            const editBtn = event.target.closest("[data-timeline-action='edit']");
            if (!editBtn || !container.contains(editBtn)) return;
            const article = editBtn.closest("[data-timeline-post-id]");
            if (article) openEditor(article);
        });
        contentInput.addEventListener("input", () => {
            updateCount();
            setError("");
        });
        chooseMediaBtn.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", () => setMediaFile(fileInput.files?.[0]));
        removeMediaBtn.addEventListener("click", () => {
            revokePreview();
            selectedFile = null;
            selectedExternalUrl = "";
            selectedExternalProvider = "";
            removeMedia = true;
            fileInput.value = "";
            syncMediaPreview();
        });
        clearMediaBtn.addEventListener("click", resetReplacement);
        saveBtn.addEventListener("click", submitEdit);
        cancelBtn.addEventListener("click", closeEditor);
        closeBtn.addEventListener("click", closeEditor);
        modal.addEventListener("click", event => {
            if (event.target === modal) closeEditor();
        });

        window.GiphyPicker?.init({
            openButtonId: "open-timeline-edit-giphy",
            modalId: "timeline-edit-giphy-modal",
            closeButtonId: "close-timeline-edit-giphy",
            searchInputId: "timeline-edit-giphy-search-input",
            searchButtonId: "timeline-edit-giphy-search-button",
            resultsId: "timeline-edit-giphy-results",
            statusId: "timeline-edit-giphy-status",
            onSelect: setExternalMedia,
        });
    }

    window.TimelineFeed = {
        render,
        append,
        prepend,
        createTimelineItemHtml,
        renderInteractions,
        initEditor,
    };
})();
