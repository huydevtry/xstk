const COMMUNITY_NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };

let communityViewer = null;
let communityNextOffset = 0;
let communityLoading = false;

function communityEscapeHtml(value) {
    return String(value ?? "").replace(/[&<>\"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[ch]));
}

function communitySafeImageSrc(value) {
    const src = String(value ?? "").trim();
    if (!src) return "";
    if (src.startsWith("/") || /^https?:\/\//i.test(src)) return communityEscapeHtml(src);
    return "";
}

function communitySafeCssColor(value) {
    const color = String(value ?? "").trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : "#6366f1";
}

function renderCommunityHeaderUser() {
    const el = document.getElementById("user-info");
    if (!el || !communityViewer) return;
    window.UserShell?.renderUserInfo?.(el, communityViewer);
}

function renderCommunityState() {
    const emptyEl = document.getElementById("community-empty");
    const loadMoreBtn = document.getElementById("community-load-more");
    const container = document.getElementById("community-timeline");
    if (!emptyEl || !loadMoreBtn || !container) return;
    emptyEl.classList.toggle("hidden", container.children.length > 0);
    loadMoreBtn.classList.toggle("hidden", communityNextOffset === null);
    loadMoreBtn.disabled = communityLoading;
    loadMoreBtn.textContent = communityLoading ? "Đang tải..." : "Xem thêm";
}

async function fetchCommunityViewer() {
    const el = document.getElementById("user-info");
    try {
        const res = await fetch("/api/v1/me", COMMUNITY_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        communityViewer = await res.json();
        renderCommunityHeaderUser();
    } catch (error) {
        console.error("fetchCommunityViewer error:", error);
        if (el) {
            el.innerHTML = `<span class="font-medium text-red-400">Lỗi kết nối Auth</span>`;
        }
    }
}

async function fetchCommunityTimeline(reset = false) {
    const container = document.getElementById("community-timeline");
    const errorEl = document.getElementById("community-error");
    if (!container || communityLoading) return;

    if (reset) {
        communityNextOffset = 0;
        container.innerHTML = "";
    }

    communityLoading = true;
    renderCommunityState();
    if (errorEl) {
        errorEl.textContent = "";
        errorEl.classList.add("hidden");
    }

    try {
        const offset = communityNextOffset ?? 0;
        const res = await fetch(`/api/v1/community/timeline?offset=${offset}&limit=10`, COMMUNITY_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];

        if (reset) {
            window.TimelineFeed?.render(container, items, {
                authorHrefBuilder(author) {
                    return author?.id ? `/profile?user_id=${encodeURIComponent(author.id)}` : null;
                },
            });
        } else {
            window.TimelineFeed?.append(container, items, {
                authorHrefBuilder(author) {
                    return author?.id ? `/profile?user_id=${encodeURIComponent(author.id)}` : null;
                },
            });
        }

        communityNextOffset = data.next_offset ?? null;
    } catch (error) {
        console.error("fetchCommunityTimeline error:", error);
        if (errorEl) {
            errorEl.textContent = "Không thể tải news feed cộng đồng lúc này.";
            errorEl.classList.remove("hidden");
        }
    } finally {
        communityLoading = false;
        renderCommunityState();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("community-load-more")?.addEventListener("click", () => fetchCommunityTimeline(false));
    fetchCommunityViewer();
    fetchCommunityTimeline(true);
});
