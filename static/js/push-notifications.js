/**
 * push-notifications.js
 *
 * Handles browser-side push notification subscription lifecycle:
 *  - Check browser support
 *  - Request permission
 *  - Subscribe to push with VAPID public key
 *  - POST/DELETE subscription to backend
 *  - Update UI button state
 */

(function () {
  'use strict';

  const API_BASE = '/api/v1/push';
  let _vapidPublicKey = null;

  // ---------------------------------------------------------------------------
  // Utility: convert base64url to Uint8Array (required by PushManager)
  // ---------------------------------------------------------------------------
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
  }

  // ---------------------------------------------------------------------------
  // Fetch VAPID public key from server (cached after first call)
  // ---------------------------------------------------------------------------
  async function getVapidPublicKey() {
    if (_vapidPublicKey) return _vapidPublicKey;
    const res = await fetch(`${API_BASE}/vapid-public-key`);
    if (!res.ok) throw new Error('Push notifications not configured on server.');
    const data = await res.json();
    _vapidPublicKey = data.public_key;
    return _vapidPublicKey;
  }

  // ---------------------------------------------------------------------------
  // Check if push is supported by this browser
  // ---------------------------------------------------------------------------
  function isPushSupported() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  // ---------------------------------------------------------------------------
  // Get current push subscription (or null)
  // ---------------------------------------------------------------------------
  async function getCurrentSubscription() {
    const reg = await navigator.serviceWorker.ready;
    return reg.pushManager.getSubscription();
  }

  // ---------------------------------------------------------------------------
  // Subscribe: request permission → PushManager.subscribe → POST to server
  // ---------------------------------------------------------------------------
  async function enablePush() {
    if (!isPushSupported()) {
      alert('Trình duyệt của bạn không hỗ trợ push notification.');
      return false;
    }

    // Request notification permission
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.warn('[Push] Permission denied.');
      return false;
    }

    try {
      const publicKey = await getVapidPublicKey();
      const reg = await navigator.serviceWorker.ready;

      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });

      const keys = subscription.toJSON().keys || {};
      const res = await fetch(`${API_BASE}/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: subscription.endpoint,
          p256dh: keys.p256dh,
          auth: keys.auth,
          user_agent: navigator.userAgent,
        }),
      });

      if (!res.ok) throw new Error('Server rejected subscription.');
      console.info('[Push] Subscribed successfully.');
      return true;
    } catch (err) {
      console.error('[Push] Subscribe failed:', err);
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Unsubscribe: PushManager.unsubscribe → DELETE from server
  // ---------------------------------------------------------------------------
  async function disablePush() {
    try {
      const subscription = await getCurrentSubscription();
      if (!subscription) return true;

      await fetch(`${API_BASE}/unsubscribe`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });

      await subscription.unsubscribe();
      console.info('[Push] Unsubscribed.');
      return true;
    } catch (err) {
      console.error('[Push] Unsubscribe failed:', err);
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Update button UI based on current state
  // ---------------------------------------------------------------------------
  async function _updateButtonUI(btn) {
    if (!btn) return;
    if (!isPushSupported()) {
      btn.style.display = 'none';
      return;
    }

    const permission = Notification.permission;
    const sub = await getCurrentSubscription();
    const slash = document.getElementById('push-bell-slash');

    if (permission === 'denied') {
      btn.setAttribute('data-push-state', 'denied');
      btn.title = 'Thông báo bị chặn trong cài đặt trình duyệt';
      btn.classList.remove('text-sky-600', 'border-sky-300');
      btn.classList.add('text-slate-300', 'border-slate-200', 'opacity-50', 'cursor-not-allowed');
      // Show slash through bell
      if (slash) slash.setAttribute('stroke-dasharray', '30');
    } else if (sub) {
      btn.setAttribute('data-push-state', 'enabled');
      btn.title = 'Tắt thông báo';
      btn.classList.remove('text-slate-400', 'border-slate-200', 'opacity-50', 'cursor-not-allowed');
      btn.classList.add('text-sky-600', 'border-sky-300');
      // No slash — bell is active
      if (slash) slash.setAttribute('stroke-dasharray', '0');
    } else {
      btn.setAttribute('data-push-state', 'disabled');
      btn.title = 'Bật thông báo';
      btn.classList.remove('text-sky-600', 'border-sky-300', 'opacity-50', 'cursor-not-allowed');
      btn.classList.add('text-slate-400', 'border-slate-200');
      // Show slash through bell
      if (slash) slash.setAttribute('stroke-dasharray', '30');
    }
  }

  // ---------------------------------------------------------------------------
  // Toggle handler attached to the bell button
  // ---------------------------------------------------------------------------
  async function handlePushToggle(btn) {
    const state = btn.getAttribute('data-push-state');
    btn.disabled = true;

    if (state === 'enabled') {
      await disablePush();
    } else if (state === 'disabled') {
      await enablePush();
    }

    btn.disabled = false;
    await _updateButtonUI(btn);
  }

  // ---------------------------------------------------------------------------
  // Init — register SW + wire up button
  // ---------------------------------------------------------------------------
  async function initPushNotifications() {
    if (!isPushSupported()) return;

    // Register service worker if not already registered
    try {
      await navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
    } catch (err) {
      console.warn('[SW] Registration failed:', err);
      return;
    }

    // Wire up bell button if present
    const btn = document.getElementById('push-toggle-btn');
    if (btn) {
      await _updateButtonUI(btn);
      btn.addEventListener('click', () => handlePushToggle(btn));
    }
  }

  // Run on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPushNotifications);
  } else {
    initPushNotifications();
  }

  // Expose for manual use if needed
  window.pushNotifications = { enable: enablePush, disable: disablePush, init: initPushNotifications };
})();
