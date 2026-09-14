/* ────────────────────────────────────────────────────────────────────────────
   script.js — ChatPay "Chat na Ulipwe" Platform Logic
   ──────────────────────────────────────────────────────────────────────────── */
'use strict';

// ── DOM References ──────────────────────────────────────────────────────────
const toast = document.querySelector('#toast');
const headerWalletAmount = document.querySelector('#header-wallet-amount');
const modalWalletBalance = document.querySelector('#modal-wallet-balance');
const partnersGrid = document.querySelector('#partners-grid');
const topicFilters = document.querySelector('#topic-filters');
const payoutTicker = document.querySelector('#payout-ticker');

// User Nav DOM
const loggedOutActions = document.querySelector('#logged-out-actions');
const userMenuWrap = document.querySelector('#user-menu-wrap');
const userPillBtn = document.querySelector('#user-pill-btn');
const navUserAvatar = document.querySelector('#nav-user-avatar');
const navUserName = document.querySelector('#nav-user-name');
const dropdownUserName = document.querySelector('#dropdown-user-name');
const dropdownUserEmail = document.querySelector('#dropdown-user-email');
const dropdownUserRole = document.querySelector('#dropdown-user-role');
const menuWithdrawBtn = document.querySelector('#menu-withdraw-btn');
const menuSessionsBtn = document.querySelector('#menu-sessions-btn');
const menuProfileBtn = document.querySelector('#menu-profile-btn');
const menuLogoutBtn = document.querySelector('#menu-logout-btn');

// Withdrawal Modal DOM
const withdrawModal = document.querySelector('#withdraw-modal');
const withdrawForm = document.querySelector('#withdraw-form');
const withdrawPhoneInput = document.querySelector('#withdraw-phone');
const withdrawAmountInput = document.querySelector('#withdraw-amount');
const withdrawMsg = document.querySelector('#withdraw-msg');
const withdrawSubmitBtn = document.querySelector('#withdraw-submit-btn');
const networkSelector = document.querySelector('#network-selector');

// Tips Modal DOM
const tipsModal = document.querySelector('#tips-modal');
const navTipsBtn = document.querySelector('#nav-tips-btn');

// Sessions & History Modal DOM
const sessionsModal = document.querySelector('#sessions-modal');
const sessionsList = document.querySelector('#sessions-list');

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

// State
let allPartners = [];
let userWallet = { balance_tsh: 0, total_earned: 0, total_withdrawn: 0 };
let selectedProvider = 'mpesa';

// ── Helpers ─────────────────────────────────────────────────────────────────
function showToast(message, duration = 3800) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

function moneyTZS(amount) {
  try {
    return new Intl.NumberFormat('sw-TZ', { style: 'currency', currency: 'TZS', maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `TSh ${Number(amount).toLocaleString()}`;
  }
}

function getAuth() {
  const token = localStorage.getItem('talkroom_token');
  const user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');
  return { token, user };
}

async function api(path, options = {}) {
  const { token } = getAuth();
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok) {
    let msg = data.detail || 'Hitilafu imetokea. Tafadhali jaribu tena.';
    if (Array.isArray(msg)) {
      msg = msg.map(e => e.msg || JSON.stringify(e)).join('; ');
    }
    throw new Error(msg);
  }
  return data;
}

// ── Auth & Wallet UI ────────────────────────────────────────────────────────
async function refreshWallet() {
  const { token } = getAuth();
  if (!token) {
    if (headerWalletAmount) headerWalletAmount.textContent = 'TSh 0.00';
    if (modalWalletBalance) modalWalletBalance.textContent = 'TSh 0.00';
    return;
  }
  try {
    const data = await api('/api/me/wallet');
    userWallet = data;
    const formatted = moneyTZS(data.balance_tsh || 0);
    if (headerWalletAmount) headerWalletAmount.textContent = formatted;
    if (modalWalletBalance) modalWalletBalance.textContent = formatted;
    if (withdrawPhoneInput && data.phone_number && !withdrawPhoneInput.value) {
      withdrawPhoneInput.value = data.phone_number;
    }
  } catch (err) {
    console.warn('[Wallet Refresh]', err);
  }
}

function updateNavAuth() {
  const { token, user } = getAuth();

  if (token && user) {
    if (loggedOutActions) loggedOutActions.style.display = 'none';
    if (userMenuWrap) userMenuWrap.style.display = 'inline-block';

    const firstName = user.name ? user.name.split(' ')[0] : 'Mtumiaji';
    const initial = user.name ? user.name.charAt(0).toUpperCase() : '✦';

    if (navUserName) navUserName.textContent = firstName;
    if (navUserAvatar) navUserAvatar.textContent = initial;
    if (dropdownUserName) dropdownUserName.textContent = user.name || 'Mtumiaji wa ChatPay';
    if (dropdownUserEmail) dropdownUserEmail.textContent = user.email || '';
    if (dropdownUserRole) dropdownUserRole.textContent = 'Akaunti Hai';

    refreshWallet();
  } else {
    if (loggedOutActions) loggedOutActions.style.display = 'flex';
    if (userMenuWrap) userMenuWrap.style.display = 'none';
    if (headerWalletAmount) headerWalletAmount.textContent = 'TSh 0.00';
  }
}

// ── Live Partners Grid & Filtering ──────────────────────────────────────────
async function loadLivePartners() {
  if (!partnersGrid) return;
  try {
    const data = await api('/api/live-partners');
    allPartners = data.partners || [];
    renderPartners(allPartners);
  } catch (err) {
    console.error('[Live Partners Error]', err);
    partnersGrid.innerHTML = `<p class="sessions-loading">Hitilafu ya kupakia wazungu live. Tafadhali onyesha upya ukurasa.</p>`;
  }
}

// ── Daily Partner Locking Utilities ──────────────────────────────────────────
function getTodayDateKey() {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function isPartnerChattedToday(pName) {
  if (!pName) return false;
  try {
    const raw = localStorage.getItem('chatpay_chatted_today');
    if (!raw) return false;
    const store = JSON.parse(raw);
    const today = getTodayDateKey();
    const list = store[today] || [];
    return list.some(name => name.toLowerCase() === pName.trim().toLowerCase());
  } catch {
    return false;
  }
}

function renderPartners(partners) {
  if (!partnersGrid) return;
  if (!partners.length) {
    partnersGrid.innerHTML = `<div class="empty-state"><span>🔍</span><h3>Hakuna mzungu aliyepatikana kwa mada hii</h3><p>Tafadhali chagua mada nyingine kuona wazungu waliopo live.</p></div>`;
    return;
  }

  partnersGrid.innerHTML = partners
    .map(
      p => {
        const isLocked = Boolean(p.chatted_today || isPartnerChattedToday(p.name));
        return `
      <article class="partner-card ${isLocked ? 'is-locked' : ''}" data-id="${p.id}" data-topic="${p.topic}">
        <div class="photo-wrap">
          <img src="${p.avatar}" alt="${p.name}" loading="lazy">
          ${isLocked
            ? `<div class="partner-online-chip" style="background:#3b3223e6;color:#fedb98"><span class="online-dot" style="background:#f5bd58;box-shadow:none"></span> IMELIPWA LEO</div>
               <div class="partner-card-lock-badge">🔒 Rudi Kesho</div>`
            : `<div class="partner-online-chip"><span class="online-dot"></span> LIVE SASA</div>`
          }
          <div class="partner-country-chip">${p.flag} ${p.country}</div>
        </div>
        <div class="partner-head">
          <div>
            <h3>${p.name}</h3>
            <p class="partner-topic">🏷️ ${p.topic}</p>
          </div>
        </div>
        <div class="partner-payout-row">
          <span class="partner-duration">⏱️ Ujumbe 11</span>
          <div class="partner-rate">
            ${moneyTZS(p.amount_tsh)}
            <small>${isLocked ? 'Imelipwa leo 🔒' : `TSh ${Number(p.rate_per_min).toLocaleString()} / dk`}</small>
          </div>
        </div>
        ${isLocked
          ? `<button class="chat-now-btn locked-chat-btn" type="button" data-partner="${p.name}">
              Umeshachat Naye Leo (Inafunguka Kesho) 🔒
            </button>`
          : `<button class="chat-now-btn start-chat-btn" type="button" data-partner="${p.name}" data-country="${p.country}" data-topic="${p.topic}" data-minutes="${p.minutes}" data-amount="${p.amount_tsh}" data-avatar="${p.avatar}" data-bio="${p.bio || ''}">
              Anza Kuchat Papo Hapo 💬
            </button>`
        }
      </article>
    `;
      }
    )
    .join('');

  // Wire click to start chat or show locked notification
  partnersGrid.querySelectorAll('.chat-now-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const partner = btn.dataset.partner;

      if (btn.classList.contains('locked-chat-btn')) {
        showToast(`🔒 Umeshakamilisha mazungumzo na ${partner} leo na kupokea malipo! Mazungumzo mapya na ${partner} yatafunguliwa tena kesho.`);
        return;
      }

      const { token } = getAuth();
      const topic = btn.dataset.topic;
      const minutes = btn.dataset.minutes;
      const amount = btn.dataset.amount;
      const avatar = encodeURIComponent(btn.dataset.avatar);
      const bio = encodeURIComponent(btn.dataset.bio);

      const chatUrl = `/chat.html?partner=${encodeURIComponent(partner)}&topic=${encodeURIComponent(topic)}&minutes=${minutes}&amount=${amount}&avatar=${avatar}&bio=${bio}`;

      if (!token) {
        localStorage.setItem('helachat_pending_chat', chatUrl);
        location.href = `/auth.html?mode=register&intent=chat&partner=${encodeURIComponent(partner)}`;
        return;
      }

      location.href = chatUrl;
    });
  });
}

// Topic filter clicks
if (topicFilters) {
  topicFilters.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      topicFilters.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const filter = btn.dataset.filter.toLowerCase();
      if (filter === 'all') {
        renderPartners(allPartners);
      } else {
        const filtered = allPartners.filter(p => p.topic.toLowerCase().includes(filter));
        renderPartners(filtered);
      }
    });
  });
}

// ── Live Payouts Ticker ─────────────────────────────────────────────────────
async function loadRecentPayouts() {
  if (!payoutTicker) return;
  try {
    const data = await api('/api/recent-payouts');
    const payouts = data.payouts || [];
    if (payouts.length) {
      // Duplicate items to ensure smooth infinite loop
      const itemsHtml = payouts
        .concat(payouts)
        .map(
          p => `
          <div class="payout-item">
            <span class="payout-dot">●</span>
            <span class="payout-name">${p.name} (${p.city})</span> amepokea
            <span class="payout-sum">${moneyTZS(p.amount_tsh)}</span>
            <span class="payout-provider">${p.provider}</span>
            <span class="payout-time">${p.time_ago}</span>
          </div>
        `
        )
        .join('');
      payoutTicker.innerHTML = itemsHtml;
    }
  } catch (err) {
    console.warn('[Payouts Ticker]', err);
  }
}

// ── Withdrawal Modal (Kutoa Pesa) ───────────────────────────────────────────
function openWithdrawModal() {
  const { token } = getAuth();
  if (!token) {
    showToast('Tafadhali ingia au jikisajili kwanza ili kutoa salio lako.');
    setTimeout(() => {
      location.href = '/auth.html?mode=login';
    }, 1200);
    return;
  }
  refreshWallet();
  if (withdrawModal) withdrawModal.classList.add('show');
}

function closeWithdrawModal() {
  if (withdrawModal) withdrawModal.classList.remove('show');
  if (withdrawMsg) {
    withdrawMsg.textContent = '';
    withdrawMsg.className = 'profile-msg';
  }
}

document.querySelectorAll('.open-withdraw-modal').forEach(btn => {
  btn.addEventListener('click', openWithdrawModal);
});
document.querySelectorAll('.close-withdraw-modal').forEach(btn => {
  btn.addEventListener('click', closeWithdrawModal);
});

if (networkSelector) {
  networkSelector.querySelectorAll('.network-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      networkSelector.querySelectorAll('.network-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedProvider = btn.dataset.provider;
    });
  });
}

// Amount presets
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.id === 'preset-all') {
      if (withdrawAmountInput) withdrawAmountInput.value = userWallet.balance_tsh || 0;
    } else {
      const val = btn.dataset.val;
      if (withdrawAmountInput) withdrawAmountInput.value = val;
    }
  });
});

// Withdrawal Form Submit
if (withdrawForm) {
  withdrawForm.addEventListener('submit', async e => {
    e.preventDefault();
    if (!withdrawSubmitBtn) return;

    const amount = Number(withdrawAmountInput.value);
    const phone = withdrawPhoneInput.value.trim();

    if (!amount || amount < 1000) {
      withdrawMsg.textContent = 'Kiasi cha chini cha kutoa ni TSh 1,000.';
      withdrawMsg.className = 'profile-msg error';
      return;
    }

    if (!phone || phone.length < 9) {
      withdrawMsg.textContent = 'Tafadhali weka namba sahihi ya simu.';
      withdrawMsg.className = 'profile-msg error';
      return;
    }

    withdrawSubmitBtn.disabled = true;
    withdrawSubmitBtn.textContent = 'Inachakata ombi…';
    withdrawMsg.textContent = '';

    try {
      const res = await api('/api/wallet/withdraw', {
        method: 'POST',
        body: JSON.stringify({
          amount_tsh: amount,
          provider: selectedProvider,
          phone_number: phone,
        }),
      });

      withdrawMsg.textContent = res.message;
      withdrawMsg.className = 'profile-msg success';
      showToast(`🎉 ${res.message}`);
      refreshWallet();

      setTimeout(() => {
        closeWithdrawModal();
      }, 2500);
    } catch (err) {
      withdrawMsg.textContent = err.message;
      withdrawMsg.className = 'profile-msg error';
    } finally {
      withdrawSubmitBtn.disabled = false;
      withdrawSubmitBtn.innerHTML = 'Toa Pesa Sasa <span>↗</span>';
    }
  });
}

// ── Tips Modal ──────────────────────────────────────────────────────────────
if (navTipsBtn && tipsModal) {
  navTipsBtn.addEventListener('click', e => {
    e.preventDefault();
    tipsModal.classList.add('show');
  });
}
document.querySelectorAll('.close-tips-modal').forEach(btn => {
  btn.addEventListener('click', () => {
    if (tipsModal) tipsModal.classList.remove('show');
  });
});

// ── Sessions & Earnings History Modal ───────────────────────────────────────
if (menuWithdrawBtn) {
  menuWithdrawBtn.addEventListener('click', () => {
    if (userMenuWrap) userMenuWrap.classList.remove('open');
    openWithdrawModal();
  });
}

if (menuSessionsBtn) {
  menuSessionsBtn.addEventListener('click', async () => {
    if (userMenuWrap) userMenuWrap.classList.remove('open');
    if (sessionsModal) sessionsModal.classList.add('show');

    if (!sessionsList) return;
    sessionsList.innerHTML = `<p class="sessions-loading">Inapakia taarifa zako za malipo…</p>`;

    try {
      const [walletData, bookingsData] = await Promise.allSettled([
        api('/api/me/wallet'),
        api('/api/learner/bookings'),
      ]);

      const data = walletData.status === 'fulfilled' ? walletData.value : { balance_tsh: 0, total_earned: 0, total_withdrawn: 0 };
      const bookings = bookingsData.status === 'fulfilled' && Array.isArray(bookingsData.value) ? bookingsData.value : [];
      const earnings = data.earnings || [];
      const withdrawals = data.withdrawals || [];

      if (!bookings.length && !earnings.length && !withdrawals.length) {
        sessionsList.innerHTML = `
          <div class="empty-state">
            <span>💬</span>
            <h3>Bado haujaanza kuchat</h3>
            <p>Chagua mzungu yeyote aliyepo live kwenye ukurasa wa nyumbani au mwalimu uanze kupata huduma!</p>
          </div>
        `;
        return;
      }

      let html = `
        <div style="background:#f4f8ed;border-radius:6px;padding:14px;display:flex;justify-content:space-between;margin-bottom:14px;border:1px solid #dce8cf">
          <div><small style="color:#697d70;font-size:10px;display:block">JUMLA ULIZOPATA</small><b style="color:#1c4b14;font-size:15px">${moneyTZS(data.total_earned)}</b></div>
          <div><small style="color:#697d70;font-size:10px;display:block">JUMLA ULIZOTOA</small><b style="color:#b2472b;font-size:15px">${moneyTZS(data.total_withdrawn)}</b></div>
          <div><small style="color:#697d70;font-size:10px;display:block">SALIO LILILOBAKI</small><b style="color:#1d4c14;font-size:15px">${moneyTZS(data.balance_tsh)}</b></div>
        </div>
      `;

      if (bookings.length) {
        html += `<h4 style="margin:14px 0 10px;font-size:14px;color:#183a31;font-weight:700">👩‍🏫 Mikutano na Walimu (Teacher Sessions)</h4>`;
        html += bookings
          .map(
            b => `
          <div class="learner-session-card" style="border:1.5px solid ${b.status === 'accepted' ? '#8bc34a' : '#d2dfd6'};background:${b.status === 'accepted' ? '#fbfef7' : '#fff'};margin-bottom:10px">
            <div class="session-meta">
              <div class="session-avatar" style="background:#183a31;color:#fff">${(b.teacher_name || 'T').charAt(0)}</div>
              <div class="session-info">
                <h4 style="margin:0 0 4px;font-size:14px">${b.teacher_name} — <em>${b.topic}</em></h4>
                <p style="margin:0;font-size:12px;color:#576b61">Dakika ${b.duration_minutes} · Malipo: ${moneyTZS(b.amount_cents)}</p>
                <div class="session-date" style="margin-top:4px;font-size:11px;color:#85968d">${new Date(b.created_at).toLocaleString('sw-TZ')}</div>
              </div>
            </div>
            <div class="session-right" style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              ${b.status === 'accepted'
                ? `<a class="open-chat-btn" href="/chat.html?booking=${b.id}" style="background:#183a31;color:#f4fbf7;padding:8px 14px;border-radius:4px;font-size:12px;text-decoration:none;font-weight:700;display:inline-flex;align-items:center;gap:5px">💬 Ingia Chumbani (Chat) →</a>`
                : b.status === 'requested'
                  ? `<span class="session-status-tag requested" style="background:#fef3c7;color:#92400e">Inasubiri Mwalimu</span>`
                  : `<a class="small-button" href="/checkout.html?booking=${b.id}" style="padding:6px 10px;font-size:11px">Lipa Sasa →</a>`
              }
            </div>
          </div>
        `
          )
          .join('');
      }

      if (earnings.length) {
        html += `<h4 style="margin:18px 0 8px;font-size:13px">Mazungumzo na Wazungu (ChatPay Live)</h4>`;
        html += earnings
          .map(
            e => `
          <div class="learner-session-card">
            <div class="session-meta">
              <div class="session-avatar">💬</div>
              <div class="session-info">
                <h4>Kuchat na ${e.partner_name}</h4>
                <p>Umetumia dakika ${e.minutes_spent}</p>
                <div class="session-date">${new Date(e.created_at).toLocaleString('sw-TZ')}</div>
              </div>
            </div>
            <div class="session-right">
              <span class="session-status-tag accepted">+${moneyTZS(e.amount_tsh)}</span>
            </div>
          </div>
        `
          )
          .join('');
      }

      if (withdrawals.length) {
        html += `<h4 style="margin:20px 0 8px;font-size:13px">Miamala ya Kutoa Pesa (Withdrawals)</h4>`;
        html += withdrawals
          .map(
            w => `
          <div class="learner-session-card">
            <div class="session-meta">
              <div class="session-avatar" style="background:#e87042">💸</div>
              <div class="session-info">
                <h4>Kutoa Pesa kwenda ${w.provider.toUpperCase()} (${w.phone_number})</h4>
                <p>Kumbukumbu: ${w.reference}</p>
                <div class="session-date">${new Date(w.created_at).toLocaleString('sw-TZ')}</div>
              </div>
            </div>
            <div class="session-right">
              <span class="session-status-tag requested" style="background:#e9f5d4;color:#356f27">IMEKAMILIKA: -${moneyTZS(w.amount_tsh)}</span>
            </div>
          </div>
        `
          )
          .join('');
      }

      sessionsList.innerHTML = html;
    } catch (err) {
      sessionsList.innerHTML = `<p class="sessions-loading">Hitilafu: ${err.message}</p>`;
    }
  });
}

document.querySelectorAll('.close-sessions-modal').forEach(btn => {
  btn.addEventListener('click', () => {
    if (sessionsModal) sessionsModal.classList.remove('show');
  });
});

// ── Profile Modal ───────────────────────────────────────────────────────────
if (menuProfileBtn) {
  menuProfileBtn.addEventListener('click', () => {
    if (userMenuWrap) userMenuWrap.classList.remove('open');
    const { user } = getAuth();
    if (user) {
      if (profileNameInput) profileNameInput.value = user.name || '';
      if (profileEmailInput) profileEmailInput.value = user.email || '';
    }
    if (profileModal) profileModal.classList.add('show');
  });
}

document.querySelectorAll('.close-profile-modal').forEach(btn => {
  btn.addEventListener('click', () => {
    if (profileModal) profileModal.classList.remove('show');
  });
});

if (togglePasswordBtn && passwordFields) {
  togglePasswordBtn.addEventListener('click', () => {
    const isHidden = passwordFields.style.display === 'none';
    passwordFields.style.display = isHidden ? 'grid' : 'none';
  });
}

if (profileForm) {
  profileForm.addEventListener('submit', async e => {
    e.preventDefault();
    if (!profileSaveBtn) return;

    profileSaveBtn.disabled = true;
    profileSaveBtn.textContent = 'Inahifadhi…';
    if (profileMsg) profileMsg.textContent = '';

    const payload = {
      name: profileNameInput.value.trim(),
      email: profileEmailInput.value.trim(),
    };

    if (passwordFields && passwordFields.style.display !== 'none' && profileNewPass.value) {
      payload.current_password = profileCurrPass.value;
      payload.new_password = profileNewPass.value;
    }

    try {
      const data = await api('/api/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });

      localStorage.setItem('talkroom_token', data.access_token);
      localStorage.setItem('talkroom_user', JSON.stringify(data.user));

      updateNavAuth();
      if (profileMsg) {
        profileMsg.textContent = 'Taarifa zako zimehifadhiwa kikamilifu!';
        profileMsg.className = 'profile-msg success';
      }
      showToast('Taarifa zako zimehifadhiwa kikamilifu.');
      setTimeout(() => {
        if (profileModal) profileModal.classList.remove('show');
      }, 1500);
    } catch (err) {
      if (profileMsg) {
        profileMsg.textContent = err.message;
        profileMsg.className = 'profile-msg error';
      }
    } finally {
      profileSaveBtn.disabled = false;
      profileSaveBtn.innerHTML = 'Hifadhi Mabadiliko <span>→</span>';
    }
  });
}

// User Menu Dropdown Toggle
if (userPillBtn && userMenuWrap) {
  userPillBtn.addEventListener('click', e => {
    e.stopPropagation();
    userMenuWrap.classList.toggle('open');
    userPillBtn.setAttribute('aria-expanded', userMenuWrap.classList.contains('open'));
  });

  document.addEventListener('click', e => {
    if (!userMenuWrap.contains(e.target)) {
      userMenuWrap.classList.remove('open');
      userPillBtn.setAttribute('aria-expanded', 'false');
    }
  });
}

// Logout
if (menuLogoutBtn) {
  menuLogoutBtn.addEventListener('click', () => {
    localStorage.removeItem('talkroom_token');
    localStorage.removeItem('talkroom_user');
    updateNavAuth();
    showToast('Umetoka kwenye akaunti yako.');
    location.reload();
  });
}

// Hero open chat trigger
document.querySelectorAll('.open-chat-trigger').forEach(btn => {
  btn.addEventListener('click', () => {
    const partner = btn.dataset.partner || 'Emma Johansson';
    // Find requested partner if unlocked, or first unlocked partner
    const requested = allPartners.find(x => x.name === partner);
    const isReqLocked = requested && (requested.chatted_today || isPartnerChattedToday(requested.name));
    
    let p = requested;
    if (isReqLocked) {
      p = allPartners.find(x => !(x.chatted_today || isPartnerChattedToday(x.name))) || requested;
    }
    if (!p && allPartners.length) p = allPartners[0];

    if (p) {
      const chatUrl = `/chat.html?partner=${encodeURIComponent(p.name)}&topic=${encodeURIComponent(p.topic)}&minutes=${p.minutes}&amount=${p.amount_tsh}&avatar=${encodeURIComponent(p.avatar)}&bio=${encodeURIComponent(p.bio || '')}`;
      location.href = chatUrl;
    }
  });
});

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateNavAuth();
  loadLivePartners();
  loadRecentPayouts();
});
