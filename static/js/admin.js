const state = {
    overview: null,
    settings: {
        points_enabled: true,
        homepage_announcement: "",
    },
    users: [],
    matches: [],
    pointTransactionsByUser: {},
    userSearch: "",
    activeTab: "overview",
    toastTimer: null,
    countryCodeOptions: [],
    countryCodeLookup: {},
};

const MATCH_DEFAULT_DURATION_MINUTES = 120;
const FLAG_CDN_PREFIX = "https://flagcdn.com/128x96/";
const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";

document.addEventListener("DOMContentLoaded", () => {
    loadCountryCodeOptions();
    renderCountryCodeDatalist();
    renderCountryNameDatalist();
    bindTabs();
    bindActions();
    bindMatchFormControls();
    document.getElementById("match-form")?.addEventListener("submit", saveMatch);
    fetchInitialData();
});

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

function normalizeCountryCode(value) {
    return String(value ?? "")
        .toUpperCase()
        .replace(/[^A-Z0-9-]/g, "")
        .replace(/-+/g, "-")
        .replace(/^-+|-+$/g, "");
}

function normalizeCountryName(value) {
    return String(value ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
}

function loadCountryCodeOptions() {
    const source = document.getElementById("country-code-options-data");
    if (!source) return;
    try {
        const parsed = JSON.parse(source.textContent || "[]");
        state.countryCodeOptions = Array.isArray(parsed) ? parsed : [];
        state.countryCodeLookup = state.countryCodeOptions.reduce((acc, item) => {
            const code = normalizeCountryCode(item?.code || "");
            const name = String(item?.name || "").trim();
            if (code && name) acc[code] = name;
            return acc;
        }, {});
    } catch {
        state.countryCodeOptions = [];
        state.countryCodeLookup = {};
    }
}

function renderCountryCodeDatalist() {
    const datalist = document.getElementById("country-code-options");
    if (!datalist) return;
    datalist.innerHTML = state.countryCodeOptions.map(item => `
        <option value="${escapeHtml(normalizeCountryCode(item.code))}">${escapeHtml(item.name)}</option>
    `).join("");
}

function renderCountryNameDatalist() {
    const datalist = document.getElementById("country-name-options");
    if (!datalist) return;
    datalist.innerHTML = state.countryCodeOptions.map(item => `
        <option value="${escapeHtml(item.name)}">${escapeHtml(normalizeCountryCode(item.code))}</option>
    `).join("");
}

function extractCountryCode(value) {
    const src = String(value ?? "").trim();
    if (!src) return "";
    const direct = src.match(/flagcdn\.com\/128x96\/([a-z0-9-]+)\.png/i);
    if (direct) return direct[1].toUpperCase();
    try {
        const url = new URL(src);
        const filename = url.pathname.split("/").filter(Boolean).pop() || "";
        const code = filename.replace(/\.png$/i, "");
        return /^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(code) ? code.toUpperCase() : "";
    } catch {
        return "";
    }
}

function buildFlagUrl(countryCode) {
    const code = normalizeCountryCode(countryCode).toLowerCase();
    return code ? `${FLAG_CDN_PREFIX}${code}.png` : "";
}

function safeCssColor(value) {
    const color = String(value ?? "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString("vi-VN");
}

function formatCoins(value) {
    return `${formatNumber(value)}đ`;
}

function pointTransactionBadge(item) {
    const type = String(item?.transaction_type || "");
    if (type === "legacy_balance_adjustment") return "border-violet-500/30 bg-violet-500/10 text-violet-200";
    if (type === "admin_adjustment") return "border-amber-500/30 bg-amber-500/10 text-amber-200";
    if (type === "recharge_approved") return "border-violet-500/30 bg-violet-500/10 text-violet-200";
    if (type === "bet_reward") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
    if (type === "bet_refund") return "border-sky-500/30 bg-sky-500/10 text-sky-200";
    return "border-slate-700 bg-slate-900 text-slate-300";
}

function getVNDateParts(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return Object.fromEntries(
        new Intl.DateTimeFormat("en-CA", {
            timeZone: APP_TIME_ZONE,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        }).formatToParts(date)
            .filter(part => part.type !== "literal")
            .map(part => [part.type, part.value])
    );
}

function formatDateTime(value) {
    if (!value) return "Chưa có dữ liệu";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Không hợp lệ";
    return new Intl.DateTimeFormat("vi-VN", {
        timeZone: APP_TIME_ZONE,
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
    }).format(date);
}

function formatDateLabel(value) {
    if (!value) return "Chưa rõ ngày";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Không hợp lệ";
    return new Intl.DateTimeFormat("vi-VN", {
        timeZone: APP_TIME_ZONE,
        weekday: "long",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
    }).format(date);
}

function localDateValue(value) {
    const parts = getVNDateParts(value);
    return parts ? `${parts.year}-${parts.month}-${parts.day}` : "";
}

function localTimeValue(value) {
    const parts = getVNDateParts(value);
    return parts ? `${parts.hour}:${parts.minute}` : "";
}

function todayDateValue() {
    const now = new Date();
    const parts = getVNDateParts(now.toISOString());
    return parts ? `${parts.year}-${parts.month}-${parts.day}` : "";
}

function localDateTimeValueFromParts(dateValue, timeValue, addMinutes = 0) {
    if (!dateValue || !timeValue) return "";
    const [year, month, day] = dateValue.split("-").map(Number);
    const [hour, minute] = timeValue.split(":").map(Number);
    const date = new Date(year, month - 1, day, hour, minute + addMinutes, 0, 0);
    if (Number.isNaN(date.getTime())) return "";
    const pad = number => String(number).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function apiDateTimeValueFromParts(dateValue, timeValue) {
    const localValue = localDateTimeValueFromParts(dateValue, timeValue);
    return localValue ? apiDateTimeValue(localValue) : "";
}

function normalizeMatchStatus(value) {
    const raw = typeof value === "string"
        ? value
        : value && typeof value === "object" && "value" in value
            ? value.value
            : value;
    return String(raw || "").toLowerCase();
}

function renderMiniAvatar({ avatar_url, avatar_color, initials }) {
    const avatarSrc = safeImageSrc(avatar_url);
    if (avatarSrc) {
        return `<img src="${avatarSrc}" alt="" class="h-6 w-6 rounded-full border border-emerald-500/30 object-cover">`;
    }
    return `<span class="inline-flex h-6 w-6 items-center justify-center rounded-full border border-emerald-500/30 text-[10px] font-black text-white" style="background:${safeCssColor(avatar_color)}">${escapeHtml(initials || "??")}</span>`;
}

function bindTabs() {
    document.querySelectorAll("[data-tab-target]").forEach(btn => {
        btn.addEventListener("click", () => setActiveTab(btn.dataset.tabTarget));
    });
    document.getElementById("mobile-tab-trigger")?.addEventListener("click", toggleMobileTabMenu);
    updateMobileTabLabel(state.activeTab);
}

function setActiveTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll("[data-tab-target]").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.tabTarget === tabName);
    });
    document.querySelectorAll("[data-tab-panel]").forEach(panel => {
        panel.classList.toggle("hidden", panel.dataset.tabPanel !== tabName);
    });
    updateMobileTabLabel(tabName);
    closeMobileTabMenu();
}

function tabLabel(tabName) {
    const labels = {
        overview: "Tổng quan",
        users: "Người dùng",
        settings: "Cài đặt",
        matches: "Trận đấu",
    };
    return labels[tabName] || "Menu";
}

function updateMobileTabLabel(tabName) {
    const label = document.getElementById("mobile-tab-label");
    if (label) label.textContent = tabLabel(tabName);
}

function toggleMobileTabMenu() {
    const nav = document.getElementById("admin-tab-nav");
    const trigger = document.getElementById("mobile-tab-trigger");
    if (!nav || !trigger) return;
    const willOpen = !nav.classList.contains("is-open");
    nav.classList.toggle("is-open", willOpen);
    trigger.setAttribute("aria-expanded", String(willOpen));
}

function closeMobileTabMenu() {
    const nav = document.getElementById("admin-tab-nav");
    const trigger = document.getElementById("mobile-tab-trigger");
    if (!nav || !trigger) return;
    nav.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
}

function bindActions() {
    document.getElementById("quick-refresh-users")?.addEventListener("click", () => fetchUsers(""));
    document.getElementById("refresh-users")?.addEventListener("click", () => fetchUsers(state.userSearch));
    document.getElementById("save-settings")?.addEventListener("click", saveSettings);
    document.getElementById("cancel-edit-btn")?.addEventListener("click", () => {
        resetMatchForm();
        closeMatchComposer();
    });
    document.getElementById("open-match-composer")?.addEventListener("click", () => {
        resetMatchForm();
        openMatchComposer();
    });
    document.getElementById("close-match-composer")?.addEventListener("click", () => {
        resetMatchForm();
        closeMatchComposer();
    });

    const searchInput = document.getElementById("user-search");
    let debounceTimer = null;
    searchInput?.addEventListener("input", event => {
        state.userSearch = event.target.value.trim();
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => fetchUsers(state.userSearch), 250);
    });
}

function openMatchComposer(mode = "create") {
    const composer = document.getElementById("match-composer");
    const openButton = document.getElementById("open-match-composer");
    if (!composer) return;
    composer.classList.remove("is-collapsed");
    openButton?.classList.add("hidden");
    if (mode === "create") {
        document.getElementById("match-form-title").textContent = "Thêm trận đấu";
        document.getElementById("save-match-btn").textContent = "Lưu trận";
        const startDateInput = document.getElementById("start-date");
        if (startDateInput && !startDateInput.value) {
            startDateInput.value = todayDateValue();
            syncMatchEndTime();
        }
    }
}

function closeMatchComposer() {
    const composer = document.getElementById("match-composer");
    const openButton = document.getElementById("open-match-composer");
    if (!composer) return;
    composer.classList.add("is-collapsed");
    openButton?.classList.remove("hidden");
}

function bindMatchFormControls() {
    ["home-country-code", "away-country-code"].forEach(inputId => {
        const input = document.getElementById(inputId);
        if (!input) return;
        const previewId = inputId === "home-country-code" ? "home-flag-preview" : "away-flag-preview";
        const handleInput = () => {
            delete input.dataset.autoCountryCode;
            input.value = normalizeCountryCode(input.value);
            updateFlagPreview(previewId, input.value);
        };
        input.addEventListener("input", handleInput);
        input.addEventListener("blur", handleInput);
        updateFlagPreview(previewId, input.value);
    });

    [
        ["home-team", "home-country-code", "home-flag-preview"],
        ["away-team", "away-country-code", "away-flag-preview"],
    ].forEach(([teamInputId, countryInputId, previewId]) => {
        const teamInput = document.getElementById(teamInputId);
        const countryInput = document.getElementById(countryInputId);
        if (!teamInput || !countryInput) return;
        const suggest = () => suggestCountryCodeFromTeam(teamInput, countryInput, previewId);
        teamInput.addEventListener("input", suggest);
        teamInput.addEventListener("blur", suggest);
        teamInput.addEventListener("change", suggest);
    });

    ["start-date", "start-time"].forEach(inputId => {
        document.getElementById(inputId)?.addEventListener("input", syncMatchEndTime);
        document.getElementById(inputId)?.addEventListener("change", syncMatchEndTime);
    });
}

function updateFlagPreview(previewId, countryCode) {
    const preview = document.getElementById(previewId);
    if (!preview) return;
    const code = normalizeCountryCode(countryCode);
    const url = buildFlagUrl(code);
    const countryName = state.countryCodeLookup[code] || "";
    preview.innerHTML = url
        ? `${countryName ? `Quốc gia: <span class="font-medium text-emerald-300">${escapeHtml(countryName)}</span><br>` : ""}URL: <span class="break-all font-medium text-slate-200">${escapeHtml(url)}</span>`
        : "Flag URL sẽ tự sinh tại đây.";
}

function suggestCountryCodeFromTeam(teamInput, countryInput, previewId) {
    const teamName = String(teamInput.value || "").trim();
    const existingCode = normalizeCountryCode(countryInput.value);
    const previousAutoCode = normalizeCountryCode(countryInput.dataset.autoCountryCode || "");
    if (!teamName) {
        if (previousAutoCode && existingCode === previousAutoCode) {
            countryInput.value = "";
            delete countryInput.dataset.autoCountryCode;
            updateFlagPreview(previewId, "");
        }
        return;
    }
    const match = findCountryCodeByTeamName(teamName);
    if (!match) return;
    if (existingCode && existingCode !== previousAutoCode) return;
    countryInput.value = match.code;
    countryInput.dataset.autoCountryCode = match.code;
    updateFlagPreview(previewId, match.code);
}

function findCountryCodeByTeamName(teamName) {
    const normalizedTeam = normalizeCountryName(teamName);
    if (!normalizedTeam) return null;

    const exact = state.countryCodeOptions.find(item => normalizeCountryName(item.name) === normalizedTeam);
    if (exact) {
        return { code: normalizeCountryCode(exact.code), name: exact.name };
    }

    const contains = state.countryCodeOptions.find(item => {
        const normalizedCountry = normalizeCountryName(item.name);
        return normalizedCountry && (
            normalizedCountry.includes(normalizedTeam) ||
            normalizedTeam.includes(normalizedCountry)
        );
    });
    if (contains) {
        return { code: normalizeCountryCode(contains.code), name: contains.name };
    }

    return null;
}

function syncMatchEndTime() {
    const startDate = document.getElementById("start-date")?.value || "";
    const startTime = document.getElementById("start-time")?.value || "";
    const endTime = document.getElementById("end-time");
    if (!endTime) return;
    endTime.value = localDateTimeValueFromParts(startDate, startTime, MATCH_DEFAULT_DURATION_MINUTES) || "";
}

async function refreshAll() {
    await Promise.all([
        fetchOverview(),
        fetchSettings(),
        fetchUsers(state.userSearch),
        fetchMatches(),
    ]);
}

async function fetchInitialData() {
    await refreshAll();
}

async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.detail || `Lỗi ${res.status}`);
    }
    return data;
}

async function fetchOverview() {
    try {
        state.overview = await fetchJson("/api/v1/admin/overview");
        renderOverview();
    } catch (err) {
        showToast(err.message || "Không thể tải tổng quan.", "error");
    }
}

function renderOverview() {
    if (!state.overview) return;
    const walletPoints = Number(state.overview.wallet_points || 0);
    const lockedPoints = Number(state.overview.locked_points || 0);
    const metrics = [
        { label: "Tổng user", value: formatNumber(state.overview.total_users), tone: "text-emerald-300" },
        {
            label: "Điểm đang lưu thông",
            value: formatCoins(state.overview.total_points),
            tone: "text-amber-300",
            hint: `Ví user ${formatCoins(walletPoints)} + kèo chưa settle ${formatCoins(lockedPoints)}`,
        },
        { label: "Trận đang mở", value: formatNumber(state.overview.upcoming_matches), tone: "text-sky-300" },
        { label: "Lịch sử", value: formatNumber(state.overview.total_bets), tone: "text-pink-300" },
    ];

    document.getElementById("overview-metrics").innerHTML = metrics.map(metric => `
        <div class="metric-card rounded-3xl p-4 lg:p-5">
            <div class="text-xs uppercase tracking-[0.2em] text-slate-400">${metric.label}</div>
            <div class="mt-4 text-3xl font-black ${metric.tone}">${metric.value}</div>
            ${metric.hint ? `<div class="mt-2 text-xs leading-5 text-slate-400">${metric.hint}</div>` : ""}
        </div>
    `).join("");

    renderOverviewUsers();
    renderOverviewFeatures();
}

function renderOverviewUsers() {
    const list = document.getElementById("overview-user-list");
    const items = state.users.slice(0, 5);
    if (!items.length) {
        list.innerHTML = `<div class="rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-4 text-sm text-slate-400">Chưa có người dùng nào.</div>`;
        return;
    }

    list.innerHTML = items.map(user => `
        <div class="rounded-2xl border border-slate-800 bg-slate-950/50 px-4 py-3">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                    <div class="truncate font-semibold text-white">${escapeHtml(user.display_name || user.email.split("@")[0])}</div>
                    <div class="truncate text-xs text-slate-400">${escapeHtml(user.email)}</div>
                </div>
                <div class="text-right">
                    <div class="text-sm font-bold text-amber-300">${formatCoins(user.total_points)}</div>
                    <div class="text-[11px] text-slate-500">${user.bet_count} Lịch sử báo nhà</div>
                </div>
            </div>
        </div>
    `).join("");
}

function renderOverviewFeatures() {
    const container = document.getElementById("overview-features");
    const announcement = String(state.settings.homepage_announcement || "").trim();
    container.innerHTML = `
        <div class="rounded-2xl border ${announcement ? "border-sky-500/30 bg-sky-500/8" : "border-slate-800 bg-slate-950/50"} px-4 py-4">
            <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                    <div class="font-semibold text-white">Thong bao trang chu</div>
                    <div class="mt-1 text-sm ${announcement ? "text-sky-100" : "text-slate-400"}">${escapeHtml(announcement || "Chua co thong bao hien thi cho user.")}</div>
                </div>
                <span class="rounded-full px-3 py-1 text-xs font-semibold ${announcement ? "bg-sky-500/15 text-sky-200" : "bg-slate-800 text-slate-300"}">
                    ${announcement ? "Dang hien" : "Dang an"}
                </span>
            </div>
        </div>
    `;
}
function renderSettings() {
    const list = document.getElementById("settings-list");
    const announcement = String(state.settings.homepage_announcement || "");
    list.innerHTML = `
        <div class="rounded-2xl border border-slate-800 bg-slate-950/50 px-4 py-4">
            <label for="homepage-announcement-input" class="block">
                <div class="font-semibold text-white">Thong bao hien thi o trang chu</div>
                <div class="mt-1 text-sm text-slate-400">Nhap noi dung de hien cho tat ca user. Xoa het noi dung neu muon an thong bao.</div>
            </label>
            <textarea
                id="homepage-announcement-input"
                class="mt-3 min-h-28 w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none transition focus:border-sky-500"
                maxlength="280"
                placeholder="Vi du: Toi nay he thong se bao tri tu 22:00 den 22:15."
            >${escapeHtml(announcement)}</textarea>
            <div class="mt-2 flex items-center justify-between gap-3 text-xs">
                <span class="${announcement.trim() ? "text-sky-200" : "text-slate-500"}">${announcement.trim() ? "Thong bao nay dang san sang de hien tren homepage." : "Chua co noi dung thong bao."}</span>
                <span id="homepage-announcement-count" class="text-slate-400">${announcement.length}/280</span>
            </div>
        </div>
    `;
    const announcementInput = document.getElementById("homepage-announcement-input");
    announcementInput?.addEventListener("input", event => {
        state.settings.homepage_announcement = event.target.value;
        const count = document.getElementById("homepage-announcement-count");
        if (count) {
            count.textContent = `${event.target.value.length}/280`;
        }
    });
}

async function fetchSettings() {
    try {
        state.settings = await fetchJson("/api/v1/admin/settings");
        renderSettings();
        renderOverviewFeatures();
    } catch (err) {
        showToast(err.message || "Không thể tải cài đặt.", "error");
    }
}

async function saveSettings() {
    const btn = document.getElementById("save-settings");
    const oldText = btn?.textContent;
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Đang lưu...";
    }

    try {
        state.settings = await fetchJson("/api/v1/admin/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                points_enabled: Boolean(state.settings.points_enabled),
                homepage_announcement: String(state.settings.homepage_announcement || ""),
            }),
        });
        renderSettings();
        renderOverviewFeatures();
        showToast("Đã lưu cài đặt.", "success");
    } catch (err) {
        showToast(err.message || "Không thể lưu cài đặt.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || "Lưu cài đặt";
        }
    }
}

async function fetchUsers(q = "") {
    try {
        const url = q ? `/api/v1/admin/users?q=${encodeURIComponent(q)}` : "/api/v1/admin/users";
        state.users = await fetchJson(url);
        renderUsers();
        renderOverviewUsers();
    } catch (err) {
        showToast(err.message || "Không thể tải danh sách người dùng.", "error");
    }
}

function renderUsers() {
    const list = document.getElementById("admin-user-list");
    if (!list) return;

    if (!state.users.length) {
        list.innerHTML = emptyPanel("Không tìm thấy người dùng nào.");
        return;
    }

    list.innerHTML = state.users.map(user => {
        const name = user.display_name || user.email.split("@")[0];
        const created = formatDateTime(user.created_at);
        const lastBet = user.last_bet_at ? formatDateTime(user.last_bet_at) : "Chưa đặt";
        const approvedAt = user.approved_at ? formatDateTime(user.approved_at) : "Đang chờ duyệt";
        return `
            <div class="glass-panel rounded-3xl p-4 lg:p-5">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                            <h3 class="truncate text-lg font-bold text-white">${escapeHtml(name)}</h3>
                            ${user.is_admin ? `<span class="rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 text-xs font-semibold text-sky-200">Admin</span>` : ""}
                            ${user.is_approved
                                ? `<span class="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-200">Đã duyệt</span>`
                                : `<span class="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-200">Chờ phê duyệt</span>`}
                        </div>
                        <div class="mt-1 truncate text-sm text-slate-400">${escapeHtml(user.email)}</div>
                        <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                            <span class="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1">Tạo: ${escapeHtml(created)}</span>
                            <span class="rounded-full border ${user.is_approved ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200" : "border-amber-500/25 bg-amber-500/10 text-amber-200"} px-2.5 py-1">Phê duyệt: ${escapeHtml(approvedAt)}</span>
                            <span class="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1">Bet: ${formatNumber(user.bet_count)}</span>
                            <span class="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-emerald-200">Thắng: ${formatNumber(user.win_count)}</span>
                            <span class="rounded-full border border-rose-500/25 bg-rose-500/10 px-2.5 py-1 text-rose-200">Thua: ${formatNumber(user.loss_count)}</span>
                            <span class="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1">Gần nhất: ${escapeHtml(lastBet)}</span>
                        </div>
                    </div>
                    <form class="w-full max-w-xl flex flex-col gap-2 lg:min-w-[26rem]" onsubmit="return saveUserPoints(event, '${escapeHtml(user.id)}')">
                        <input
                            class="user-points-input w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-2.5 text-sm font-bold text-amber-200 outline-none transition focus:border-amber-400 sm:w-40"
                            type="number"
                            min="0"
                            max="1000000000"
                            step="1"
                            value="${Number(user.total_points || 0)}"
                            aria-label="Tổng điểm"
                        >
                        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                            <input
                                class="w-full rounded-2xl border border-slate-700 bg-slate-950/80 px-4 py-2.5 text-sm text-white outline-none transition focus:border-sky-500"
                                type="text"
                                maxlength="280"
                                placeholder="Lý do điều chỉnh điểm"
                                aria-label="Lý do điều chỉnh điểm"
                            >
                            <button type="submit" class="rounded-2xl bg-amber-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-300">
                                Lưu điểm
                            </button>
                            ${!user.is_approved ? `
                                <button type="button" class="rounded-2xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400" onclick="approveUser('${escapeHtml(user.id)}')">
                                    Duyệt user
                                </button>
                            ` : ""}
                            <button type="button" class="rounded-2xl border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500 hover:text-white" onclick="toggleUserPointTransactions('${escapeHtml(user.id)}')">
                                Lịch sử điểm
                            </button>
                        </div>
                    </form>
                </div>
                <div id="user-point-transactions-${escapeHtml(user.id)}" class="hidden mt-4 rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <div class="text-xs uppercase tracking-[0.2em] text-slate-400">Point ledger</div>
                            <div class="mt-1 text-sm font-semibold text-white">Lịch sử giao dịch điểm</div>
                        </div>
                        <button type="button" class="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white" onclick="loadMoreUserPointTransactions('${escapeHtml(user.id)}')">
                            Xem thêm
                        </button>
                    </div>
                    <div id="user-point-transactions-list-${escapeHtml(user.id)}" class="mt-4 space-y-3"></div>
                </div>
            </div>
        `;
    }).join("");
}

async function approveUser(userId) {
    if (!window.confirm("Phê duyệt user này để họ vào được trang chủ?")) return;
    try {
        await fetchJson(`/api/v1/admin/users/${encodeURIComponent(userId)}/approve`, { method: "POST" });
        await Promise.all([fetchUsers(state.userSearch), fetchOverview()]);
        showToast("Đã phê duyệt user mới.", "success");
    } catch (err) {
        showToast(err.message || "Không thể phê duyệt user.", "error");
    }
}

async function saveUserPoints(event, userId) {
    event.preventDefault();
    const form = event.currentTarget;
    const [input, reasonInput] = form.querySelectorAll("input");
    const button = form.querySelector("button");
    const wasPanelOpen = !document.getElementById(`user-point-transactions-${userId}`)?.classList.contains("hidden");
    const totalPoints = Number(input.value);
    const reason = String(reasonInput?.value || "").trim();

    if (!Number.isInteger(totalPoints) || totalPoints < 0 || totalPoints > 1_000_000_000) {
        showToast("Điểm phải là số nguyên từ 0 đến 1.000.000.000.", "error");
        return false;
    }
    if (!reason) {
        showToast("Vui lòng nhập lý do điều chỉnh điểm.", "error");
        reasonInput?.focus();
        return false;
    }

    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Đang lưu...";
    try {
        const data = await fetchJson(`/api/v1/admin/users/${encodeURIComponent(userId)}/points`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ total_points: totalPoints, reason }),
        });
        const user = state.users.find(item => item.id === data.id);
        if (user) user.total_points = data.total_points;
        if (data.transaction) {
            const current = state.pointTransactionsByUser[userId];
            if (current?.items) {
                current.items.unshift(data.transaction);
            }
        }
        reasonInput.value = "";
        renderUsers();
        if (wasPanelOpen) {
            document.getElementById(`user-point-transactions-${userId}`)?.classList.remove("hidden");
            renderUserPointTransactions(userId);
        }
        renderOverviewUsers();
        await fetchOverview();
        showToast("Đã cập nhật điểm người dùng.", "success");
    } catch (err) {
        showToast(err.message || "Không thể cập nhật điểm.", "error");
    } finally {
        button.disabled = false;
        button.textContent = oldText;
    }
    return false;
}

function renderUserPointTransactions(userId) {
    const container = document.getElementById(`user-point-transactions-list-${userId}`);
    if (!container) return;
    const stateEntry = state.pointTransactionsByUser[userId];
    const items = Array.isArray(stateEntry?.items) ? stateEntry.items : [];
    if (!items.length) {
        container.innerHTML = emptyPanel("Chưa có giao dịch điểm nào.");
        return;
    }
    container.innerHTML = items.map(item => `
        <article class="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="rounded-full border px-2.5 py-1 text-[11px] font-semibold ${pointTransactionBadge(item)}">${escapeHtml(item.transaction_type_label || item.transaction_type || "Giao dịch")}</span>
                        ${item.is_backfilled ? `<span class="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-slate-400">Backfill</span>` : ""}
                    </div>
                    <div class="mt-2 text-sm font-semibold text-white">${escapeHtml(item.description || "")}</div>
                    <div class="mt-1 text-xs text-slate-400">${escapeHtml(formatDateTime(item.created_at))}</div>
                    ${item.actor ? `<div class="mt-1 text-[11px] text-slate-500">Actor: ${escapeHtml(item.actor.display_name || item.actor.email || "")}</div>` : ""}
                </div>
                <div class="flex-shrink-0 text-right">
                    <div class="text-sm font-black ${Number(item.delta_points || 0) >= 0 ? "text-emerald-300" : "text-rose-300"}">${Number(item.delta_points || 0) >= 0 ? "+" : "-"}${formatCoins(Math.abs(Number(item.delta_points || 0)))}</div>
                    <div class="mt-1 text-[11px] text-slate-500">Số dư ${formatCoins(item.balance_after || 0)}</div>
                </div>
            </div>
        </article>
    `).join("");
}

async function fetchUserPointTransactions(userId, reset = false) {
    const entry = state.pointTransactionsByUser[userId] || { items: [], nextOffset: 0, loading: false };
    if (entry.loading) return;
    if (reset) {
        entry.items = [];
        entry.nextOffset = 0;
    }
    entry.loading = true;
    state.pointTransactionsByUser[userId] = entry;
    try {
        const offset = entry.nextOffset ?? 0;
        const data = await fetchJson(`/api/v1/admin/users/${encodeURIComponent(userId)}/point-transactions?offset=${offset}&limit=10`);
        const items = Array.isArray(data.items) ? data.items : [];
        entry.items = reset ? items : entry.items.concat(items);
        entry.nextOffset = data.next_offset ?? null;
        renderUserPointTransactions(userId);
    } catch (err) {
        showToast(err.message || "Không thể tải lịch sử điểm.", "error");
    } finally {
        entry.loading = false;
    }
}

async function toggleUserPointTransactions(userId) {
    const panel = document.getElementById(`user-point-transactions-${userId}`);
    if (!panel) return;
    const isHidden = panel.classList.contains("hidden");
    panel.classList.toggle("hidden");
    if (isHidden) {
        await fetchUserPointTransactions(userId, true);
    }
}

async function loadMoreUserPointTransactions(userId) {
    const entry = state.pointTransactionsByUser[userId];
    if (entry?.nextOffset === null) {
        showToast("Đã tải hết lịch sử điểm.", "success");
        return;
    }
    await fetchUserPointTransactions(userId, false);
}

async function fetchMatches() {
    try {
        state.matches = await fetchJson("/api/v1/admin/matches");
        renderMatches();
    } catch (err) {
        showToast(err.message || "Không thể tải danh sách trận đấu.", "error");
    }
}

function renderMatches() {
    const list = document.getElementById("admin-match-list");
    if (!list) return;

    if (!state.matches.length) {
        list.innerHTML = emptyPanel("Chưa có trận đấu nào.");
        return;
    }

    const sortedMatches = [...state.matches].sort((a, b) => {
        const aTime = new Date(a.start_time || 0).getTime();
        const bTime = new Date(b.start_time || 0).getTime();
        return bTime - aTime;
    });
    const groupedMatches = sortedMatches.reduce((groups, match) => {
        const dayKey = localDateValue(match.start_time) || "unknown";
        if (!groups[dayKey]) groups[dayKey] = [];
        groups[dayKey].push(match);
        return groups;
    }, {});

    list.innerHTML = Object.values(groupedMatches).map(matches => `
        <section class="match-day-group">
            <div class="sticky-section-head -mx-2 rounded-2xl border border-slate-800 bg-slate-950/85 px-4 py-3">
                <div class="flex items-center justify-between gap-3">
                    <div class="text-sm font-bold text-white">${escapeHtml(formatDateLabel(matches[0]?.start_time))}</div>
                    <div class="text-xs text-slate-400">${formatNumber(matches.length)} trận</div>
                </div>
            </div>
            <div class="space-y-3">
                ${matches.map(match => renderMatchCard(match)).join("")}
            </div>
        </section>
    `).join("");
}

function renderMatchCard(match) {
    const status = normalizeMatchStatus(match.status);
    const canEdit = status !== "finished";
    const statusClass = status === "finished"
        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
        : status === "live"
            ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
            : "border-sky-500/30 bg-sky-500/10 text-sky-200";
    return `
        <article class="glass-panel rounded-3xl p-4 lg:p-5">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="rounded-full border border-slate-700 bg-slate-950/70 px-2.5 py-1 text-[11px] font-semibold text-slate-300">#${Number(match.id)}</span>
                        <span class="rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClass}">${escapeHtml(status)}</span>
                        ${match.result_published ? `<span class="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-200">Đã giải</span>` : ""}
                    </div>
                    <h3 class="mt-3 text-base font-black text-white sm:text-lg">
                        ${teamLabel(match.home_team, match.home_icon)} <span class="text-slate-500">vs</span> ${teamLabel(match.away_team, match.away_icon)}
                    </h3>
                    <div class="mt-3 grid gap-2 text-sm text-slate-400 sm:grid-cols-2 xl:grid-cols-4">
                        <div>Giờ bắt đầu: <span class="font-semibold text-white">${escapeHtml(formatDateTime(match.start_time))}</span></div>
                        <div>Giờ kết thúc: <span class="font-semibold text-white">${escapeHtml(formatDateTime(match.end_time))}</span></div>
                        <div>Kèo: <span class="font-semibold text-white">${Number(match.handicap || 0)}</span></div>
                        <div>Tỷ số: <span class="font-semibold text-white">${Number(match.home_score || 0)} - ${Number(match.away_score || 0)}</span></div>
                    </div>
                </div>
                <div class="flex flex-wrap gap-2 lg:max-w-sm lg:justify-end">
                    ${canEdit ? `
                        <button type="button" class="rounded-2xl border border-sky-500/40 px-3 py-2 text-sm font-medium text-sky-200 transition hover:bg-sky-500/10" onclick="editMatch(${match.id})">Sửa</button>
                        <button type="button" class="rounded-2xl border border-rose-500/40 px-3 py-2 text-sm font-medium text-rose-200 transition hover:bg-rose-500/10" onclick="deleteMatch(${match.id})">Xóa</button>
                    ` : ""}
                    ${status === "finished" && !match.result_published ? resolveForm(match) : ""}
                </div>
            </div>
        </article>
    `;
}

function resolveForm(match) {
    return `
        <form class="flex flex-wrap items-center gap-2" onsubmit="return resolveMatch(event, ${match.id})">
            <input class="w-20 rounded-2xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500" type="number" min="0" step="1" value="${Number(match.home_score || 0)}" aria-label="Tỷ số đội nhà">
            <span class="text-slate-500">-</span>
            <input class="w-20 rounded-2xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500" type="number" min="0" step="1" value="${Number(match.away_score || 0)}" aria-label="Tỷ số đội khách">
            <button type="submit" class="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400">Giải trận</button>
        </form>
    `;
}

function teamLabel(name, icon) {
    const iconSrc = safeImageSrc(icon);
    const iconHtml = iconSrc ? `<img src="${iconSrc}" alt="" class="inline-block h-6 w-6 rounded-full border border-slate-700 object-cover align-middle">` : "";
    return `${iconHtml}<span class="align-middle">${escapeHtml(name)}</span>`;
}

function localDateTimeValue(value) {
    const parts = getVNDateParts(value);
    return parts ? `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}` : "";
}

function apiDateTimeValue(value) {
    return value ? value.replace("T", " ") + ":00" : "";
}

function readMatchPayload() {
    const startDate = document.getElementById("start-date").value;
    const startTime = document.getElementById("start-time").value;
    const homeCountryCode = normalizeCountryCode(document.getElementById("home-country-code").value);
    const awayCountryCode = normalizeCountryCode(document.getElementById("away-country-code").value);
    return {
        home_team: document.getElementById("home-team").value.trim(),
        away_team: document.getElementById("away-team").value.trim(),
        home_icon: homeCountryCode ? buildFlagUrl(homeCountryCode) : null,
        away_icon: awayCountryCode ? buildFlagUrl(awayCountryCode) : null,
        handicap: Number(document.getElementById("handicap").value || 0),
        status: document.getElementById("status").value,
        start_time: apiDateTimeValueFromParts(startDate, startTime),
        end_time: apiDateTimeValue(document.getElementById("end-time").value),
    };
}

async function saveMatch(event) {
    event.preventDefault();
    const matchId = document.getElementById("match-id").value;
    const payload = readMatchPayload();

    if (!payload.home_team || !payload.away_team || !payload.start_time || !payload.end_time) {
        showToast("Vui lòng nhập đủ thông tin trận đấu.", "error");
        return;
    }

    const btn = document.getElementById("save-match-btn");
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Đang lưu...";
    try {
        const url = matchId ? `/api/v1/admin/matches/${matchId}/update` : "/api/v1/admin/matches";
        await fetchJson(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        resetMatchForm();
        closeMatchComposer();
        await Promise.all([fetchMatches(), fetchOverview()]);
        showToast(matchId ? "Đã cập nhật trận đấu." : "Đã thêm trận đấu.", "success");
    } catch (err) {
        showToast(err.message || "Không thể lưu trận đấu.", "error");
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}

function editMatch(matchId) {
    const match = state.matches.find(item => Number(item.id) === Number(matchId));
    if (!match) return;
    openMatchComposer("edit");
    document.getElementById("match-id").value = match.id;
    document.getElementById("home-team").value = match.home_team || "";
    document.getElementById("away-team").value = match.away_team || "";
    document.getElementById("home-country-code").value = extractCountryCode(match.home_icon);
    document.getElementById("away-country-code").value = extractCountryCode(match.away_icon);
    delete document.getElementById("home-country-code").dataset.autoCountryCode;
    delete document.getElementById("away-country-code").dataset.autoCountryCode;
    updateFlagPreview("home-flag-preview", document.getElementById("home-country-code").value);
    updateFlagPreview("away-flag-preview", document.getElementById("away-country-code").value);
    document.getElementById("handicap").value = Number(match.handicap || 0);
    document.getElementById("status").value = normalizeMatchStatus(match.status) === "live" ? "live" : "upcoming";
    document.getElementById("start-date").value = localDateValue(match.start_time);
    document.getElementById("start-time").value = localTimeValue(match.start_time);
    syncMatchEndTime();
    document.getElementById("match-form-title").textContent = "Sửa trận đấu";
    document.getElementById("save-match-btn").textContent = "Cập nhật trận";
    document.getElementById("cancel-edit-btn").classList.remove("hidden");
    setActiveTab("matches");
    document.getElementById("match-composer")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetMatchForm() {
    document.getElementById("match-form")?.reset();
    document.getElementById("match-id").value = "";
    document.getElementById("handicap").value = "0";
    document.getElementById("status").value = "upcoming";
    document.getElementById("home-country-code").value = "";
    document.getElementById("away-country-code").value = "";
    delete document.getElementById("home-country-code").dataset.autoCountryCode;
    delete document.getElementById("away-country-code").dataset.autoCountryCode;
    updateFlagPreview("home-flag-preview", "");
    updateFlagPreview("away-flag-preview", "");
    document.getElementById("start-date").value = todayDateValue();
    document.getElementById("start-time").value = "";
    document.getElementById("end-time").value = "";
    document.getElementById("match-form-title").textContent = "Thêm trận đấu";
    document.getElementById("save-match-btn").textContent = "Lưu trận";
    document.getElementById("cancel-edit-btn")?.classList.add("hidden");
}

async function deleteMatch(matchId) {
    if (!window.confirm(`Xóa trận #${matchId}?`)) return;
    try {
        await fetchJson(`/api/v1/admin/matches/${matchId}/delete`, { method: "POST" });
        await Promise.all([fetchMatches(), fetchOverview()]);
        showToast("Đã xóa trận đấu.", "success");
    } catch (err) {
        showToast(err.message || "Không thể xóa trận đấu.", "error");
    }
}

async function resolveMatch(event, matchId) {
    event.preventDefault();
    const form = event.currentTarget;
    const inputs = form.querySelectorAll("input");
    const homeScore = Number(inputs[0].value);
    const awayScore = Number(inputs[1].value);
    if (!Number.isInteger(homeScore) || homeScore < 0 || !Number.isInteger(awayScore) || awayScore < 0) {
        showToast("Tỷ số phải là số nguyên không âm.", "error");
        return false;
    }
    if (!window.confirm(`Giải trận #${matchId} với tỷ số ${homeScore} - ${awayScore}?`)) return false;

    try {
        const data = await fetchJson(`/api/v1/admin/resolve-match/${matchId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ home_score: homeScore, away_score: awayScore }),
        });
        await Promise.all([fetchMatches(), fetchOverview(), fetchUsers(state.userSearch)]);
        showToast(data.message || "Đã giải trận.", "success");
    } catch (err) {
        showToast(err.message || "Không thể giải trận.", "error");
    }
    return false;
}

function emptyPanel(message) {
    return `<div class="rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-4 text-sm text-slate-400">${escapeHtml(message)}</div>`;
}

function showToast(message, tone = "success") {
    const toast = document.getElementById("toast");
    if (!toast) return;
    clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.className = `rounded-2xl border px-4 py-3 text-sm font-medium ${
        tone === "error"
            ? "border-rose-500/30 bg-rose-500/10 text-rose-100"
            : "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
    }`;
    toast.classList.remove("hidden");
    state.toastTimer = setTimeout(() => toast.classList.add("hidden"), 3500);
}
