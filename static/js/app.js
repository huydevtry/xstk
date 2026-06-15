document.addEventListener("DOMContentLoaded", () => {
    fetchUserProfile();
    fetchUpcomingMatches();
});

// 1. Lấy thông tin User đã login qua Cloudflare
async function fetchUserProfile() {
    const userInfoEl = document.getElementById("user-info");
    try {
        const response = await fetch("/api/v1/me");
        if (!response.ok) throw new Error("Chưa xác thực");
        const user = await response.json();
        
        const shortEmail = user.email.split('@')[0];
        userInfoEl.innerHTML = `👤 <span class="font-semibold text-white">${shortEmail}</span> | 🪙 <span class="text-yellow-400 font-bold">${user.total_points}đ</span>`;
    } catch (error) {
        userInfoEl.innerHTML = `<span class="text-red-400 font-medium">Lỗi kết nối Auth</span>`;
    }
}

// 2. Lấy danh sách trận đấu, Group theo ngày và render Accordion
async function fetchUpcomingMatches() {
    const matchListEl = document.getElementById("match-list");
    try {
        const response = await fetch("/api/v1/matches");
        const matches = await response.json();

        if (matches.length === 0) {
            matchListEl.innerHTML = `
                <div class="text-center py-12 text-gray-500 text-sm">
                    Hiện chưa có trận đấu nào sắp diễn ra.
                </div>`;
            return;
        }

        // Bước A: Group các trận đấu theo ngày (YYYY-MM-DD)
        const groupedMatches = {};
        matches.forEach(match => {
            const dateObj = new Date(match.start_time);
            // Lấy key dạng chuẩn để dễ sort: YYYY-MM-DD
            const year = dateObj.getFullYear();
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            const day = String(dateObj.getDate()).padStart(2, '0');
            const dateKey = `${year}-${month}-${day}`;

            if (!groupedMatches[dateKey]) {
                groupedMatches[dateKey] = [];
            }
            groupedMatches[dateKey].push(match);
        });

        // Bước B: Sort các ngày từ gần nhất đến xa nhất
        const sortedDates = Object.keys(groupedMatches).sort();

        // Bước C: Render HTML
        let htmlContent = '';
        
        sortedDates.forEach((dateKey, index) => {
            const dateMatches = groupedMatches[dateKey];
            const displayDate = dateKey.split('-').reverse().join('/'); // Chuyển thành DD/MM/YYYY
            
            // Chỉ expand (mở) ngày đầu tiên (index === 0), các ngày khác ẩn đi
            const isExpanded = index === 0;
            const contentClass = isExpanded ? '' : 'hidden';
            const iconRotation = isExpanded ? 'rotate-180' : '';

            // Render các trận đấu trong ngày đó
            let matchesHtml = dateMatches.map(match => {
                const matchDate = new Date(match.start_time);
                const timeStr = matchDate.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });

                return `
                    <div class="bg-gray-800 border border-gray-700 hover:border-emerald-500/50 rounded-xl p-4 shadow-sm transition duration-200 active:scale-[0.99] clickable-card mb-3 last:mb-0">
                        <div class="text-center mb-2">
                            <span class="text-xs bg-gray-900 text-emerald-400 font-mono font-semibold px-2 py-1 rounded">
                                ⏰ ${timeStr}
                            </span>
                        </div>
                        
                        <div class="flex items-center justify-between my-3 px-2">
                            <div class="w-2/5 text-center">
                                <p class="text-sm font-bold text-white truncate">${match.home_team}</p>
                                <span class="text-xs text-gray-400 block mt-0.5">Chủ nhà</span>
                            </div>
                            
                            <div class="w-1/5 text-center text-gray-500 font-black text-sm">VS</div>
                            
                            <div class="w-2/5 text-center">
                                <p class="text-sm font-bold text-white truncate">${match.away_team}</p>
                                <span class="text-xs text-gray-400 block mt-0.5">Khách</span>
                            </div>
                        </div>

                        <div class="mt-3">
                            <button onclick="openBetModal(${match.id}, '${match.home_team}', '${match.away_team}')" 
                                    class="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white text-xs font-bold py-2.5 px-4 rounded-lg shadow transition duration-150">
                                Đặt Cược Tỉ Số
                            </button>
                        </div>
                    </div>
                `;
            }).join('');

            // Bọc lại trong 1 Group (Accordion)
            htmlContent += `
                <div class="mb-4">
                    <button onclick="toggleGroup('${dateKey}')" class="w-full flex justify-between items-center bg-gray-800/80 p-3 rounded-lg border border-gray-700 focus:outline-none mb-2 active:bg-gray-700">
                        <span class="font-bold text-emerald-400 text-sm">📅 Ngày ${displayDate} <span class="text-gray-400 text-xs font-normal">(${dateMatches.length} trận)</span></span>
                        <svg id="icon-${dateKey}" class="w-5 h-5 text-gray-400 transform transition-transform duration-200 ${iconRotation}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>
                    
                    <div id="content-${dateKey}" class="${contentClass} transition-all duration-300 origin-top">
                        ${matchesHtml}
                    </div>
                </div>
            `;
        });

        matchListEl.innerHTML = htmlContent;

    } catch (error) {
        console.error(error);
        matchListEl.innerHTML = `
            <div class="text-center py-8 text-red-400 text-xs">
                Không thể tải danh sách trận đấu. Vui lòng thử lại sau!
            </div>`;
    }
}

// Hàm xử lý Đóng/Mở (Toggle) Group Trận đấu
window.toggleGroup = function(dateKey) {
    const content = document.getElementById(`content-${dateKey}`);
    const icon = document.getElementById(`icon-${dateKey}`);

    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.add('rotate-180');
    } else {
        content.classList.add('hidden');
        icon.classList.remove('rotate-180');
    }
};

// Hàm xử lý khi ấn cược
window.openBetModal = function(matchId, home, away) {
    alert(`Bạn đang chọn cược trận: ${home} vs ${away} (ID: ${matchId}).`);
};