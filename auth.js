/* ────────────────────────────────────────────────────────────────────────────
   auth.js — ChatPay Auth Redirect (Moxera Agencies)
   Tab switching + dev test account quick-login
   ──────────────────────────────────────────────────────────────────────────── */
'use strict';

// ── Tab switching ─────────────────────────────────────────────────────────────
const tabBtns = document.querySelectorAll('.auth-tab-btn');
const panels = document.querySelectorAll('.auth-panel');

function switchTab(panelId) {
  tabBtns.forEach(btn => {
    const isActive = btn.dataset.panel === panelId;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });
  panels.forEach(panel => {
    panel.classList.toggle('active', panel.id === panelId);
  });
}

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.panel));
});

// Check for ?mode=login or ?mode=register in URL
const initialMode = new URLSearchParams(location.search).get('mode');
if (initialMode === 'login') {
  switchTab('panel-login');
} else if (initialMode === 'register') {
  switchTab('panel-register');
}

// "Jisajili hapa" link on login panel switches back to register
const switchToRegister = document.querySelector('#switch-to-register');
if (switchToRegister) {
  switchToRegister.addEventListener('click', () => switchTab('panel-register'));
}

// "Ingia hapa" link on register panel switches to login
const switchToLogin = document.querySelector('#switch-to-login');
if (switchToLogin) {
  switchToLogin.addEventListener('click', () => switchTab('panel-login'));
}

// ── Dev Test Accounts (quick local login for testing) ────────────────────────
async function devLogin(email, password) {
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Login failed');

    localStorage.setItem('talkroom_token', result.access_token);
    localStorage.setItem('talkroom_user', JSON.stringify(result.user));

    const pendingChat = localStorage.getItem('helachat_pending_chat');
    if (pendingChat) {
      localStorage.removeItem('helachat_pending_chat');
      window.location.href = pendingChat;
      return;
    }

    window.location.href =
      result.user.role === 'teacher' && result.user.teacher_status !== 'active'
        ? '/teacher-enrollment.html'
        : result.user.role === 'teacher' && !result.user.teacher_profile_completed
          ? '/teacher-profile.html'
          : result.user.role === 'teacher'
            ? '/teacher.html'
            : '/?welcome=1';
  } catch (err) {
    alert('Hitilafu ya majaribio: ' + (err.message || err));
  }
}

const TEACHER_CREDS = { email: 'teacher@talkroom.com', password: 'Password123!' };
const LEARNER_CREDS = { email: 'learner@talkroom.com', password: 'Password123!' };

[
  ['#btn-quick-teacher', TEACHER_CREDS],
  ['#btn-quick-teacher-login', TEACHER_CREDS],
  ['#btn-quick-learner', LEARNER_CREDS],
  ['#btn-quick-learner-login', LEARNER_CREDS],
].forEach(([selector, creds]) => {
  const btn = document.querySelector(selector);
  if (btn) {
    btn.addEventListener('click', () => devLogin(creds.email, creds.password));
  }
});
