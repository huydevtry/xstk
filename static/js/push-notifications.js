/**
 * push-notifications.js
 *
 * Responsibilities:
 *  1. Register Service Worker
 *  2. Auto-request notification permission + subscribe on first load
 *  3. Push toggle button in user menu (on/off + pill label)
 *  4. Notification inbox bell: fetch list, show badge, open/close panel
 */

(function () {
  'use strict';

  const API_PUSH   = '/api/v1/push';
  const API_NOTIF  = '/api/v1/notifications';
  const LOG  = (...a) => console.info('[Push]',  ...a);
  const WARN = (...a) => console.warn('[Push]',  ...a);
  const ERR  = (...a) => console.error('[Push]', ...a);

  let _vapidKey = null;
  let _swReg    = null;

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------
  function urlBase64ToUint8Array(b64) {
    const pad = '='.repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  }

  function isPushSupported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  function timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = Date.now() - new Date(isoStr + 'Z').getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'Vừa xong';
    if (m < 60) return `${m} phút trước`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} giờ trước`;
    return `${Math.floor(h / 24)} ngày trước`;
  }

  // -------------------------------------------------------------------------
  // Service Worker
  // -------------------------------------------------------------------------
  async function registerSW() {
    if (_swReg) return _swReg;
    _swReg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    LOG('SW registered.');
    return _swReg;
  }

  async function getVapidKey() {
    if (_vapidKey) return _vapidKey;
    const res = await fetch(`${API_PUSH}/vapid-public-key`);
    if (!res.ok) throw new Error(`VAPID key endpoint: ${res.status}`);
    _vapidKey = (await res.json()).public_key;
    return _vapidKey;
  }

  async function getCurrentSub() {
    const reg = _swReg || await navigator.serviceWorker.ready;
    return reg.pushManager.getSubscription();
  }

  // -------------------------------------------------------------------------
  // Subscribe / Unsubscribe
  // -------------------------------------------------------------------------
  async function enablePush() {
    if (!isPushSupported()) return false;

    LOG('Requesting permission…');
    const perm = await Notification.requestPermission();
    LOG('Permission:', perm);
    if (perm !== 'granted') return false;

    try {
      const key = await getVapidKey();
      const reg = _swReg || await navigator.serviceWorker.ready;

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });

      const keys = sub.toJSON().keys || {};
      const res  = await fetch(`${API_PUSH}/subscribe`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          endpoint:   sub.endpoint,
          p256dh:     keys.p256dh,
          auth:       keys.auth,
          user_agent: navigator.userAgent,
        }),
      });
      if (!res.ok) throw new Error(`Subscribe rejected: ${res.status}`);
      LOG('Subscribed OK.');
      return true;
    } catch (err) {
      ERR('enablePush failed:', err);
      return false;
    }
  }

  async function disablePush() {
    try {
      const sub = await getCurrentSub();
      if (!sub) return true;
      await fetch(`${API_PUSH}/unsubscribe`, {
        method:  'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ endpoint: sub.endpoint }),
      });
      await sub.unsubscribe();
      LOG('Unsubscribed.');
      return true;
    } catch (err) {
      ERR('disablePush failed:', err);
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // Push toggle pill in user menu
  // -------------------------------------------------------------------------
  async function updateTogglePill() {
    const pill = document.getElementById('push-toggle-label');
    const btn  = document.getElementById('push-toggle-btn');
    if (!pill) return;

    if (!isPushSupported()) {
      pill.textContent = 'Không hỗ trợ';
      pill.className   = 'push-toggle-pill off';
      if (btn) btn.disabled = true;
      return;
    }

    const perm = Notification.permission;
    const sub  = await getCurrentSub();

    if (perm === 'denied') {
      pill.textContent = 'Bị chặn';
      pill.className   = 'push-toggle-pill denied';
      if (btn) btn.disabled = true;
    } else if (sub) {
      pill.textContent = 'BẬT';
      pill.className   = 'push-toggle-pill on';
    } else {
      pill.textContent = 'TẮT';
      pill.className   = 'push-toggle-pill off';
    }
  }

  async function handlePushToggle() {
    const sub = await getCurrentSub();
    const btn = document.getElementById('push-toggle-btn');
    if (btn) btn.disabled = true;

    if (sub) {
      await disablePush();
    } else {
      await enablePush();
    }

    if (btn) btn.disabled = false;
    await updateTogglePill();
  }

  // -------------------------------------------------------------------------
  // Notification inbox
  // -------------------------------------------------------------------------
  let _notifOpen = false;

  async function loadNotifications() {
    const list  = document.getElementById('notif-list');
    const badge = document.getElementById('notif-badge');
    if (!list) return;

    try {
      const res  = await fetch(API_NOTIF, { credentials: 'include', cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();

      // Update badge
      if (badge) {
        if (data.unread_count > 0) {
          badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
          badge.classList.remove('hidden');
        } else {
          badge.classList.add('hidden');
        }
      }

      // Render list
      if (!data.notifications || data.notifications.length === 0) {
        list.innerHTML = '<p class="notif-empty">Chưa có thông báo nào</p>';
        return;
      }

      list.innerHTML = data.notifications.map(n => {
        const icon = _iconForTitle(n.title);
        return `
          <a href="${n.url || '/'}" class="notif-item${n.is_read ? '' : ' unread'}" data-id="${n.id}">
            <div class="notif-item-icon">${icon}</div>
            <div class="notif-item-body">
              <div class="notif-item-title">${_esc(n.title)}</div>
              <div class="notif-item-text">${_esc(n.body)}</div>
              <div class="notif-item-time">${timeAgo(n.created_at)}</div>
            </div>
            ${n.is_read ? '' : '<div class="notif-unread-dot"></div>'}
          </a>`;
      }).join('');

    } catch (err) {
      WARN('loadNotifications failed:', err);
    }
  }

  function _iconForTitle(title) {
    if (!title) return '🔔';
    if (title.includes('🏆') || title.includes('Kết quả')) return '🏆';
    if (title.includes('❤️') || title.includes('thích'))    return '❤️';
    if (title.includes('💬') || title.includes('Bình luận')) return '💬';
    if (title.includes('😢') || title.includes('Thua'))     return '😢';
    if (title.includes('🤝') || title.includes('hòa'))      return '🤝';
    return '🔔';
  }

  function _esc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function openNotifPanel() {
    const panel = document.getElementById('notif-panel');
    if (!panel) return;
    panel.classList.remove('hidden');
    _notifOpen = true;
    loadNotifications();
  }

  function closeNotifPanel() {
    const panel = document.getElementById('notif-panel');
    if (!panel) return;
    panel.classList.add('hidden');
    _notifOpen = false;
  }

  function toggleNotifPanel() {
    if (_notifOpen) closeNotifPanel();
    else openNotifPanel();
  }

  async function markAllRead() {
    await fetch(`${API_NOTIF}/read-all`, { method: 'POST', credentials: 'include' });
    await loadNotifications();  // refresh badge + list
  }

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------
  async function initPushNotifications() {
    LOG('Init. Push supported:', isPushSupported());
    if (!isPushSupported()) return;

    // 1. Register SW
    try {
      await registerSW();
      await navigator.serviceWorker.ready;
      LOG('SW ready.');
    } catch (err) {
      ERR('SW registration failed:', err);
      return;
    }

    // 2. Wire up push toggle in user menu
    const toggleBtn = document.getElementById('push-toggle-btn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', handlePushToggle);
    }
    await updateTogglePill();

    // 3. Wire up notification inbox bell
    const bellBtn     = document.getElementById('notif-bell-btn');
    const readAllBtn  = document.getElementById('notif-read-all');
    const wrap        = document.getElementById('notif-wrap');

    if (bellBtn) bellBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleNotifPanel(); });
    if (readAllBtn) readAllBtn.addEventListener('click', (e) => { e.stopPropagation(); markAllRead(); });

    // Close panel when clicking outside
    document.addEventListener('click', (e) => {
      if (_notifOpen && wrap && !wrap.contains(e.target)) closeNotifPanel();
    });

    // 4. Fetch initial badge count (don't open panel)
    loadNotifications();

    // 5. Auto-request permission if not yet asked
    if (Notification.permission === 'default') {
      LOG('Permission default — auto-prompting in 1.5s…');
      await new Promise(r => setTimeout(r, 1500));
      const granted = await enablePush();
      await updateTogglePill();
      if (granted) LOG('Auto-subscribed on page load.');
    } else {
      LOG('Permission already:', Notification.permission);
    }
  }

  // Bootstrap
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPushNotifications);
  } else {
    initPushNotifications();
  }

  // Expose for DevTools debugging
  window.pushNotifications = {
    enable:  enablePush,
    disable: disablePush,
    status:  async () => {
      const sub = await getCurrentSub();
      console.table({
        'Supported':  isPushSupported(),
        'Permission': Notification.permission,
        'Subscribed': !!sub,
      });
    },
  };

  LOG('push-notifications.js loaded.');
})();
