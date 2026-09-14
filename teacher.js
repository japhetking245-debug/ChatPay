/* ────────────────────────────────────────────────────────────────────────────
   teacher.js — Teacher Dashboard, Session Management & Profile
   ──────────────────────────────────────────────────────────────────────────── */
'use strict';

let token = localStorage.getItem('talkroom_token');
let user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');

if (!token || !user || user.role !== 'teacher') {
  location.href = '/auth.html';
}

// DOM refs
const requests = document.querySelector('#requests');
const state = document.querySelector('#requests-status');
const toast = document.querySelector('#toast');
const earningTotal = document.querySelector('#earning-total');

// User Menu DOM
const userMenuWrap = document.querySelector('#user-menu-wrap');
const userPillBtn = document.querySelector('#user-pill-btn');
const teacherAvatar = document.querySelector('#teacher-avatar');
const teacherLabel = document.querySelector('#teacher-label');
const teacherName = document.querySelector('#teacher-name');
const dropdownTeacherName = document.querySelector('#dropdown-teacher-name');
const dropdownTeacherEmail = document.querySelector('#dropdown-teacher-email');
const menuProfileBtn = document.querySelector('#menu-profile-btn');
const menuLogoutBtn = document.querySelector('#menu-logout-btn');

// Profile Modal DOM
const profileModal = document.querySelector('#profile-modal');
const profileForm = document.querySelector('#profile-form');
const profileNameInput = document.querySelector('#profile-name');
const profileEmailInput = document.querySelector('#profile-email');
const togglePasswordBtn = document.querySelector('#toggle-password-fields');
const passwordFields = document.querySelector('#password-fields');
const profileCurrPass = document.querySelector('#profile-curr-pass');
const profileNewPass = document.querySelector('#profile-new-pass');
const profileMsg = document.querySelector('#profile-msg');
const profileSaveBtn = document.querySelector('#profile-save-btn');

// ── Helpers ─────────────────────────────────────────────────────────────────
function showToast(message, duration = 3500) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

function moneyTZS(amount) {
  try {
    return new Intl.NumberFormat('sw-TZ', { style: 'currency', currency: 'TZS' }).format(amount);
  } catch {
    return `TZS ${Number(amount).toLocaleString()}`;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) {
    let msg = data.detail || 'Something went wrong';
    if (Array.isArray(msg)) {
      msg = msg.map(e => `${e.loc ? e.loc.filter(x => x !== 'body').join('.') + ': ' : ''}${e.msg || JSON.stringify(e)}`).join('; ');
    } else if (typeof msg === 'object') {
      msg = JSON.stringify(msg);
    }
    throw new Error(msg);
  }
  return data;
}

// ── Header Profile Setup ────────────────────────────────────────────────────
function refreshTeacherHeader() {
  user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');
  if (!user) return;

  const firstName = user.name ? user.name.split(' ')[0] : 'Teacher';
  const initial = user.name ? user.name.charAt(0).toUpperCase() : '✦';

  if (teacherLabel) teacherLabel.textContent = firstName;
  if (teacherAvatar) teacherAvatar.textContent = initial;
  if (teacherName) teacherName.textContent = `${firstName}.`;
  if (dropdownTeacherName) dropdownTeacherName.textContent = user.name || 'Teacher';
  if (dropdownTeacherEmail) dropdownTeacherEmail.textContent = user.email || '';
}

// User Menu Dropdown Toggle
if (userPillBtn && userMenuWrap) {
  userPillBtn.addEventListener('click', e => {
    e.stopPropagation();
    const isOpen = userMenuWrap.classList.toggle('open');
    userPillBtn.setAttribute('aria-expanded', String(isOpen));
  });

  document.addEventListener('click', e => {
    if (!userMenuWrap.contains(e.target)) {
      userMenuWrap.classList.remove('open');
      userPillBtn.setAttribute('aria-expanded', 'false');
    }
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      userMenuWrap.classList.remove('open');
      userPillBtn.setAttribute('aria-expanded', 'false');
      closeProfileModal();
    }
  });
}

// Log Out Handler
if (menuLogoutBtn) {
  menuLogoutBtn.addEventListener('click', () => {
    localStorage.removeItem('talkroom_token');
    localStorage.removeItem('talkroom_user');
    location.href = '/auth.html?mode=login';
  });
}

// ── Render Booking Requests ─────────────────────────────────────────────────
function render(items) {
  const actionable = items.filter(item => item.status === 'requested');
  const accepted = items.filter(item => item.status === 'accepted');

  document.querySelector('#request-count').textContent = actionable.length;
  state.textContent = actionable.length
    ? `${actionable.length} waiting for you`
    : 'All caught up';

  // Calculate earnings from accepted/completed sessions
  const totalEarned = accepted.reduce((sum, item) => sum + (item.amount_cents || 0), 0);
  if (earningTotal) earningTotal.textContent = moneyTZS(totalEarned);

  if (!items.length) {
    requests.innerHTML = `
      <div class="empty-state">
        <span>☀</span>
        <h3>Your room is quiet for now.</h3>
        <p>New conversation requests from learners will appear here.</p>
      </div>
    `;
    return;
  }

  requests.innerHTML = items
    .map(
      item => `
      <article class="request-card">
        <div class="request-avatar">${item.learner_name.slice(0, 1)}</div>
        <div class="request-copy">
          <div>
            <h3>${item.learner_name}</h3>
            <span class="request-status ${item.status}">${item.status.replace('_', ' ')}</span>
          </div>
          <p><b>${item.topic}</b> · 30 min conversation with you</p>
        </div>
        <div class="request-price">
          <b>${moneyTZS(item.amount_cents)}</b>
          <small>session total</small>
        </div>
        ${
          item.status === 'requested'
            ? `<button class="accept-button" data-id="${item.id}">Accept request →</button>`
            : `<a class="open-chat" href="/chat.html?booking=${item.id}">Open chat →</a>`
        }
      </article>
    `
    )
    .join('');

  document.querySelectorAll('.accept-button').forEach(button =>
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = 'Opening chat…';
      try {
        await api(`/api/teacher/bookings/${button.dataset.id}/accept`, {
          method: 'POST',
        });
        showToast('Request accepted! Conversation room is ready.');
        await load();
      } catch (error) {
        state.textContent = error.message;
        showToast(error.message);
        button.disabled = false;
        button.textContent = 'Accept request →';
      }
    })
  );
}

async function load() {
  try {
    render(await api('/api/teacher/bookings'));
  } catch (error) {
    state.textContent = error.message;
  }
}

// ── Edit Profile Modal ──────────────────────────────────────────────────────
function openProfileModal() {
  userMenuWrap?.classList.remove('open');
  if (!user || !profileModal) return;

  profileNameInput.value = user.name || '';
  profileEmailInput.value = user.email || '';
  profileCurrPass.value = '';
  profileNewPass.value = '';
  profileMsg.textContent = '';
  profileMsg.className = 'profile-msg';
  passwordFields.style.display = 'none';
  togglePasswordBtn.textContent = '🔒 Change password ▾';

  profileModal.classList.add('show');
  profileModal.setAttribute('aria-hidden', 'false');
}

function closeProfileModal() {
  if (profileModal) {
    profileModal.classList.remove('show');
    profileModal.setAttribute('aria-hidden', 'true');
  }
}

if (menuProfileBtn) {
  menuProfileBtn.addEventListener('click', openProfileModal);
}
document.querySelectorAll('.close-profile-modal').forEach(btn =>
  btn.addEventListener('click', closeProfileModal)
);

if (togglePasswordBtn && passwordFields) {
  togglePasswordBtn.addEventListener('click', () => {
    const isHidden = passwordFields.style.display === 'none';
    passwordFields.style.display = isHidden ? 'grid' : 'none';
    togglePasswordBtn.textContent = isHidden ? '✕ Keep current password' : '🔒 Change password ▾';
    if (!isHidden) {
      profileCurrPass.value = '';
      profileNewPass.value = '';
    }
  });
}

if (profileForm) {
  profileForm.addEventListener('submit', async e => {
    e.preventDefault();
    if (!token) return;

    profileMsg.textContent = '';
    profileMsg.className = 'profile-msg';

    const payload = {
      name: profileNameInput.value.trim(),
      email: profileEmailInput.value.trim(),
    };

    if (passwordFields.style.display !== 'none' && profileNewPass.value) {
      if (!profileCurrPass.value) {
        profileMsg.textContent = 'Please enter your current password to set a new password.';
        profileMsg.className = 'profile-msg error';
        profileCurrPass.focus();
        return;
      }
      if (profileNewPass.value.length < 8) {
        profileMsg.textContent = 'New password must be at least 8 characters.';
        profileMsg.className = 'profile-msg error';
        profileNewPass.focus();
        return;
      }
      payload.current_password = profileCurrPass.value;
      payload.new_password = profileNewPass.value;
    }

    profileSaveBtn.disabled = true;
    profileSaveBtn.innerHTML = 'Saving changes…';

    try {
      const result = await api('/api/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });

      token = result.access_token;
      user = result.user;
      localStorage.setItem('talkroom_token', token);
      localStorage.setItem('talkroom_user', JSON.stringify(user));
      refreshTeacherHeader();

      profileMsg.textContent = 'Profile updated successfully!';
      profileMsg.className = 'profile-msg success';
      setTimeout(() => {
        closeProfileModal();
        showToast('Profile updated!');
      }, 1200);
    } catch (err) {
      profileMsg.textContent = err.message;
      profileMsg.className = 'profile-msg error';
    } finally {
      profileSaveBtn.disabled = false;
      profileSaveBtn.innerHTML = 'Save changes <span>→</span>';
    }
  });
}

// ── Initialize ──────────────────────────────────────────────────────────────
refreshTeacherHeader();
load();
