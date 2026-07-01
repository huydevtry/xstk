// ─── State ───────────────────────────────────────────────────────────────────
let currentUser = null;          // { email, total_points }
let placedBets = new Set();      // match IDs đã cược trong session này
let myBetsByMatchId = new Map();
let matchDetailCache = new Map();
let finishedSectionLoaded = false;
let finishedSectionRefreshTimer = null;
let lastMatchesSignature = "";
let expandedMatchGroups = new Set();
let selectedMatchDate = "";
let currentMatchGroups = {};
let currentMatchDates = [];
let leaderboardNextOffset = 0;
let leaderboardLoading = false;
let appSettings = {
    points_enabled: true,
    homepage_announcement: "",
};
const NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };
const MIN_STAKE = 10;
const QUICK_STAKE_OPTIONS = [100, 200, 500, 1000];

// Bảng màu avatar — hash từ tên để màu ổn định
const AVATAR_COLORS = [
    "#7c3aed","#db2777","#0891b2","#059669","#d97706",
    "#dc2626","#2563eb","#7c3aed","#0d9488","#9333ea",
];

function nameToColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

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
    const flagMatch = src.match(/flagcdn\.com\/(?:[a-z0-9]+\/)?([a-z0-9-]+)\.(?:png|webp|jpg|jpeg|svg)/i);
    if (flagMatch) return escapeHtml(`https://flagcdn.com/w320/${flagMatch[1].toLowerCase()}.webp`);
    if (src.startsWith("/") || /^https?:\/\//i.test(src)) return escapeHtml(src);
    return "";
}

function safeCssColor(value) {
    const color = String(value ?? "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
}

function formatCoins(value) {
    return `${Number(value || 0).toLocaleString()}đ`;
}

function renderLeaderboardAvatar(entry, className = "lb-avatar") {
    const avatarSrc = safeImageSrc(entry.avatar_url);
    const initials = escapeHtml(entry.initials || (String(entry.name ?? "").slice(0, 2).toUpperCase() || "??"));
    const bg = safeCssColor(entry.avatar_color) || nameToColor(String(entry.name ?? ""));
    if (avatarSrc) {
        return `<img src="${avatarSrc}" alt="" class="${className} object-cover border border-slate-200 flex-shrink-0">`;
    }
    return `<span class="${className} flex items-center justify-center text-sm font-black text-white flex-shrink-0" style="background:${bg}">${initials}</span>`;
}

function renderMiniAvatar({ avatar_url, avatar_color, initials }) {
    const avatarSrc = safeImageSrc(avatar_url);
    if (avatarSrc) {
        return `<img src="${avatarSrc}" alt="" class="w-5 h-5 rounded-full object-cover border border-sky-300 flex-shrink-0">`;
    }
    return `<span class="w-5 h-5 rounded-full border border-sky-300 flex items-center justify-center text-[9px] font-black text-white flex-shrink-0" style="background:${safeCssColor(avatar_color)}">${escapeHtml(initials || "??")}</span>`;
}

function renderBettorAvatar(bettor, className = "w-7 h-7") {
    const avatarSrc = safeImageSrc(bettor.avatar_url);
    if (avatarSrc) {
        return `<img src="${avatarSrc}" alt="" class="${className} rounded-full object-cover border border-slate-200 flex-shrink-0">`;
    }
    return `<span class="${className} rounded-full border border-slate-200 flex items-center justify-center text-[11px] font-black text-white flex-shrink-0" style="background:${safeCssColor(bettor.avatar_color)}">${escapeHtml(bettor.initials || "??")}</span>`;
}

const DETAIL_QUOTES = [
    "Đám đông có thể ồn, nhưng quỹ luôn thích chỗ biết thắng.",
    "Cửa ít người vào không có nghĩa là yếu, đôi khi là biết giữ tiền hơn.",
    "Ai cũng thích đi theo số đông, còn tiền thì thích đi theo người tỉnh.",
    "Cửa kia đông thật, nhưng ví tiền không ký hợp đồng với đám đông.",
    "Hôm nay không cần hô to, chỉ cần vào đúng cửa rồi ngồi nhìn tỉ số.",
    "Chọn khôn một nhịp, khịa nhẹ cả phòng.",
];
const APP_TIME_ZONE = "Asia/Ho_Chi_Minh";

function choiceLabel(choice) {
    return { HOME: "Chủ nhà", DRAW: "Hòa", AWAY: "Khách" }[choice] || choice;
}

function isLiveMatch(match) {
    return String(match?.status || "").toLowerCase() === "live";
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

function formatVNTime(value) {
    const parts = getVNDateParts(value);
    return parts ? `${parts.hour}:${parts.minute}` : "-";
}

function formatVNDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("vi-VN", {
        timeZone: APP_TIME_ZONE,
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function localDateKey(value = new Date()) {
    const parts = getVNDateParts(value);
    return parts ? `${parts.year}-${parts.month}-${parts.day}` : "";
}

function formatMatchDateTitle(dateKey) {
    const [year, month, day] = String(dateKey || "").split("-").map(Number);
    if (!year || !month || !day) return "Trận đấu";
    const date = new Date(Date.UTC(year, month - 1, day, 12));
    const text = date.toLocaleDateString("vi-VN", {
        timeZone: "UTC",
        weekday: "long",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
    });
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatTimelineWeekday(dateKey) {
    const [year, month, day] = String(dateKey || "").split("-").map(Number);
    if (!year || !month || !day) return "--";
    const date = new Date(Date.UTC(year, month - 1, day, 12));
    const weekday = date.toLocaleDateString("vi-VN", { timeZone: "UTC", weekday: "short" });
    return weekday.replace(".", "").toUpperCase();
}

function relativeDayLabel(dateKey) {
    const today = localDateKey();
    if (dateKey === today) return "H.Nay";

    const [year, month, day] = String(dateKey || "").split("-").map(Number);
    if (!year || !month || !day) return formatTimelineWeekday(dateKey);

    const date = Date.UTC(year, month - 1, day);
    const [todayYear, todayMonth, todayDay] = today.split("-").map(Number);
    const todayDate = Date.UTC(todayYear, todayMonth - 1, todayDay);
    const diffDays = Math.round((date - todayDate) / 86_400_000);
    if (diffDays === 1) return "Mai";
    if (diffDays === -1) return "Qua";
    return formatTimelineWeekday(dateKey);
}

function chooseDefaultMatchDate(sortedDates, grouped) {
    if (selectedMatchDate && grouped[selectedMatchDate]) return selectedMatchDate;

    const today = localDateKey();
    if (grouped[today]) return today;

    const nextPlayableDate = sortedDates.find(dateKey =>
        dateKey >= today && (grouped[dateKey] || []).some(match => String(match.status || "").toLowerCase() !== "finished")
    );
    return nextPlayableDate || sortedDates[sortedDates.length - 1] || "";
}

function renderMatchDateTimeline(sortedDates, grouped) {
    const timeline = document.getElementById("match-date-timeline");
    if (!timeline) return;

    if (!sortedDates.length) {
        timeline.innerHTML = `<div class="py-3 text-sm text-slate-400">Chưa có ngày thi đấu.</div>`;
        return;
    }

    const today = localDateKey();
    timeline.innerHTML = sortedDates.map(dateKey => {
        const matches = grouped[dateKey] || [];
        const isActive = dateKey === selectedMatchDate;
        const isPast = dateKey < today;
        const hasLive = matches.some(match => isLiveMatch(match));
        const hasUpcoming = matches.some(match => String(match.status || "").toLowerCase() === "upcoming");
        const dayNumber = escapeHtml(String(dateKey.split("-")[2] || ""));
        const label = escapeHtml(relativeDayLabel(dateKey));
        const activeClass = isActive
            ? "w-14 bg-blue-600 text-white shadow-md shadow-blue-200/60 scale-105"
            : `w-12 text-slate-700 hover:bg-slate-50 ${isPast ? "opacity-45 hover:opacity-80" : ""}`;
        const labelClass = isActive ? "text-blue-100" : "text-slate-500";
        const dayClass = isActive ? "text-white text-lg font-black" : "text-slate-800 text-base font-bold";
        const dot = hasLive
            ? `<span class="absolute -right-1 -top-1 flex h-3 w-3"><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75"></span><span class="relative inline-flex h-3 w-3 rounded-full border-2 border-white bg-red-500"></span></span>`
            : hasUpcoming && !isActive
                ? `<span class="absolute -bottom-1 h-1 w-1 rounded-full bg-slate-300"></span>`
                : "";

        return `
            <button type="button"
                id="match-date-${dateKey}"
                class="relative flex shrink-0 snap-start flex-col items-center justify-center rounded-2xl py-2 transition ${activeClass}"
                onclick="selectMatchDate('${dateKey}')"
                aria-pressed="${isActive ? "true" : "false"}"
                title="${escapeHtml(formatMatchDateTitle(dateKey))} - ${matches.length} trận">
                <span class="mb-1 text-[10px] font-bold uppercase tracking-wider ${labelClass}">${label}</span>
                <span class="leading-none ${dayClass}">${dayNumber}</span>
                ${dot}
            </button>
        `;
    }).join("");

    requestAnimationFrame(() => {
        const activeDay = document.getElementById(`match-date-${selectedMatchDate}`);
        if (!activeDay) return;
        timeline.scrollLeft = activeDay.offsetLeft - (timeline.offsetWidth / 2) + (activeDay.offsetWidth / 2);
    });
}

function renderSelectedMatchDate() {
    const listEl = document.getElementById("match-list");
    const titleEl = document.getElementById("selected-match-date-title");
    const countEl = document.getElementById("selected-match-count");
    if (!listEl) return;

    const matches = currentMatchGroups[selectedMatchDate] || [];
    if (titleEl) titleEl.textContent = selectedMatchDate ? formatMatchDateTitle(selectedMatchDate) : "Trận đấu";
    if (countEl) countEl.textContent = `${matches.length} trận`;

    if (!matches.length) {
        listEl.innerHTML = `<div class="rounded-2xl border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500 shadow-sm">Ngày này chưa có trận đấu.</div>`;
        return;
    }

    listEl.innerHTML = matches.map(match => renderMatchCard(match)).join("");
    matches.forEach(match => fetchAvatarStack(match.id));
}

function getQuoteByDetail(detail) {
    const pool = detail?.pool || {};
    const stakeMap = [
        ["HOME", Number(pool.home_stakes || 0)],
        ["DRAW", Number(pool.draw_stakes || 0)],
        ["AWAY", Number(pool.away_stakes || 0)],
    ].sort((a, b) => b[1] - a[1]);
    const dominant = stakeMap[0]?.[0] || "HOME";
    const quoteSets = {
        HOME: [
            "Cửa chủ nhà đang có khí thế, nhưng đừng để cái ồn che mất cái khôn.",
            "Đám đông đang nghiêng về chủ nhà, còn ai tỉnh thì vẫn biết quỹ thích gì.",
        ],
        DRAW: [
            "Kèo hòa thường rất lì, nhìn hiền mà dễ làm cả bọn im lặng.",
            "Cửa hòa không ầm ĩ, nhưng lúc nổ thì ai cũng phải nhìn lại.",
        ],
        AWAY: [
            "Cửa khách mà ít người vào thì lại càng có chất riêng.",
            "Thích đi ngược đám đông à? Cửa khách đang chờ người có gan.",
        ],
    };
    const poolQuotes = quoteSets[dominant] || DETAIL_QUOTES;
    return poolQuotes[Math.floor(Math.random() * poolQuotes.length)];
}

document.addEventListener("DOMContentLoaded", () => {
    initializeHomepage().catch(error => {
        console.error("initializeHomepage error:", error);
    });
    document.getElementById("match-detail-modal")?.addEventListener("click", e => {
        if (e.target && e.target.id === "match-detail-modal") closeMatchDetail();
    });
    document.addEventListener("keydown", e => {
        if (e.key === "Escape") closeMatchDetail();
    });
    // Refresh pool odds mỗi 30 giây
    setInterval(fetchUpcomingMatches, 30_000);
    // Refresh ticker mỗi 60 giây
    setInterval(startTicker, 60_000);
});

async function initializeHomepage() {
    fetchAppSettings();
    await Promise.all([
        fetchUserProfile(),
        fetchMyBetState(),
    ]);
    await fetchUpcomingMatches();
    startTicker();
    fetchLeaderboard();

    // Deep-link từ notification: /?match=<id>
    const matchParam = new URLSearchParams(window.location.search).get('match');
    if (matchParam) {
        const matchId = parseInt(matchParam, 10);
        if (Number.isFinite(matchId)) {
            // Xoá param khỏi URL mà không reload trang
            const cleanUrl = window.location.pathname;
            history.replaceState(null, '', cleanUrl);
            // Mở modal chi tiết trận đấu
            setTimeout(() => {
                if (typeof openMatchDetail === 'function') {
                    openMatchDetail(matchId, true);
                }
            }, 200);
        }
    }
}

async function fetchAppSettings() {
    try {
        const res = await fetch("/api/v1/settings", NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        appSettings = await res.json();
        renderHomepageAnnouncement();
    } catch (err) {
        console.error("fetchAppSettings error:", err);
    }
}

function renderHomepageAnnouncement() {
    const wrap = document.getElementById("homepage-announcement");
    const content = document.getElementById("homepage-announcement-text");
    if (!wrap || !content) return;
    const announcement = String(appSettings?.homepage_announcement || "").trim();
    if (!announcement) {
        wrap.classList.add("hidden");
        content.textContent = "";
        return;
    }
    content.textContent = announcement;
    wrap.classList.remove("hidden");
}


// ─── 1. User Profile ──────────────────────────────────────────────────────────
async function fetchUserProfile() {
    const el = document.getElementById("user-info");
    try {
        const res = await fetch("/api/v1/me", NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error();
        currentUser = await res.json();
        renderUserInfo();
    } catch {
        el.innerHTML = `<span class="text-red-400 font-medium">Lỗi kết nối Auth</span>`;
    }
}

async function fetchMyBetState() {
    try {
        const res = await fetch("/api/v1/me/bets", NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const bets = await res.json();
        myBetsByMatchId = new Map(
            (Array.isArray(bets) ? bets : []).map(bet => [Number(bet.match_id), bet])
        );
        placedBets = new Set(
            (Array.isArray(bets) ? bets : [])
                .filter(bet => String(bet.match_status || "").toLowerCase() !== "finished")
                .map(bet => Number(bet.match_id))
        );
    } catch (error) {
        console.error("fetchMyBetState error:", error);
    }
}

function upsertMyBetState(bet) {
    const matchId = Number(bet?.match_id);
    if (!Number.isFinite(matchId)) return;
    myBetsByMatchId.set(matchId, {
        ...myBetsByMatchId.get(matchId),
        ...bet,
    });
    placedBets.add(matchId);
}

function renderUserInfo() {
    const el = document.getElementById("user-info");
    if (!currentUser) return;
    window.UserShell?.renderUserInfo?.(el, currentUser, { pointsElementId: "user-points" });
}

function updateDisplayedPoints(newTotal) {
    if (currentUser) currentUser.total_points = newTotal;
    const el = document.getElementById("user-points");
    if (el) el.textContent = newTotal.toLocaleString();
}


// ─── 2. Match List ────────────────────────────────────────────────────────────
async function fetchUpcomingMatches() {
    const listEl = document.getElementById("match-list");
    try {
        const res = await fetch("/api/v1/matches", NO_CACHE_FETCH_OPTIONS);
        const matches = await res.json();
        const matchesSignature = JSON.stringify(matches);

        if (matchesSignature === lastMatchesSignature && listEl?.children.length) {
            (currentMatchGroups[selectedMatchDate] || []).forEach(match => fetchAvatarStack(match.id));
            return;
        }

        lastMatchesSignature = matchesSignature;
        matchDetailCache.clear();
        window.MatchDetailModal?.resetCache?.();

        if (!matches.length) {
            listEl.innerHTML = `<div class="text-center py-12 text-slate-500 text-sm">Hiện chưa có trận đấu nào đang mở cược.</div>`;
            expandedMatchGroups = new Set();
            currentMatchGroups = {};
            currentMatchDates = [];
            selectedMatchDate = "";
            renderMatchDateTimeline([], {});
            return;
        }

        const sortedMatches = [...matches].sort((a, b) => {
            const aTime = new Date(a.start_time || 0).getTime();
            const bTime = new Date(b.start_time || 0).getTime();
            return aTime - bTime;
        });

        const grouped = {};
        sortedMatches.forEach(m => {
            const parts = getVNDateParts(m.start_time);
            const key = parts ? `${parts.year}-${parts.month}-${parts.day}` : "unknown";
            (grouped[key] = grouped[key] || []).push(m);
        });

        const sortedDates = Object.keys(grouped).sort();
        currentMatchGroups = grouped;
        currentMatchDates = sortedDates;
        selectedMatchDate = chooseDefaultMatchDate(sortedDates, grouped);
        renderMatchDateTimeline(sortedDates, grouped);
        renderSelectedMatchDate();

    } catch (e) {
        console.error(e);
        listEl.innerHTML = `<div class="text-center py-8 text-red-400 text-xs">Không thể tải danh sách trận đấu. Vui lòng thử lại sau!</div>`;
    }
}

window.selectMatchDate = function(dateKey) {
    if (!currentMatchGroups[dateKey]) return;
    selectedMatchDate = dateKey;
    renderMatchDateTimeline(currentMatchDates, currentMatchGroups);
    renderSelectedMatchDate();
};

async function fetchLatestFinishedMatch() {
    const el = document.getElementById("latest-finished-body");
    if (!el) return;
    try {
        const res = await fetch("/api/v1/matches/latest-finished/detail", NO_CACHE_FETCH_OPTIONS);
        if (res.status === 404) {
            el.innerHTML = `<div class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">Chưa có trận nào hoàn tất.</div>`;
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const details = Array.isArray(data) ? data : [data];
        el.innerHTML = renderLatestFinishedMatches(details);
    } catch (e) {
        console.error(e);
        el.innerHTML = `<div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">Không tải được danh sách trận đã hoàn tất.</div>`;
    }
}




// ─── 4. Avatar Stack ──────────────────────────────────────────────────────────
async function fetchAvatarStack(matchId) {
    try {
        const res = await fetch(`/api/v1/matches/${matchId}/bets`, NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) return;
        const data = await res.json();
        ["HOME", "DRAW", "AWAY"].forEach(choice => {
            const slot = document.getElementById(`avatars-${choice.toLowerCase()}-${matchId}`);
            if (!slot) return;
            renderAvatarStack(slot, data[choice] || []);
        });
    } catch(e) {
        // Silently fail – avatar stack is non-critical
    }
}

function renderAvatarStack(container, bettors) {
    if (!bettors.length) {
        container.innerHTML = `<span class="text-gray-600 text-xs">—</span>`;
        return;
    }

    const MAX_SHOW = 5;
    const shown = bettors.slice(0, MAX_SHOW);
    const extra = bettors.length - MAX_SHOW;

    // Build từ phải sang trái (do flex-direction: row-reverse)
    let avatarsHtml = shown.map(b => {
        const rawName = String(b.name ?? "");
        const lwClass = b.is_lone_wolf ? " lone-wolf" : "";
        const lwIcon  = b.is_lone_wolf ? `<span style="position:absolute;top:-7px;right:-3px;font-size:0.6rem;line-height:1">👑</span>` : "";
        const title = escapeHtml(
            b.is_lone_wolf
                ? `${rawName} — Kẻ đi ngược đám đông! (${formatCoins(b.stake)})`
                : `${rawName} (${formatCoins(b.stake)})`
        );
        const avatar = renderBettorAvatar(b, "w-full h-full");
        return `<div class="avatar-circle${lwClass}" title="${title}">${lwIcon}${avatar}</div>`;
    }).join("");

    if (extra > 0) {
        avatarsHtml += `<div class="avatar-more">+${extra}</div>`;
    }

    container.innerHTML = `<div class="avatar-stack">${avatarsHtml}</div>`;
}


// ─── 5. Tính điểm thưởng dự kiến ───────────────────────────────────────────────
function estimateReward(totalPool, choicePool, stake) {
    const pool = Math.max(0, Number(totalPool) || 0);
    const choice = Math.max(0, Number(choicePool) || 0);
    const bet = Math.max(0, Number(stake) || 0);
    if (bet <= 0) return 0;
    return Math.floor(((pool + bet) * bet) / (choice + bet));
}

function renderLatestFinishedMatch(detail) {
    const match = detail.match || {};
    const settlement = detail.settlement || {};
    const pool = detail.pool || {};
    const myBet = detail.my_bet;

    const isPublished = Boolean(settlement.result_published);
    const totalPool = Number(pool.total_pool || 0);
    const winnerCount = Number(settlement.winner_count || 0);
    const loserCount = Number(settlement.loser_count || 0);
    const refundCount = Number(settlement.refund_count || 0);
    const winnerText = !isPublished ? "Chờ kết quả"
        : settlement.refunded ? "Hoàn điểm"
        : choiceLabel(settlement.winning_choice);
    const scoreText = isPublished
        ? (settlement.score || `${match.home_score ?? 0}-${match.away_score ?? 0}`)
        : "?-?";

    const cardId = `finished-card-${match.id}`;

    // Badge + border + detail block based on user outcome
    let outcomeBadge, cardBorderClass, myResultBlock;
    if (!myBet) {
        outcomeBadge = `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-400">Không cược</span>`;
        cardBorderClass = "border-slate-200";
        myResultBlock = `<p class="text-xs text-slate-400 italic">Bạn chưa tham gia trận này.</p>`;
    } else if (!isPublished) {
        outcomeBadge = `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500">⏳ Chờ kết quả</span>`;
        cardBorderClass = "border-slate-200";
        myResultBlock = `<p class="text-xs text-slate-500">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · Chờ công bố</p>`;
    } else if (myBet.outcome === "WIN") {
        outcomeBadge = `<span class="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">🏆 Thắng +${formatCoins(myBet.points_earned)}</span>`;
        cardBorderClass = "border-emerald-300";
        myResultBlock = `<p class="text-xs text-emerald-700">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · Nhận về <strong>${escapeHtml(myBet.reward_label || formatCoins(myBet.points_earned))}</strong></p>`;
    } else if (myBet.outcome === "HALF_WIN") {
        outcomeBadge = `<span class="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">➗ Thắng nửa ${formatCoins(myBet.points_earned)}</span>`;
        cardBorderClass = "border-emerald-300";
        myResultBlock = `<p class="text-xs text-emerald-700">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · ${escapeHtml(myBet.reward_label || "")}</p>`;
    } else if (myBet.outcome === "LOSE") {
        outcomeBadge = `<span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-600">💸 Thua</span>`;
        cardBorderClass = "border-rose-200";
        myResultBlock = `<p class="text-xs text-rose-600">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · Mất trắng</p>`;
    } else if (myBet.outcome === "HALF_LOSE") {
        outcomeBadge = `<span class="inline-flex items-center gap-1 rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-[10px] font-bold text-orange-700">➗ Thua nửa ${formatCoins(myBet.points_earned)}</span>`;
        cardBorderClass = "border-orange-200";
        myResultBlock = `<p class="text-xs text-orange-700">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · ${escapeHtml(myBet.reward_label || "")}</p>`;
    } else if (myBet.outcome === "REFUND") {
        outcomeBadge = `<span class="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">🔄 Hoàn điểm</span>`;
        cardBorderClass = "border-amber-200";
        myResultBlock = `<p class="text-xs text-amber-700">Cửa: <strong>${escapeHtml(choiceLabel(myBet.choice))}</strong> · Đặt ${formatCoins(myBet.stake)} · Hoàn lại ${formatCoins(myBet.stake)}</p>`;
    } else {
        outcomeBadge = `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-400">─</span>`;
        cardBorderClass = "border-slate-200";
        myResultBlock = "";
    }

    const myResultBg = ["WIN", "HALF_WIN"].includes(myBet?.outcome) ? "bg-emerald-50 border-emerald-100"
        : myBet?.outcome === "LOSE" ? "bg-rose-50 border-rose-100"
        : myBet?.outcome === "HALF_LOSE" ? "bg-orange-50 border-orange-100"
        : myBet?.outcome === "REFUND" ? "bg-amber-50 border-amber-100"
        : "bg-slate-50 border-slate-100";

    const quote = settlement.headline_quote || getQuoteByDetail(detail);

    return `
        <div class="rounded-xl border ${cardBorderClass} bg-white shadow-sm overflow-hidden">
            <button class="w-full flex items-start justify-between gap-3 p-3 sm:p-4 text-left hover:bg-slate-50 active:bg-slate-100 transition-colors"
                onclick="toggleFinishedCard('${cardId}')">
                <div class="flex-1 min-w-0">
                    <div class="flex flex-wrap items-center gap-1.5 mb-1">
                        ${outcomeBadge}
                        ${isPublished && !settlement.refunded ? `<span class="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-500">Cửa thắng: ${escapeHtml(winnerText)}</span>` : ""}
                    </div>
                    <div class="text-sm font-bold text-slate-900 truncate">
                        ${escapeHtml(match.home_team || "?")}
                        <span class="font-normal text-slate-400 mx-1">${isPublished ? escapeHtml(scoreText) : "vs"}</span>
                        ${escapeHtml(match.away_team || "?")}
                    </div>
                    <div class="mt-0.5 text-[11px] text-slate-400">${formatVNDateTime(match.start_time)} · Kèo chấp ${match.handicap ?? 0}</div>
                </div>
                <svg id="${cardId}-icon" class="w-4 h-4 mt-1 text-slate-400 transition-transform duration-200 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                </svg>
            </button>

            <div id="${cardId}" class="hidden border-t border-slate-100 p-3 sm:p-4 space-y-3">
                <div class="rounded-lg border ${myResultBg} px-3 py-2">
                    <div class="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Kết quả của bạn</div>
                    ${myResultBlock}
                </div>

                ${isPublished ? `
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        ${summaryTile("Tổng quỹ", formatCoins(totalPool), "text-[#D3af37]")}
                        ${summaryTile("Người thắng", String(winnerCount), "text-emerald-600")}
                        ${summaryTile("Người thua", String(loserCount), "text-rose-600")}
                        ${summaryTile(settlement.refunded ? "Hoàn tiền" : "Cửa thắng", settlement.refunded ? String(refundCount) : escapeHtml(winnerText), "text-[#D3af37]")}
                    </div>
                    ${settlement.adjusted_score ? `<div class="text-[11px] text-slate-400">Tỷ số: <strong class="text-slate-600">${escapeHtml(scoreText)}</strong> · Sau kèo: <strong class="text-slate-600">${escapeHtml(settlement.adjusted_score)}</strong></div>` : ""}
                ` : `
                    <div class="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                        Trận đã kết thúc theo lịch, đang chờ công bố kết quả chính thức.
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        ${summaryTile("Tổng quỹ", formatCoins(totalPool), "text-[#D3af37]")}
                        ${summaryTile("Trạng thái", "Chờ công bố", "text-slate-500")}
                    </div>
                `}

                ${quote ? `
                    <div class="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
                        <div class="text-[10px] uppercase tracking-wide text-amber-700 mb-1">Chuyên gia nhận định</div>
                        <div class="text-xs italic leading-relaxed text-amber-900">${escapeHtml(quote)}</div>
                    </div>
                ` : ""}

                <button type="button" onclick="openMatchDetail(${match.id}, true)"
                    class="w-full rounded-lg border border-sky-200 bg-sky-50 py-2 text-xs font-semibold text-sky-700 hover:bg-sky-100 transition-colors">
                    🔎 Xem toàn bộ chi tiết
                </button>
            </div>
        </div>`;
}

function renderLatestFinishedMatches(details) {
    if (!details.length) {
        return `<div class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">Chưa có trận nào hoàn tất.</div>`;
    }
    return details.map(renderLatestFinishedMatch).join("");
}




// ─── 9. Toggle Accordion ─────────────────────────────────────────────────────
function summaryTile(label, value, valueClass) {
    return `
        <div class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <div class="text-[11px] uppercase tracking-wide text-slate-500">${escapeHtml(label)}</div>
            <div class="mt-1 text-sm font-black ${valueClass}">${escapeHtml(value)}</div>
        </div>`;
}

window.toggleGroup = function(dateKey) {
    const content = document.getElementById(`content-${dateKey}`);
    const icon = document.getElementById(`icon-${dateKey}`);
    if (!content) return;
    const isHidden = content.classList.toggle("hidden");
    icon?.classList.toggle("rotate-180");
    if (isHidden) {
        expandedMatchGroups.delete(dateKey);
    } else {
        expandedMatchGroups.add(dateKey);
    }
};

window.toggleFinishedSection = function() {
    const container = document.getElementById("finished-section-container");
    const btn = document.getElementById("finished-toggle-btn");
    if (!container) return;
    const isNowHidden = container.classList.toggle("hidden");
    if (isNowHidden) {
        if (btn) btn.textContent = "Xem kết quả ▸";
        clearInterval(finishedSectionRefreshTimer);
        finishedSectionRefreshTimer = null;
    } else {
        if (btn) btn.textContent = "Thu gọn ▾";
        if (!finishedSectionLoaded) {
            fetchLatestFinishedMatch();
            finishedSectionLoaded = true;
        }
        clearInterval(finishedSectionRefreshTimer);
        finishedSectionRefreshTimer = setInterval(fetchLatestFinishedMatch, 30_000);
    }
};

window.toggleFinishedCard = function(cardId) {
    const body = document.getElementById(cardId);
    const icon = document.getElementById(`${cardId}-icon`);
    if (!body) return;
    body.classList.toggle("hidden");
    icon?.classList.toggle("rotate-180");
};


// ─── 10. Live Ticker ──────────────────────────────────────────────────────────
async function startTicker() {
    const wrap = document.getElementById("ticker-content");
    if (!wrap) return;
    try {
        const res = await fetch("/api/v1/activity-feed", NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) return;
        const activities = await res.json();
        if (!activities.length) return;

        const text = activities
            .map(a => `<span>${escapeHtml(a.text)}</span>`)
            .join(`<span class="ticker-sep">•</span>`);

        // Duplicate để loop mượt
        wrap.innerHTML = text + `<span class="ticker-sep">•••</span>` + text;

        // Reset animation
        wrap.style.animation = "none";
        wrap.offsetHeight; // reflow
        wrap.style.animation = "";
    } catch(e) {
        // Silently fail
    }
}


// ─── 11. Leaderboard (Bảng Phong Thần) ───────────────────────────────────────
async function fetchLeaderboard() {
    const el = document.getElementById("leaderboard-body");
    if (!el) return;
    if (leaderboardLoading) return;

    leaderboardLoading = true;
    renderLeaderboardLoadMoreState();
    try {
        const offset = leaderboardNextOffset ?? 0;
        const res = await fetch(`/api/v1/leaderboard?offset=${offset}&limit=10`, NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) return;
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];
        renderLeaderboard(items, el, { append: offset > 0 });
        leaderboardNextOffset = data.next_offset ?? null;
    } catch(e) {
        // Silently fail
    } finally {
        leaderboardLoading = false;
        renderLeaderboardLoadMoreState();
    }
}

function renderLeaderboardLoadMoreState() {
    const btn = document.getElementById("leaderboard-load-more");
    if (!btn) return;
    btn.disabled = leaderboardLoading;
    btn.setAttribute("aria-busy", String(leaderboardLoading));
    btn.classList.toggle("hidden", leaderboardNextOffset === null);
    btn.innerHTML = leaderboardLoading
        ? `
            <span class="leaderboard-expand-spinner" aria-hidden="true"></span>
            <span class="leaderboard-expand-copy">
                <span class="leaderboard-expand-title">Đang tải thêm...</span>
                <span class="leaderboard-expand-subtitle">Giữ chỗ, bảng sắp dài hơn</span>
            </span>`
        : `
            <span class="leaderboard-expand-icon" aria-hidden="true">↓</span>
            <span class="leaderboard-expand-copy">
                <span class="leaderboard-expand-title">Xem đáy xã hội</span>
            </span>`;
}

function renderLeaderboard(data, container, { append = false } = {}) {
    if (!data.length) {
        if (!append) {
            container.innerHTML = `<div class="text-center py-8 text-slate-500 text-sm">Chưa có dữ liệu xếp hạng.</div>`;
        }
        return;
    }

    const BADGE_COLOR_MAP = {
        gold: "lb-badge-gold",
        purple: "lb-badge-purple",
        red: "lb-badge-red",
        gray: "lb-badge-gray",
    };

    const RANK_MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };

    const markup = data.map(entry => {
        const rankEl = RANK_MEDALS[entry.rank]
            ? `<span class="lb-rank ${entry.rank === 1 ? "top1" : entry.rank === 2 ? "top2" : "top3"}">${RANK_MEDALS[entry.rank]}</span>`
            : `<span class="lb-rank">${entry.rank}</span>`;

        const badgeHtml = entry.badge
            ? `<span class="lb-badge ${BADGE_COLOR_MAP[entry.badge.color] || ""}">${escapeHtml(entry.badge.emoji)} ${escapeHtml(entry.badge.label)}</span>`
            : "";

        const rawName = String(entry.display_name ?? entry.name ?? "");
        const profileHref = entry.id ? `/profile?user_id=${encodeURIComponent(entry.id)}` : "/profile";

        let trendHtml;
        if (entry.trend === "up") {
            trendHtml = `<span class="lb-trend up"><span class="trend-arrow-up">↑</span> +${entry.earned_24h.toLocaleString()}</span>`;
        } else if (entry.trend === "down") {
            trendHtml = `<span class="lb-trend down">↓ Thua ${entry.streak_loss} trận</span>`;
        } else {
            trendHtml = `<span class="lb-trend neutral">— Ổn định</span>`;
        }

        return `
        <div class="lb-row">
            ${rankEl}
            <a href="${profileHref}" class="lb-info group text-left block">
                <div class="lb-name">
                    ${renderLeaderboardAvatar({ ...entry, name: rawName })}
                    <div class="min-w-0">
                        <span class="group-hover:underline">${escapeHtml(rawName)}</span>
                        ${badgeHtml}
                    </div>
                </div>
            </a>
            <div class="lb-points">
                <span class="lb-score">${entry.total_points.toLocaleString()}</span>
                ${trendHtml}
            </div>
        </div>`;
    }).join("");

    if (append) {
        container.insertAdjacentHTML("beforeend", markup);
        return;
    }

    container.innerHTML = markup;
}


// ─── 12. Toast Notification ───────────────────────────────────────────────────
function showToast(msg, type = "success") {
    const existing = document.getElementById("toast-container");
    if (existing) existing.remove();

    const color = type === "success" ? "bg-emerald-700 border-emerald-500" : "bg-red-800 border-red-600";
    const toast = document.createElement("div");
    toast.id = "toast-container";
    toast.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-xl border text-sm font-semibold text-white shadow-xl ${color} max-w-xs text-center`;
    toast.style.animation = "slideDown 0.25s ease";
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

const matchSelections = {};

function getEffectiveMinStake(minStake) {
    const parsed = Number(minStake);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function buildQuickStakeOptions(minStake, maxStake) {
    const effectiveMin = getEffectiveMinStake(minStake);
    const hasDynamicMin = Number.isFinite(Number(minStake)) && Number(minStake) > 0;
    const unique = new Set([...(hasDynamicMin ? [effectiveMin] : []), ...QUICK_STAKE_OPTIONS, maxStake]);
    return [...unique]
        .map(Number)
        .filter(value => Number.isFinite(value) && value >= effectiveMin && value <= maxStake)
        .sort((a, b) => a - b);
}

function normalizeStakeValue(rawVal, minStake, maxStake) {
    const effectiveMin = getEffectiveMinStake(minStake);
    const parsed = parseInt(rawVal, 10);
    if (!Number.isFinite(parsed)) return effectiveMin;
    return Math.max(effectiveMin, Math.min(parsed, maxStake));
}

function renderMatchCard(match) {
    const timeStr = formatVNTime(match.start_time);
    const { id, home_team, home_icon, away_team, away_icon, handicap, stakes_home, stakes_draw, stakes_away, total_pool } = match;
    const status = String(match.status || "upcoming");
    const isLive = isLiveMatch(match);
    const canBet = status === "upcoming";
    const endTimeStr = match.end_time ? formatVNTime(match.end_time) : "-";
    const homeTeam = escapeHtml(home_team);
    const awayTeam = escapeHtml(away_team);
    const homeIconSrc = safeImageSrc(home_icon);
    const awayIconSrc = safeImageSrc(away_icon);
    const minStake = match.min_stake;
    const minStakeHint = minStake ? `Tối thiểu ${formatCoins(minStake)}` : "Mở bát tự do";

    const hcSign = handicap > 0 ? "+" : "";
    const hcClass = handicap >= 0 ? "handicap-pos" : "handicap-neg";
    const hcBadge = handicap !== 0 ? `<span class="${hcClass}">(${hcSign}${handicap})</span>` : "";
    // Kèo chấp lẻ (0.5, 1.5, ...) không có kết quả hòa
    const isOddHandicap = handicap % 1 !== 0;

    const betArea = placedBets.has(id)
        ? `<div class="bet-placed-badge">Đã đặt cược cho trận này</div>`
        : canBet
        ? `
            <div class="bet-btn-group" id="btn-group-${id}">
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-home-${id}" onclick="selectChoice(${id}, 'HOME', ${total_pool}, ${stakes_home}, '${status}', ${minStake ?? "null"})">
                        <span class="bet-label">NHÀ</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-home-${id}"></div>
                </div>
                ${!isOddHandicap ? `
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-draw-${id}" onclick="selectChoice(${id}, 'DRAW', ${total_pool}, ${stakes_draw}, '${status}', ${minStake ?? "null"})">
                        <span class="bet-label">HÒA</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-draw-${id}"></div>
                </div>` : ""}
                <div class="bet-choice-block">
                    <button class="bet-btn w-full" id="bet-away-${id}" onclick="selectChoice(${id}, 'AWAY', ${total_pool}, ${stakes_away}, '${status}', ${minStake ?? "null"})">
                        <span class="bet-label">KHÁCH</span>
                    </button>
                    <div class="avatar-stack-row" id="avatars-away-${id}"></div>
                </div>
            </div>
            <div class="mt-2 text-center text-[11px] text-slate-500">${escapeHtml(minStakeHint)}</div>
            <div id="stake-panel-${id}" class="hidden"></div>`
        : `
            <div class="bet-btn-group" id="btn-group-${id}">
                <div class="bet-choice-block">
                    <div class="px-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">NHÀ</div>
                    <div class="avatar-stack-row" id="avatars-home-${id}"></div>
                </div>
                ${!isOddHandicap ? `
                <div class="bet-choice-block">
                    <div class="px-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">HÒA</div>
                    <div class="avatar-stack-row" id="avatars-draw-${id}"></div>
                </div>` : ""}
                <div class="bet-choice-block">
                    <div class="px-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">KHÁCH</div>
                    <div class="avatar-stack-row" id="avatars-away-${id}"></div>
                </div>
            </div>
            <div class="mt-2 text-center text-[11px] text-slate-500">${escapeHtml(minStakeHint)}</div>
            <div id="stake-panel-${id}" class="hidden"></div>`;

    const teamLogoClass = "h-8 w-12 rounded-none border border-slate-200 bg-white object-contain shadow-sm md:h-12 md:w-16 lg:h-14 lg:w-20";
    const homeIconHtml = homeIconSrc ? `<img src="${homeIconSrc}" class="${teamLogoClass}" alt="">` : "";
    const awayIconHtml = awayIconSrc ? `<img src="${awayIconSrc}" class="${teamLogoClass}" alt="">` : "";
    const liveBadge = isLive ? `
        <span class="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-bold text-rose-600">
            <span class="h-2 w-2 rounded-full bg-rose-500 animate-pulse"></span>
            LIVE
        </span>` : "";

    return `
        <div class="bg-white border border-slate-200 hover:border-sky-300 rounded-xl p-4 shadow-sm transition duration-200 mb-3 last:mb-0">
            <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                    ${liveBadge}
                    <span class="text-xs bg-sky-50 text-sky-700 font-mono font-semibold px-2 py-1 rounded border border-sky-100">⏰ ${timeStr} - ${endTimeStr}</span>
                </div>
                <button type="button"
                    class="inline-flex items-center gap-1 text-xs bg-white text-slate-600 border border-slate-200 hover:border-sky-300 hover:text-sky-700 px-2.5 py-1 rounded-full transition-colors shadow-sm"
                    onclick="openMatchDetail(${id})"
                    title="Xem chi tiết trận">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M11 16h2M12 8v4m0 8a8 8 0 100-16 8 8 0 000 16z"/>
                    </svg>
                    <span>Chi tiết</span>
                </button>
            </div>

            <div class="flex items-center justify-between my-3 px-2">
                <div class="w-2/5 text-center flex flex-col items-center">
                    <div class="flex items-center justify-center mb-2 md:mb-3">${homeIconHtml}</div>
                    <p class="text-sm font-bold text-slate-900 truncate w-full">${homeTeam} ${hcBadge}</p>
                    <span class="text-xs text-slate-500 block mt-0.5">Chủ nhà</span>
                </div>
                <div class="w-1/5 text-center text-slate-400 font-black text-sm">VS</div>
                <div class="w-2/5 text-center flex flex-col items-center">
                    <div class="flex items-center justify-center mb-2 md:mb-3">${awayIconHtml}</div>
                    <p class="text-sm font-bold text-slate-900 truncate w-full">${awayTeam}</p>
                    <span class="text-xs text-slate-500 block mt-0.5">Khách</span>
                </div>
            </div>

            <div class="text-center text-xs text-slate-500 mb-1">
                Pool: <span class="text-[#D3af37] font-semibold">${formatCoins(total_pool)}</span>
            </div>

            ${betArea}
        </div>`;
}

window.selectChoice = function(matchId, choice, totalPool, stakesOnChoice, matchStatus = "upcoming", minStake = null) {
    if (String(matchStatus).toLowerCase() !== "upcoming") return;
    matchSelections[matchId] = { choice, totalPool, stakesOnChoice, status: matchStatus, minStake };

    ["HOME", "DRAW", "AWAY"].forEach(c => {
        const btn = document.getElementById(`bet-${c.toLowerCase()}-${matchId}`);
        if (btn) btn.classList.toggle("selected", c === choice);
    });

    renderStakePanel(matchId, choice, totalPool, stakesOnChoice, minStake);
};

function renderStakePanel(matchId, choice, totalPool, stakesOnChoice, minStake = null) {
    const panel = document.getElementById(`stake-panel-${matchId}`);
    const selection = matchSelections[matchId] || {};
    const matchStatus = selection.status || "upcoming";
    if (!panel || String(matchStatus).toLowerCase() !== "upcoming") return;

    const maxStake = currentUser ? Number(currentUser.total_points || 0) : 1000;
    const effectiveMin = getEffectiveMinStake(minStake ?? selection.minStake);
    const defaultStake = Math.max(effectiveMin, Math.min(buildQuickStakeOptions(minStake, maxStake)[0] || effectiveMin, maxStake));

    panel.classList.remove("hidden");
    if (maxStake < effectiveMin) {
        panel.innerHTML = `
            <div class="stake-panel">
                <label>Số điểm đặt cược</label>
                <div class="text-sm text-rose-600 mt-2">Trận này đang yêu cầu tối thiểu ${formatCoins(effectiveMin)}. Hiện tại bạn có ${formatCoins(maxStake)}.</div>
            </div>`;
        return;
    }

    const chips = buildQuickStakeOptions(minStake, maxStake).map(value => `
        <button type="button"
            class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 transition hover:border-sky-300 hover:text-sky-700"
            onclick="pickStake(${matchId}, ${totalPool}, ${stakesOnChoice}, ${value})">
            ${formatCoins(value)}
        </button>
    `).join("");

    panel.innerHTML = `
        <div class="stake-panel">
            <label>Số điểm đặt cược</label>
            <div class="mt-2 text-xs text-slate-500">
                ${effectiveMin > 1 ? `Tối thiểu hiện tại: ${formatCoins(effectiveMin)}.` : "Chưa ai lên thuyền. Bạn có thể mở bát tự do."}
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
                ${chips}
            </div>
            <div class="mt-3">
                <input type="number" class="stake-input w-full"
                    id="input-${matchId}"
                    min="${effectiveMin}" max="${maxStake}" step="1" value="${defaultStake}"
                    oninput="syncStake(${matchId}, ${totalPool}, ${stakesOnChoice}, this.value)">
            </div>
            <div class="est-return" id="est-${matchId}">
                Ước tính nhận: <strong>${formatCoins(estimateReward(totalPool, stakesOnChoice, defaultStake))}</strong>
            </div>
            <button class="confirm-bet-btn" id="confirm-btn-${matchId}" onclick="confirmBet(${matchId})">
                Xuống xác
            </button>
        </div>`;
}

window.pickStake = function(matchId, totalPool, stakesOnChoice, value) {
    syncStake(matchId, totalPool, stakesOnChoice, value);
};

window.syncStake = function(matchId, totalPool, stakesOnChoice, rawVal) {
    const input = document.getElementById(`input-${matchId}`);
    if (!input) return;
    const selection = matchSelections[matchId] || {};
    const maxStake = currentUser ? Number(currentUser.total_points || 0) : 9999;
    const value = normalizeStakeValue(rawVal, selection.minStake, maxStake);
    input.value = value;
    const est = estimateReward(totalPool, stakesOnChoice, value);
    const estEl = document.getElementById(`est-${matchId}`);
    if (estEl) estEl.innerHTML = `Ước tính nhận: <strong>${formatCoins(est)}</strong>`;
};

window.confirmBet = async function(matchId) {
    const sel = matchSelections[matchId];
    if (!sel || String(sel.status || "upcoming").toLowerCase() !== "upcoming") return;

    const input = document.getElementById(`input-${matchId}`);
    const effectiveMin = getEffectiveMinStake(sel.minStake);
    const stakeVal = parseInt(input?.value || "0", 10) || 0;
    if (stakeVal < effectiveMin) {
        showToast(`Số điểm tối thiểu là ${formatCoins(effectiveMin)}.`, "error");
        return;
    }
    if (currentUser && stakeVal > currentUser.total_points) {
        showToast("Số điểm không đủ.", "error");
        return;
    }

    const btn = document.getElementById(`confirm-btn-${matchId}`);
    btn.disabled = true;
    btn.textContent = "Đang xử...";

    try {
        const res = await fetch("/api/v1/bets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ match_id: matchId, choice: sel.choice, stake: stakeVal }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            showToast(data.detail || "Đặt thất bại.", "error");
            btn.disabled = false;
            btn.textContent = "Xuống xác";
            return;
        }

        placedBets.add(matchId);
        updateDisplayedPoints(data.remaining_points);
        showToast(`Đóng họ thành công. Còn lại ${formatCoins(data.remaining_points)}.`, "success");
        matchDetailCache.delete(matchId);
        window.MatchDetailModal?.resetCache?.();

        const stakePanel = document.getElementById(`stake-panel-${matchId}`);
        const btnGroup = document.getElementById(`btn-group-${matchId}`);
        if (stakePanel) stakePanel.innerHTML = "";
        if (btnGroup) btnGroup.outerHTML = `<div class="bet-placed-badge">Đã lên thuyền</div>`;

        fetchAvatarStack(matchId);
        fetchUpcomingMatches();
        startTicker();
    } catch (e) {
        showToast(" lỗi kết nối. Vui lòng thử lại.", "error");
        btn.disabled = false;
        btn.textContent = "Xuống xác";
    }
};
