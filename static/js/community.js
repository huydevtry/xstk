const COMMUNITY_NO_CACHE_FETCH_OPTIONS = { cache: "no-store" };

let communityViewer = null;
let communityNextOffset = 0;
let communityLoading = false;
let selectedReactionBet = null;
let selectedFeedMediaFile = null;
let selectedFeedMediaPreviewUrl = "";

const FEED_MEDIA_MAX_BYTES = 8 * 1024 * 1024;
const FEED_MEDIA_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

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

function setFeedMediaError(message) {
    const errorEl = document.getElementById("feed-media-error");
    if (!errorEl) return;
    errorEl.textContent = message || "";
    errorEl.classList.toggle("hidden", !message);
}

function resetFeedMediaSelection() {
    const input = document.getElementById("feed-media-input");
    const preview = document.getElementById("feed-media-preview");
    const previewWrap = document.getElementById("feed-media-preview-wrap");
    const clearBtn = document.getElementById("clear-feed-media");
    if (selectedFeedMediaPreviewUrl) {
        URL.revokeObjectURL(selectedFeedMediaPreviewUrl);
    }
    selectedFeedMediaFile = null;
    selectedFeedMediaPreviewUrl = "";
    if (input) input.value = "";
    if (preview) preview.src = "";
    previewWrap?.classList.add("hidden");
    clearBtn?.classList.add("hidden");
    setFeedMediaError("");
}

function setFeedMediaFile(file) {
    const preview = document.getElementById("feed-media-preview");
    const previewWrap = document.getElementById("feed-media-preview-wrap");
    const clearBtn = document.getElementById("clear-feed-media");
    if (!file) return;
    if (!FEED_MEDIA_TYPES.has(file.type)) {
        resetFeedMediaSelection();
        setFeedMediaError("Chỉ chấp nhận ảnh JPG, PNG, WebP, GIF.");
        return;
    }
    if (file.size > FEED_MEDIA_MAX_BYTES) {
        resetFeedMediaSelection();
        setFeedMediaError("Ảnh/GIF quá lớn, tối đa 8MB.");
        return;
    }
    if (selectedFeedMediaPreviewUrl) {
        URL.revokeObjectURL(selectedFeedMediaPreviewUrl);
    }
    selectedFeedMediaFile = file;
    selectedFeedMediaPreviewUrl = URL.createObjectURL(file);
    if (preview) preview.src = selectedFeedMediaPreviewUrl;
    previewWrap?.classList.remove("hidden");
    clearBtn?.classList.remove("hidden");
    setFeedMediaError("");
}

function initFeedMediaPicker() {
    const chooseBtn = document.getElementById("choose-feed-media");
    const clearBtn = document.getElementById("clear-feed-media");
    const input = document.getElementById("feed-media-input");
    if (!chooseBtn || !clearBtn || !input) return;
    chooseBtn.addEventListener("click", () => input.click());
    clearBtn.addEventListener("click", resetFeedMediaSelection);
    input.addEventListener("change", () => setFeedMediaFile(input.files?.[0]));
}

function getPastedFeedMediaFile(event) {
    const items = Array.from(event.clipboardData?.items || []);
    const mediaItem = items.find(item => FEED_MEDIA_TYPES.has(item.type));
    return mediaItem?.getAsFile() || null;
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
    const composer = document.getElementById("profile-composer-section");
    try {
        const res = await fetch("/api/v1/me", COMMUNITY_NO_CACHE_FETCH_OPTIONS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        communityViewer = await res.json();
        renderCommunityHeaderUser();
        composer?.classList.toggle("hidden", communityViewer?.can_edit === false);
    } catch (error) {
        console.error("fetchCommunityViewer error:", error);
        if (el) {
            el.innerHTML = `<span class="font-medium text-red-400">Lỗi kết nối Auth</span>`;
        }
        composer?.classList.add("hidden");
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

function initCommunityComposer() {
    const input = document.getElementById("default-taunt-input");
    const saveBtn = document.getElementById("save-profile-status");
    if (!input || !saveBtn) return;

    input.addEventListener("input", () => {
        updateComposerCount();
        setComposerStatus("");
    });
    input.addEventListener("paste", event => {
        const pastedFile = getPastedFeedMediaFile(event);
        if (!pastedFile) return;
        event.preventDefault();
        setFeedMediaFile(pastedFile);
        setComposerStatus("Đã dán ảnh/GIF vào bài đăng.", "success");
    });

    document.getElementById("clear-selected-match")?.addEventListener("click", () => {
        selectedReactionBet = null;
        syncSelectedMatchContext();
    });

    saveBtn.addEventListener("click", async () => {
        if (!communityViewer || communityViewer.can_edit === false) return;
        if (input.value.length > Number(input.maxLength || 160)) {
            setComposerStatus(`Tối đa ${input.maxLength} ký tự.`, "error");
            return;
        }
        if (!input.value.trim() && !selectedFeedMediaFile) {
            setComposerStatus("Nhập trạng thái hoặc chọn ảnh/GIF để đăng.", "error");
            return;
        }

        saveBtn.disabled = true;
        const oldText = saveBtn.textContent;
        saveBtn.textContent = "Đang đăng...";
        setComposerStatus("");

        try {
            let requestOptions;
            if (selectedFeedMediaFile) {
                const form = new FormData();
                form.append("content", input.value);
                if (selectedReactionBet?.match_id) {
                    form.append("match_id", String(Number(selectedReactionBet.match_id)));
                }
                form.append("media", selectedFeedMediaFile);
                requestOptions = { method: "POST", body: form };
            } else {
                const payload = { content: input.value };
                if (selectedReactionBet?.match_id) {
                    payload.match_id = Number(selectedReactionBet.match_id);
                }
                requestOptions = {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                };
            }

            const res = await fetch("/api/v1/me/statuses", requestOptions);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `Lỗi ${res.status}`);

            input.value = "";
            updateComposerCount();
            resetFeedMediaSelection();
            setComposerStatus("Đã đăng bài mới.", "success");
            selectedReactionBet = null;
            syncSelectedMatchContext();
            await fetchCommunityTimeline(true);
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

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("community-load-more")?.addEventListener("click", () => fetchCommunityTimeline(false));
    initCommunityComposer();
    initFeedMediaPicker();
    fetchCommunityViewer();
    fetchCommunityTimeline(true);
});
