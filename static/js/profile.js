const PROFILE_NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };

let viewerData = null;
let profileData = null;
let profileBets = [];
let selectedReactionBet = null;
let selectedAvatarFile = null;
let timelineNextOffset = 0;
let timelineLoading = false;
let pointTransactions = [];
let pointHistoryNextOffset = 0;
let pointHistoryLoading = false;

const PROFILE_USER_ID = new URLSearchParams(window.location.search).get("user_id") || "";
const IS_OWN_PROFILE = !PROFILE_USER_ID;
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

function normalizeImageSrc(value) {
    const src = String(value ?? "").trim();
    if (!src) return "";
    if (src.startsWith("/") || /^https?:\/\//i.test(src)) return src;
    return "";
}

function safeImageSrc(value) {
    return escapeHtml(normalizeImageSrc(value));
}

function safeCssColor(value) {
    const color = String(value ?? "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
}

function formatCoins(value) {
    return `${Number(value || 0).toLocaleString()}đ`;
}

function formatProfileTime(value) {
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

function renderBadge(badge) {
    if (!badge) return "";
    return `<span class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-bold ${
        badge.color === "gold" ? "border-amber-200 bg-amber-50 text-amber-700" :
        badge.color === "purple" ? "border-violet-200 bg-violet-50 text-violet-700" :
        badge.color === "red" ? "border-rose-200 bg-rose-50 text-rose-700" :
        "border-slate-200 bg-slate-50 text-slate-700"
    }">${escapeHtml(badge.emoji)} ${escapeHtml(badge.label)}</span>`;
}

function renderHeaderUserInfo() {
    const host = document.getElementById("user-info");
    if (!host || !viewerData) return;
    window.UserShell?.renderUserInfo?.(host, viewerData);
}

function applyNavState() {
    const profileLink = document.getElementById("nav-profile");
    const profileLabel = document.getElementById("nav-profile-label");
    if (!profileLink || !profileLabel) return;
    const isActiveProfile = IS_OWN_PROFILE && profileData?.can_edit !== false;
    profileLink.classList.toggle("text-sky-600", isActiveProfile);
    profileLink.classList.toggle("text-slate-500", !isActiveProfile);
    profileLink.classList.toggle("hover:text-sky-600", !isActiveProfile);
    profileLabel.classList.toggle("font-semibold", isActiveProfile);
}

function renderAvatar({ avatar_url, avatar_color, initials }) {
    const initialsEl = document.getElementById("avatar-initials");
    const imgEl = document.getElementById("avatar-img");
    if (!initialsEl || !imgEl) return;
    const avatarSrc = normalizeImageSrc(avatar_url);
    if (avatarSrc) {
        imgEl.src = avatarSrc;
        imgEl.classList.remove("hidden");
        initialsEl.classList.add("hidden");
        return;
    }
    initialsEl.textContent = initials || "??";
    initialsEl.style.background = safeCssColor(avatar_color);
    initialsEl.classList.remove("hidden");
    imgEl.classList.add("hidden");
}

function applyProfileUI() {
    if (!profileData) return;
    const fallbackName = profileData.email ? profileData.email.split("@")[0] : (profileData.initials || "User");
    const shortName = profileData.display_name || fallbackName;
    const emailEl = document.getElementById("profile-email");
    const badgeHost = document.getElementById("profile-badge");
    const editable = profileData.can_edit !== false;

    document.getElementById("profile-name").textContent = shortName;
    document.getElementById("profile-points").textContent = Number(profileData.total_points || 0).toLocaleString();
    if (emailEl) {
        emailEl.textContent = editable && profileData.email ? profileData.email : "";
        emailEl.classList.toggle("hidden", !(editable && profileData.email));
    }
    if (badgeHost) {
        badgeHost.innerHTML = renderBadge(profileData.badge);
    }

    document.getElementById("open-avatar-modal")?.classList.toggle("hidden", !editable);
    document.getElementById("open-name-modal")?.classList.toggle("hidden", !editable);
    document.getElementById("profile-composer-section")?.classList.toggle("hidden", !editable);
    document.getElementById("open-point-history-sheet")?.classList.toggle("hidden", !editable);

    const caption = document.getElementById("timeline-caption");
    if (caption) {
        caption.textContent = editable
            ? "Hồi ký của một dân chơi"
            : "Hành trình giác ngộ";
    }

    renderAvatar(profileData);
    applyNavState();
}

function renderStats() {
    const finished = profileBets.filter(bet => String(bet.match_status || "").toLowerCase() === "finished" && bet.result_published);
    const wins = finished.filter(bet => Number(bet.points_earned || 0) > 0);
    const loses = finished.filter(bet => Number(bet.points_earned || 0) === 0);
    document.getElementById("stat-total").textContent = String(profileBets.length);
    document.getElementById("stat-win").textContent = String(wins.length);
    document.getElementById("stat-lose").textContent = String(loses.length);
}

function transactionBadgeHtml(item) {
    const type = String(item?.transaction_type || "");
    if (type === "legacy_balance_adjustment") {
        return `<span class="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700">Điều chỉnh lịch sử</span>`;
    }
    if (type === "admin_adjustment") {
        return `<span class="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">Admin chỉnh điểm</span>`;
    }
    if (type === "recharge_approved") {
        return `<span class="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">Nạp điểm</span>`;
    }
    if (type === "bet_reward") {
        return `<span class="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">Thưởng cược</span>`;
    }
    if (type === "bet_refund") {
        return `<span class="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-700">Hoàn điểm</span>`;
    }
    return `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">Đặt cược</span>`;
}

function renderTimelineState() {
    const container = document.getElementById("profile-status-timeline");
    const emptyEl = document.getElementById("timeline-empty");
    const loadMoreBtn = document.getElementById("timeline-load-more");
    if (!container || !emptyEl || !loadMoreBtn) return;
    emptyEl.classList.toggle("hidden", container.children.length > 0);
    loadMoreBtn.classList.toggle("hidden", timelineNextOffset === null);
    loadMoreBtn.disabled = timelineLoading;
    loadMoreBtn.textContent = timelineLoading ? "Đang tải..." : "Xem thêm";
}

function renderPointHistoryState() {
    const emptyEl = document.getElementById("point-history-empty");
    const loadMoreBtn = document.getElementById("point-history-load-more");
    const listEl = document.getElementById("point-history-list");
    if (!emptyEl || !loadMoreBtn || !listEl) return;
    emptyEl.classList.toggle("hidden", pointTransactions.length > 0);
    loadMoreBtn.classList.toggle("hidden", pointHistoryNextOffset === null);
    loadMoreBtn.disabled = pointHistoryLoading;
    loadMoreBtn.textContent = pointHistoryLoading ? "Đang tải..." : "Xem thêm";
}

function renderHistoryState() {
    const emptyEl = document.getElementById("history-empty");
    const listEl = document.getElementById("history-bet-list");
    if (!emptyEl || !listEl) return;
    emptyEl.classList.toggle("hidden", profileBets.length > 0);
}

function setComposerStatus(message, tone = "neutral") {
    const statusEl = document.getElementById("default-taunt-status");
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.className = "text-xs";
    if (tone === "error") {
        statusEl.classList.add("text-rose-600");
    } else if (tone === "success") {
        statusEl.classList.add("text-emerald-600");
    } else {
        statusEl.classList.add("text-slate-500");
    }
}

function updateComposerCount() {
    const input = document.getElementById("default-taunt-input");
    const count = document.getElementById("default-taunt-count");
    if (!input || !count) return;
    count.textContent = String(input.value.length);
}

function getSelectedMatchSummary(bet) {
    return `${bet.home_team} ${Number(bet.home_score ?? 0)} - ${Number(bet.away_score ?? 0)} ${bet.away_team}`;
}

function syncSelectedMatchContext() {
    const contextEl = document.getElementById("selected-match-context");
    const summaryEl = document.getElementById("selected-match-summary");
    if (!contextEl || !summaryEl) return;
    if (!selectedReactionBet) {
        contextEl.classList.add("hidden");
        summaryEl.textContent = "";
        return;
    }
    contextEl.classList.remove("hidden");
    summaryEl.textContent = getSelectedMatchSummary(selectedReactionBet);
}

function openHistorySheet() {
    const sheet = document.getElementById("history-sheet");
    if (!sheet) return;
    sheet.classList.add("show");
    sheet.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
}

function openPointHistorySheet() {
    const sheet = document.getElementById("point-history-sheet");
    if (!sheet) return;
    sheet.classList.add("show");
    sheet.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    if (!pointTransactions.length && pointHistoryNextOffset !== null) {
        fetchPointHistory(true);
    }
}

function closeHistorySheet() {
    const sheet = document.getElementById("history-sheet");
    if (!sheet) return;
    sheet.classList.remove("show");
    sheet.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
}

function closePointHistorySheet() {
    const sheet = document.getElementById("point-history-sheet");
    if (!sheet) return;
    sheet.classList.remove("show");
    sheet.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
}

function historyBadgeHtml(bet) {
    const isFinished = String(bet.match_status || "").toLowerCase() === "finished";
    const isWin = isFinished && Number(bet.points_earned || 0) > 0;
    if (!isFinished || !bet.result_published) {
        return `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">Chờ kết quả</span>`;
    }
    if (bet.points_earned === null) {
        return `<span class="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">Hoàn điểm</span>`;
    }
    if (isWin) {
        return `<span class="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">✅ Thắng</span>`;
    }
    return `<span class="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-700">❌ Thua</span>`;
}

function renderHistoryList() {
    const listEl = document.getElementById("history-bet-list");
    const errorEl = document.getElementById("history-sheet-error");
    if (!listEl || !errorEl) return;
    errorEl.classList.add("hidden");
    if (!profileBets.length) {
        listEl.innerHTML = "";
        renderHistoryState();
        return;
    }

    listEl.innerHTML = profileBets.map(bet => {
        const homeIcon = safeImageSrc(bet.home_icon)
            ? `<img src="${safeImageSrc(bet.home_icon)}" alt="" class="h-5 w-5 rounded-full border border-slate-200 object-cover">`
            : "";
        const awayIcon = safeImageSrc(bet.away_icon)
            ? `<img src="${safeImageSrc(bet.away_icon)}" alt="" class="h-5 w-5 rounded-full border border-slate-200 object-cover">`
            : "";
        const canShare = Boolean(profileData?.can_edit) && Boolean(bet.can_share_reaction);
        return `
            <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <button type="button" data-open-match="${bet.match_id}" class="block w-full overflow-hidden text-left">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0 flex-1">
                            <div class="flex min-w-0 flex-wrap items-center gap-2">
                                ${homeIcon}
                                <div class="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900">${escapeHtml(bet.home_team)}</div>
                                <div class="flex-shrink-0 text-xs font-black text-slate-400">${escapeHtml(bet.result_published ? `${Number(bet.home_score ?? 0)} - ${Number(bet.away_score ?? 0)}` : "vs")}</div>
                                <div class="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900">${escapeHtml(bet.away_team)}</div>
                                ${awayIcon}
                            </div>
                            <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                ${historyBadgeHtml(bet)}
                                <span>Chọn: <strong class="text-slate-700">${escapeHtml(({ HOME: "Chủ nhà", DRAW: "Hòa", AWAY: "Khách" }[bet.choice] || bet.choice))}</strong></span>
                                <span>•</span>
                                <span>Đặt ${formatCoins(bet.stake)}</span>
                            </div>
                            <div class="mt-1 text-[11px] text-slate-400">Trận ${escapeHtml(formatProfileTime(bet.start_time))} • Đặt ${escapeHtml(formatProfileTime(bet.created_at))}</div>
                        </div>
                        <div class="flex-shrink-0 text-right">
                            <div class="text-sm font-black text-[#D3af37]">${bet.points_earned === null ? "—" : `${Number(bet.points_earned || 0) > 0 ? "+" : ""}${formatCoins(Math.abs(Number(bet.points_earned || 0)))}`}</div>
                            <div class="text-[11px] text-slate-400">Chi tiết</div>
                        </div>
                    </div>
                </button>
                ${canShare ? `
                    <div class="mt-3 border-t border-slate-100 pt-3">
                        <button
                            type="button"
                            data-share-bet="${bet.bet_id}"
                            class="w-full rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-semibold text-sky-700 transition hover:bg-sky-100"
                        >
                            Chia sẻ cảm nghĩ trận này
                        </button>
                    </div>
                ` : ""}
                ${!canShare && bet.has_shared_reaction ? `
                    <div class="mt-3 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
                        Bạn đã chia sẻ cảm nghĩ cho trận này rồi.
                    </div>
                ` : ""}
            </article>
        `;
    }).join("");
    renderHistoryState();
}

function renderPointHistoryList() {
    const listEl = document.getElementById("point-history-list");
    if (!listEl) return;
    listEl.innerHTML = pointTransactions.map(item => {
        const match = item.match || {};
        const delta = Number(item.delta_points || 0);
        const tone = delta > 0 ? "text-emerald-600" : delta < 0 ? "text-rose-600" : "text-slate-600";
        const deltaLabel = `${delta > 0 ? "+" : ""}${formatCoins(Math.abs(delta))}`;
        const matchInfo = match?.id ? `
            <button type="button" data-open-match="${match.id}" class="mt-3 flex w-full items-center justify-between gap-3 rounded-2xl border border-sky-100 bg-sky-50 px-3 py-2 text-left transition hover:border-sky-200 hover:bg-sky-100">
                <div class="min-w-0 truncate text-xs font-semibold text-slate-700">${escapeHtml(match.home_team || "?")} vs ${escapeHtml(match.away_team || "?")}</div>
                <div class="text-[11px] font-semibold text-sky-700">Xem trận</div>
            </button>
        ` : "";
        return `
            <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                        <div class="flex flex-wrap items-center gap-2">
                            ${transactionBadgeHtml(item)}
                            ${item.is_backfilled ? `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500">Backfill</span>` : ""}
                        </div>
                        <div class="mt-2 text-sm font-semibold text-slate-900">${escapeHtml(item.description || item.transaction_type_label || "Giao dịch điểm")}</div>
                        <div class="mt-1 text-[11px] text-slate-400">${escapeHtml(formatProfileTime(item.created_at))}</div>
                        ${item.actor ? `<div class="mt-1 text-[11px] text-slate-500">Thực hiện bởi: <strong class="text-slate-700">${escapeHtml(item.actor.display_name || item.actor.email || "Admin")}</strong></div>` : ""}
                        ${matchInfo}
                    </div>
                    <div class="flex-shrink-0 text-right">
                        <div class="text-sm font-black ${tone}">${delta > 0 ? "+" : delta < 0 ? "-" : ""}${formatCoins(Math.abs(delta))}</div>
                        <div class="mt-1 text-[11px] text-slate-400">Số dư ${formatCoins(item.balance_after || 0)}</div>
                    </div>
                </div>
            </article>
        `;
    }).join("");
    renderPointHistoryState();
}

async function fetchViewerProfile() {
    const host = document.getElementById("user-info");
    try {
        const res = await fetch("/api/v1/me", PROFILE_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        viewerData = await res.json();
        renderHeaderUserInfo();
    } catch (error) {
        console.error("fetchViewerProfile error:", error);
        if (host) {
            host.textContent = "Lỗi tải dữ liệu";
        }
    }
}

async function fetchProfile() {
    try {
        const url = PROFILE_USER_ID
            ? `/api/v1/users/${encodeURIComponent(PROFILE_USER_ID)}`
            : "/api/v1/me";
        const res = await fetch(url, PROFILE_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        profileData = await res.json();
        applyProfileUI();
    } catch (error) {
        console.error("fetchProfile error:", error);
    }
}

async function fetchBetHistory() {
    const errorEl = document.getElementById("history-sheet-error");
    try {
        const url = PROFILE_USER_ID
            ? `/api/v1/users/${encodeURIComponent(PROFILE_USER_ID)}/bets`
            : "/api/v1/me/bets";
        const res = await fetch(url, PROFILE_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        profileBets = await res.json();
        renderStats();
        renderHistoryList();
    } catch (error) {
        console.error("fetchBetHistory error:", error);
        profileBets = [];
        renderStats();
        renderHistoryList();
        if (errorEl) {
            errorEl.textContent = "Không thể tải lịch sử cược lúc này.";
            errorEl.classList.remove("hidden");
        }
    }
}

async function fetchTimeline(reset = false) {
    const container = document.getElementById("profile-status-timeline");
    const errorEl = document.getElementById("timeline-error");
    if (!container || timelineLoading) return;
    if (reset) {
        timelineNextOffset = 0;
        container.innerHTML = "";
    }

    timelineLoading = true;
    renderTimelineState();
    if (errorEl) {
        errorEl.textContent = "";
        errorEl.classList.add("hidden");
    }

    try {
        const offset = timelineNextOffset ?? 0;
        const url = PROFILE_USER_ID
            ? `/api/v1/users/${encodeURIComponent(PROFILE_USER_ID)}/timeline?offset=${offset}&limit=10`
            : `/api/v1/me/timeline?offset=${offset}&limit=10`;
        const res = await fetch(url, PROFILE_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];

        if (reset) {
            window.TimelineFeed?.render(container, items, {});
        } else {
            window.TimelineFeed?.append(container, items, {});
        }
        timelineNextOffset = data.next_offset ?? null;
    } catch (error) {
        console.error("fetchTimeline error:", error);
        if (errorEl) {
            errorEl.textContent = "Không thể tải dòng thời gian lúc này.";
            errorEl.classList.remove("hidden");
        }
    } finally {
        timelineLoading = false;
        renderTimelineState();
    }
}

async function fetchPointHistory(reset = false) {
    const errorEl = document.getElementById("point-history-sheet-error");
    if (pointHistoryLoading || !IS_OWN_PROFILE) return;
    if (reset) {
        pointHistoryNextOffset = 0;
        pointTransactions = [];
    }
    pointHistoryLoading = true;
    renderPointHistoryState();
    if (errorEl) {
        errorEl.textContent = "";
        errorEl.classList.add("hidden");
    }
    try {
        const offset = pointHistoryNextOffset ?? 0;
        const res = await fetch(`/api/v1/me/point-transactions?offset=${offset}&limit=10`, PROFILE_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];
        pointTransactions = reset ? items : pointTransactions.concat(items);
        pointHistoryNextOffset = data.next_offset ?? null;
        renderPointHistoryList();
    } catch (error) {
        console.error("fetchPointHistory error:", error);
        if (errorEl) {
            errorEl.textContent = "Không thể tải lịch sử điểm lúc này.";
            errorEl.classList.remove("hidden");
        }
    } finally {
        pointHistoryLoading = false;
        renderPointHistoryState();
    }
}

function initHistorySheet() {
    document.getElementById("open-history-sheet")?.addEventListener("click", openHistorySheet);
    document.getElementById("close-history-sheet")?.addEventListener("click", closeHistorySheet);
    document.getElementById("open-point-history-sheet")?.addEventListener("click", openPointHistorySheet);
    document.getElementById("close-point-history-sheet")?.addEventListener("click", closePointHistorySheet);
    document.getElementById("history-sheet")?.addEventListener("click", event => {
        if (event.target?.id === "history-sheet") {
            closeHistorySheet();
        }
    });
    document.getElementById("point-history-sheet")?.addEventListener("click", event => {
        if (event.target?.id === "point-history-sheet") {
            closePointHistorySheet();
        }
    });
    document.getElementById("history-bet-list")?.addEventListener("click", event => {
        const matchButton = event.target.closest("[data-open-match]");
        if (matchButton) {
            openMatchDetail(Number(matchButton.dataset.openMatch), true);
            return;
        }
        const shareButton = event.target.closest("[data-share-bet]");
        if (shareButton) {
            const betId = Number(shareButton.dataset.shareBet);
            selectedReactionBet = profileBets.find(bet => Number(bet.bet_id) === betId) || null;
            syncSelectedMatchContext();
            closeHistorySheet();
            document.getElementById("default-taunt-input")?.focus();
        }
    });
    document.getElementById("point-history-list")?.addEventListener("click", event => {
        const matchButton = event.target.closest("[data-open-match]");
        if (matchButton) {
            openMatchDetail(Number(matchButton.dataset.openMatch), true);
        }
    });
}

function initComposer() {
    const input = document.getElementById("default-taunt-input");
    const saveBtn = document.getElementById("save-profile-status");
    if (!input || !saveBtn) return;

    input.addEventListener("input", () => {
        updateComposerCount();
        setComposerStatus("");
    });

    document.getElementById("clear-selected-match")?.addEventListener("click", () => {
        selectedReactionBet = null;
        syncSelectedMatchContext();
    });

    saveBtn.addEventListener("click", async () => {
        if (!profileData || profileData.can_edit === false) return;
        if (input.value.length > Number(input.maxLength || 160)) {
            setComposerStatus(`Tối đa ${input.maxLength} ký tự.`, "error");
            return;
        }

        saveBtn.disabled = true;
        const oldText = saveBtn.textContent;
        saveBtn.textContent = "Đang đăng...";
        setComposerStatus("");

        try {
            const payload = { content: input.value };
            if (selectedReactionBet?.match_id) {
                payload.match_id = Number(selectedReactionBet.match_id);
            }

            const res = await fetch("/api/v1/me/statuses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `Lỗi ${res.status}`);

            input.value = "";
            updateComposerCount();
            setComposerStatus("Đã đăng bài mới.", "success");

            if (selectedReactionBet?.match_id) {
                profileBets = profileBets.map(bet => Number(bet.match_id) === Number(selectedReactionBet.match_id)
                    ? { ...bet, can_share_reaction: false, has_shared_reaction: true }
                    : bet);
                renderHistoryList();
            }

            selectedReactionBet = null;
            syncSelectedMatchContext();
            await fetchTimeline(true);
        } catch (error) {
            setComposerStatus(error.message || "Không thể đăng bài.", "error");
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = oldText;
        }
    });

    updateComposerCount();
    syncSelectedMatchContext();
}

function initAvatarModal() {
    const modal = document.getElementById("avatar-modal");
    const openBtn = document.getElementById("open-avatar-modal");
    const closeBtn = document.getElementById("close-avatar-modal");
    const cancelBtn = document.getElementById("btn-avatar-cancel");
    const saveBtn = document.getElementById("btn-avatar-save");
    const dropZone = document.getElementById("avatar-drop-zone");
    const fileInput = document.getElementById("avatar-file-input");
    const preview = document.getElementById("avatar-preview");
    const hint = document.getElementById("drop-hint");
    const errorEl = document.getElementById("avatar-error");
    const progressEl = document.getElementById("avatar-progress");
    if (!modal || !openBtn || !closeBtn || !cancelBtn || !saveBtn || !dropZone || !fileInput || !preview || !hint || !errorEl || !progressEl) {
        return;
    }

    const open = () => {
        if (profileData?.can_edit === false) return;
        modal.classList.add("show");
        reset();
    };
    const close = () => {
        modal.classList.remove("show");
        reset();
    };
    const reset = () => {
        selectedAvatarFile = null;
        preview.classList.remove("show");
        preview.src = "";
        hint.style.display = "";
        saveBtn.disabled = true;
        errorEl.classList.add("hidden");
        errorEl.textContent = "";
        progressEl.classList.remove("show");
        fileInput.value = "";
    };
    const setFile = file => {
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            errorEl.textContent = "Chỉ chấp nhận file ảnh.";
            errorEl.classList.remove("hidden");
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            errorEl.textContent = "Ảnh quá lớn, tối đa 5MB.";
            errorEl.classList.remove("hidden");
            return;
        }
        selectedAvatarFile = file;
        const reader = new FileReader();
        reader.onload = event => {
            preview.src = event.target.result;
            preview.classList.add("show");
            hint.style.display = "none";
        };
        reader.readAsDataURL(file);
        saveBtn.disabled = false;
        errorEl.classList.add("hidden");
    };

    openBtn.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    cancelBtn.addEventListener("click", close);
    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });

    dropZone.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("dragover", event => {
        event.preventDefault();
        dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", event => {
        event.preventDefault();
        dropZone.classList.remove("dragover");
        setFile(event.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

    saveBtn.addEventListener("click", async () => {
        if (!selectedAvatarFile) return;
        saveBtn.disabled = true;
        progressEl.classList.add("show");
        errorEl.classList.add("hidden");

        try {
            const form = new FormData();
            form.append("file", selectedAvatarFile);
            const res = await fetch("/api/v1/me/avatar", { method: "POST", body: form });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || `Lỗi ${res.status}`);
            }
            const { avatar_url } = await res.json();
            profileData = { ...profileData, avatar_url: normalizeImageSrc(avatar_url) };
            if (viewerData) {
                viewerData = { ...viewerData, avatar_url: normalizeImageSrc(avatar_url) };
                renderHeaderUserInfo();
            }
            applyProfileUI();
            close();
        } catch (error) {
            errorEl.textContent = error.message || "Lỗi không xác định.";
            errorEl.classList.remove("hidden");
            saveBtn.disabled = false;
            progressEl.classList.remove("show");
        }
    });
}

function initNameModal() {
    const modal = document.getElementById("name-modal");
    const openBtn = document.getElementById("open-name-modal");
    const closeBtn = document.getElementById("close-name-modal");
    const cancelBtn = document.getElementById("btn-name-cancel");
    const saveBtn = document.getElementById("btn-name-save");
    const input = document.getElementById("name-input");
    const counter = document.getElementById("name-char-count");
    const errorEl = document.getElementById("name-error");
    if (!modal || !openBtn || !closeBtn || !cancelBtn || !saveBtn || !input || !counter || !errorEl) {
        return;
    }

    const open = () => {
        if (profileData?.can_edit === false) return;
        modal.classList.add("show");
        input.value = profileData?.display_name || "";
        counter.textContent = String(input.value.length);
        errorEl.classList.add("hidden");
        setTimeout(() => input.focus(), 60);
    };
    const close = () => modal.classList.remove("show");

    openBtn.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    cancelBtn.addEventListener("click", close);
    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });

    input.addEventListener("input", () => {
        const length = input.value.length;
        counter.textContent = String(length);
        counter.parentElement.classList.toggle("warn", length > 25);
    });

    saveBtn.addEventListener("click", async () => {
        const name = input.value.trim();
        if (!name) {
            errorEl.textContent = "Tên không được để trống.";
            errorEl.classList.remove("hidden");
            return;
        }
        if (name.length > 30) {
            errorEl.textContent = "Tối đa 30 ký tự.";
            errorEl.classList.remove("hidden");
            return;
        }

        saveBtn.disabled = true;
        const oldText = saveBtn.textContent;
        saveBtn.textContent = "Đang lưu...";
        errorEl.classList.add("hidden");

        try {
            const res = await fetch("/api/v1/me/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ display_name: name }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `Lỗi ${res.status}`);

            profileData = { ...profileData, ...data };
            if (viewerData) {
                viewerData = { ...viewerData, display_name: data.display_name };
                renderHeaderUserInfo();
            }
            applyProfileUI();
            close();
        } catch (error) {
            errorEl.textContent = error.message || "Không thể đổi tên.";
            errorEl.classList.remove("hidden");
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = oldText;
        }
    });
}

document.addEventListener("DOMContentLoaded", async () => {
    initHistorySheet();
    initComposer();
    initAvatarModal();
    initNameModal();
    document.getElementById("timeline-load-more")?.addEventListener("click", () => fetchTimeline(false));
    document.getElementById("point-history-load-more")?.addEventListener("click", () => fetchPointHistory(false));

    await fetchViewerProfile();
    await fetchProfile();
    await fetchBetHistory();
    await fetchTimeline(true);
    renderPointHistoryState();
});
