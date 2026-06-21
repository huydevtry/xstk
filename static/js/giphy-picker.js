(() => {
    const API_KEY = String(window.APP_GIPHY_API_KEY || "").trim();
    const RATING = "g";
    const LIMIT = 18;

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>\"']/g, ch => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;",
        }[ch]));
    }

    function getPreviewUrl(item) {
        const images = item?.images || {};
        return (
            images.fixed_width_small?.url ||
            images.fixed_height_small?.url ||
            images.fixed_width?.url ||
            images.fixed_height?.url ||
            images.original?.url ||
            ""
        );
    }

    function getShareUrl(item) {
        const images = item?.images || {};
        return (
            images.downsized_medium?.url ||
            images.downsized?.url ||
            images.original?.url ||
            ""
        );
    }

    function createResultCard(item) {
        const previewUrl = getPreviewUrl(item);
        const shareUrl = getShareUrl(item);
        if (!previewUrl || !shareUrl) return "";
        return `
            <button
                type="button"
                class="overflow-hidden rounded-2xl border border-slate-200 bg-white transition hover:border-sky-300 hover:shadow-sm"
                data-giphy-select="${escapeHtml(shareUrl)}"
            >
                <img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(item?.title || "GIPHY GIF")}" loading="lazy" class="h-28 w-full object-cover">
            </button>
        `;
    }

    function setStatus(node, message, tone = "neutral") {
        if (!node) return;
        node.textContent = message || "";
        node.className = "text-xs";
        if (tone === "error") {
            node.classList.add("text-rose-600");
        } else {
            node.classList.add("text-slate-500");
        }
    }

    function bindPicker(config) {
        const openBtn = document.getElementById(config.openButtonId);
        const modal = document.getElementById(config.modalId);
        const closeBtn = document.getElementById(config.closeButtonId);
        const searchInput = document.getElementById(config.searchInputId);
        const searchButton = document.getElementById(config.searchButtonId);
        const results = document.getElementById(config.resultsId);
        const resultsGrid = results?.firstElementChild || results;
        const status = document.getElementById(config.statusId);

        if (!openBtn || !modal || !closeBtn || !searchInput || !searchButton || !results || !resultsGrid || !status) {
            return;
        }

        if (!API_KEY) {
            openBtn.classList.add("hidden");
            return;
        }

        let isLoading = false;

        function setLoadingState(loading) {
            isLoading = loading;
            searchButton.disabled = loading;
            searchButton.textContent = loading ? "Đang tìm..." : "Tìm";
        }

        async function fetchGifs(query = "") {
            if (isLoading) return;
            setLoadingState(true);
            setStatus(status, query ? `Đang tìm GIF cho "${query}"...` : "Đang tải GIF thịnh hành...");
            resultsGrid.innerHTML = "";

            const endpoint = query
                ? `https://api.giphy.com/v1/gifs/search?api_key=${encodeURIComponent(API_KEY)}&q=${encodeURIComponent(query)}&limit=${LIMIT}&rating=${RATING}`
                : `https://api.giphy.com/v1/gifs/trending?api_key=${encodeURIComponent(API_KEY)}&limit=${LIMIT}&rating=${RATING}`;

            try {
                const response = await fetch(endpoint, { cache: "no-store" });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                const items = Array.isArray(payload.data) ? payload.data : [];
                if (!items.length) {
                    setStatus(status, query ? "Không tìm thấy GIF phù hợp." : "Chưa tải được GIF lúc này.");
                    resultsGrid.innerHTML = "";
                    return;
                }
                resultsGrid.innerHTML = items.map(createResultCard).join("");
                results.scrollTop = 0;
                setStatus(status, query ? `Đã tìm thấy ${items.length} GIF từ GIPHY.` : "GIF thịnh hành từ GIPHY.");
            } catch (error) {
                console.error("fetchGifs error:", error);
                setStatus(status, "Không thể tải thư viện GIPHY lúc này.", "error");
            } finally {
                setLoadingState(false);
            }
        }

        function openModal() {
            modal.classList.remove("hidden");
            document.body.style.overflow = "hidden";
            if (!resultsGrid.children.length) {
                fetchGifs("");
            }
            setTimeout(() => searchInput.focus(), 40);
        }

        function closeModal() {
            modal.classList.add("hidden");
            document.body.style.overflow = "";
        }

        openBtn.addEventListener("click", openModal);
        closeBtn.addEventListener("click", closeModal);
        modal.addEventListener("click", event => {
            if (event.target === modal) closeModal();
        });
        searchButton.addEventListener("click", () => fetchGifs(searchInput.value.trim()));
        searchInput.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                event.preventDefault();
                fetchGifs(searchInput.value.trim());
            }
        });
        results.addEventListener("click", event => {
            const button = event.target.closest("[data-giphy-select]");
            if (!button) return;
            config.onSelect?.({
                url: button.dataset.giphySelect,
                provider: "giphy",
            });
            closeModal();
        });
    }

    window.GiphyPicker = {
        init: bindPicker,
    };
})();
