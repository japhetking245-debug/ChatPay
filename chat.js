/* ────────────────────────────────────────────────────────────────────────────
   chat.js — ChatPay Live Conversation Room
   Supports both:
   1. Real Teacher <-> Learner Live Session Chatroom (via ?booking=<id>)
   2. Foreign Partner Chat & Earn Simulation (via ?partner=... or defaults)
   ──────────────────────────────────────────────────────────────────────────── */
'use strict';

const token = localStorage.getItem('talkroom_token');
const user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');

if (!token) {
  // If not logged in, redirect to login
  location.href = `/auth.html?mode=login&redirect=${encodeURIComponent(location.href)}`;
}

const urlParams = new URLSearchParams(location.search);
const bookingId = urlParams.get('booking');

// URL params for foreign partner mode
let partnerName = urlParams.get('partner') || 'Emma Johansson';
let topic = urlParams.get('topic') || 'Safari na kutalii';
const totalMinutes = parseInt(urlParams.get('minutes') || '10', 10);
const targetAmount = parseInt(urlParams.get('amount') || '20000', 10);
let partnerBio = urlParams.get('bio') || 'Mpenzi wa utalii na safari za asili.';
const partnerAvatar = urlParams.get('avatar') || '';

// DOM Refs
const messagesEl = document.querySelector('#messages');
const form = document.querySelector('#message-form');
const input = document.querySelector('#message-input');
const chatNameEl = document.querySelector('#chat-name');
const chatStatusPill = document.querySelector('#chat-status-pill');
const sessionTitleEl = document.querySelector('#session-title');
const sidebarEyebrow = document.querySelector('#sidebar-eyebrow');
const sidebarPartnerName = document.querySelector('#sidebar-partner-name');
const sidebarPartnerBio = document.querySelector('#sidebar-partner-bio');
const sidebarRateInfo = document.querySelector('#sidebar-rate-info');
const sidebarNote = document.querySelector('#sidebar-note');
const timerEl = document.querySelector('#chat-timer');
const earnedDisplay = document.querySelector('#earned-display');
const liveEarningsMeter = document.querySelector('#live-earnings-meter');
const finishBtn = document.querySelector('#finish-chat-btn');
const payoutModal = document.querySelector('#payout-modal');
const payoutModalDesc = document.querySelector('#payout-modal-desc');
const toast = document.querySelector('#toast');
const partnerAvatarBadge = document.querySelector('#partner-avatar-badge');
const chatBackLink = document.querySelector('#chat-back-link');
const chatBackText = document.querySelector('#chat-back-text');
const chatWaiting = document.querySelector('#chat-waiting');

// State
let isBookingMode = Boolean(bookingId);
let currentConversation = null;
let conversationId = null;
let messages = [];
let pollInterval = null;

// Foreign partner mode state
let secondsElapsed = 0;
let totalSeconds = totalMinutes * 60;
let earnedTsh = 0;
let timerInterval = null;
let isCredited = false;

// Conversation turn tracking for the intelligent reply engine
let partnerConversationHistory = []; // [{role: 'bot'|'teacher', text: '...' }]

function showToast(message, duration = 3500) {
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

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
    let msg = data.detail || 'Hitilafu ya ombi';
    if (Array.isArray(msg)) {
      msg = msg.map(e => e.msg || JSON.stringify(e)).join('; ');
    }
    throw new Error(msg);
  }
  return data;
}

function renderMessages() {
  if (!messagesEl) return;
  messagesEl.innerHTML = messages
    .map(
      m => `
    <article class="message ${m.isMine ? 'mine' : ''}">
      <p>${String(m.text || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')}</p>
      <small>${m.isMine ? 'Wewe' : m.sender}</small>
    </article>
  `
    )
    .join('');
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(msg) {
  messages.push(msg);
  renderMessages();
}

// ────────────────────────────────────────────────────────────────────────────
// MODE 1: Real Teacher <-> Learner Session Chatroom
// ────────────────────────────────────────────────────────────────────────────
async function initBookingChat() {
  if (liveEarningsMeter) liveEarningsMeter.style.display = 'none';
  if (finishBtn) finishBtn.style.display = 'none';

  const isTeacher = user && user.role === 'teacher';
  if (chatBackLink) {
    chatBackLink.href = isTeacher ? '/teacher.html' : '/';
  }
  if (chatBackText) {
    chatBackText.textContent = isTeacher ? 'Teacher Dashboard' : 'ChatPay Home';
  }

  if (chatWaiting) {
    chatWaiting.classList.add('active');
    chatWaiting.style.display = 'flex';
    const h2 = chatWaiting.querySelector('h2');
    if (h2) h2.textContent = 'Inapakia chumba cha mazungumzo…';
  }

  try {
    // 1. Get Conversation
    const conv = await api(`/api/bookings/${bookingId}/conversation`);
    currentConversation = conv;
    conversationId = conv.id;

    // Determine partner
    const isLearnerParty = user && (user.name === conv.learner_name || (!isTeacher && user.role === 'learner'));
    partnerName = isLearnerParty ? conv.teacher_name : conv.learner_name;
    const partnerRoleLabel = isLearnerParty ? 'Mwalimu wako' : 'Mwanafunzi wako';

    if (chatNameEl) chatNameEl.textContent = partnerName;
    if (chatStatusPill) {
      chatStatusPill.innerHTML = `<i class="status-dot-live"></i> ${partnerRoleLabel} · Hewani`;
    }
    if (partnerAvatarBadge) {
      partnerAvatarBadge.textContent = partnerName ? partnerName.charAt(0).toUpperCase() : '✦';
    }

    if (sidebarEyebrow) {
      sidebarEyebrow.textContent = isLearnerParty ? 'Mwalimu Wako' : 'Mwanafunzi Wako';
    }
    if (sessionTitleEl) {
      sessionTitleEl.textContent = isLearnerParty ? `Darasa na ${partnerName}` : `Kipindi na ${partnerName}`;
    }
    if (sidebarPartnerName) {
      sidebarPartnerName.textContent = partnerName;
    }
    if (sidebarPartnerBio) {
      sidebarPartnerBio.textContent = isLearnerParty
        ? 'Mwalimu wako wa Kiswahili. Unaweza kuuliza maswali na kufanya mazungumzo kwa uhuru.'
        : 'Mwanafunzi wako wa Kiswahili. Ana shauku ya kujifunza na kufanya mazoezi ya mazungumzo.';
    }
    if (sidebarRateInfo) {
      sidebarRateInfo.textContent = `Kipindi: Dakika 30 · Chumba cha Moja kwa Moja`;
    }
    if (sidebarNote) {
      sidebarNote.textContent = 'Ujumbe unatumwa na kupokelewa moja kwa moja. Majibu yanatokea papo hapo!';
    }
    if (timerEl) {
      timerEl.textContent = '30:00';
    }

    // 2. Load Messages
    await loadConversationMessages();

    if (chatWaiting) {
      chatWaiting.classList.remove('active');
      chatWaiting.style.display = 'none';
    }

    // 3. Start real-time polling every 2.5s for live cross-window chat
    pollInterval = setInterval(loadConversationMessages, 2500);
  } catch (err) {
    if (chatWaiting) {
      chatWaiting.classList.add('active');
      chatWaiting.style.display = 'flex';
      const h2 = chatWaiting.querySelector('h2');
      const p = chatWaiting.querySelector('p');
      if (h2) h2.textContent = 'Chumba Hakijafunguliwa Bado';
      if (p) p.textContent = err.message || 'Mwalimu hajakubali ombi hili bado.';
    }
    showToast(err.message);
  }
}

async function loadConversationMessages() {
  if (!conversationId) return;
  try {
    const rawMessages = await api(`/api/conversations/${conversationId}/messages`);
    const formatted = rawMessages.map(m => ({
      id: m.id,
      sender: m.sender_name,
      isMine: Boolean(user && (m.sender_id === user.id || m.sender_name === user.name)),
      text: m.body,
    }));

    // Only update and scroll if message list has changed
    const currentLastId = messages.length ? messages[messages.length - 1].id : null;
    const newLastId = formatted.length ? formatted[formatted.length - 1].id : null;
    if (formatted.length !== messages.length || currentLastId !== newLastId) {
      messages = formatted;
      renderMessages();
    }
  } catch (err) {
    console.warn('[Message Poll Error]', err);
  }
}

// ────────────────────────────────────────────────────────────────────────────
// MODE 2: Foreign Partner Live Chat & Earn Simulation
// ────────────────────────────────────────────────────────────────────────────
let currentPartnerPromptId = null;
let totalMessages = 0;
const MAX_MESSAGES = 11;

// Additional DOM Refs for message progress and locking
const msgCountDisplay = document.querySelector('#msg-count-display');
const chatMsgCounter = document.querySelector('#chat-msg-counter');
const chatClosedBar = document.querySelector('#chat-closed-bar');
const lockedModal = document.querySelector('#locked-modal');
const lockedModalDesc = document.querySelector('#locked-modal-desc');
const payoutAmountBadge = document.querySelector('#payout-amount-badge');

// ── Daily Locking Utilities ──────────────────────────────────────────────────
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

function markPartnerChattedToday(pName) {
  if (!pName) return;
  try {
    const raw = localStorage.getItem('chatpay_chatted_today');
    let store = raw ? JSON.parse(raw) : {};
    const today = getTodayDateKey();
    if (!store[today]) {
      store = { [today]: [] };
    }
    const clean = pName.trim();
    if (!store[today].some(n => n.toLowerCase() === clean.toLowerCase())) {
      store[today].push(clean);
    }
    localStorage.setItem('chatpay_chatted_today', JSON.stringify(store));
  } catch (e) {
    console.warn('[Store lock error]', e);
  }
}

function showLockedScreen(customMessage) {
  if (form) form.style.display = 'none';
  if (finishBtn) finishBtn.style.display = 'none';
  if (chatClosedBar) chatClosedBar.style.display = 'none';
  if (chatStatusPill) {
    chatStatusPill.innerHTML = `🔒 Mazungumzo Yamefungwa`;
  }
  if (lockedModalDesc) {
    lockedModalDesc.innerHTML = `
      ${customMessage || `Umeshakamilisha mazungumzo na <strong>${partnerName}</strong> kwa siku ya leo na kupokea malipo yako ya siku.`}<br><br>
      Kwa mujibu wa mfumo wa ChatPay, unaweza kuzungumza naye tena <strong>kesho</strong>.<br><br>
      Tafadhali chagua mzungu mwingine aliyepo live sasa hivi kupokea malipo mapya!
    `;
  }
  if (lockedModal) lockedModal.classList.add('show');
}

// ── Realistic Receiving Money Sound (HTML5 Web Audio API) ───────────────────
function playMoneyReceivedSound() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const now = ctx.currentTime;

    // Pleasant 4-note ascending chime: C5, E5, G5, C6 (classic cash payout)
    const notes = [523.25, 659.25, 783.99, 1046.50];
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, now + idx * 0.11);
      gain.gain.setValueAtTime(0, now + idx * 0.11);
      gain.gain.linearRampToValueAtTime(0.3, now + idx * 0.11 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.11 + 0.46);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + idx * 0.11);
      osc.stop(now + idx * 0.11 + 0.5);
    });
  } catch (err) {
    console.log('[Sound play ignored]', err);
  }
}

// ── Message Progress & Counter UI ───────────────────────────────────────────
function updateMessageProgressUI() {
  const current = Math.min(totalMessages, MAX_MESSAGES);
  if (msgCountDisplay) {
    msgCountDisplay.textContent = current;
  }
  if (chatMsgCounter) {
    if (totalMessages >= MAX_MESSAGES) {
      chatMsgCounter.classList.add('completed');
      chatMsgCounter.innerHTML = `<span>✅ Ujumbe:</span> <b>11/11</b> (Kamili)`;
    } else {
      chatMsgCounter.classList.remove('completed');
      chatMsgCounter.innerHTML = `<span>💬 Ujumbe:</span> <b id="msg-count-display">${current}</b>/${MAX_MESSAGES}`;
    }
  }

  // Update earned display progressively up to target amount
  if (!isBookingMode && targetAmount) {
    const progress = Math.min(1, totalMessages / MAX_MESSAGES);
    earnedTsh = Math.round(progress * targetAmount);
    if (earnedDisplay) {
      earnedDisplay.textContent = moneyTZS(earnedTsh);
    }
  }
}

function closeChatroom() {
  if (form) {
    form.style.display = 'none';
  }
  if (chatClosedBar) {
    chatClosedBar.style.display = 'flex';
  }
  if (chatStatusPill) {
    chatStatusPill.innerHTML = `✅ Mazungumzo Yamekamilika`;
  }
  if (finishBtn) {
    finishBtn.disabled = true;
    finishBtn.textContent = '✅ Pesa Imelipwa';
    finishBtn.style.background = '#2da467';
  }
}

async function initPartnerChat() {
  if (chatWaiting) {
    chatWaiting.classList.remove('active');
    chatWaiting.style.display = 'none';
  }
  if (chatNameEl) chatNameEl.textContent = partnerName;
  if (sessionTitleEl) sessionTitleEl.textContent = topic;
  if (sidebarPartnerName) sidebarPartnerName.textContent = partnerName;
  if (sidebarPartnerBio) sidebarPartnerBio.textContent = partnerBio;
  if (sidebarRateInfo) {
    sidebarRateInfo.textContent = `Malipo: ${moneyTZS(targetAmount)} / Ujumbe 11`;
  }
  if (partnerAvatarBadge && partnerName) {
    partnerAvatarBadge.textContent = partnerName.charAt(0);
  }

  // Check if partner is locked today (either in localStorage or on server)
  if (isPartnerChattedToday(partnerName)) {
    showLockedScreen(`Umeshakamilisha mazungumzo na <strong>${partnerName}</strong> leo.`);
    return;
  }

  try {
    const status = await api(`/api/chat/partner-status?partner_name=${encodeURIComponent(partnerName)}`);
    if (status && status.chatted_today) {
      markPartnerChattedToday(partnerName);
      showLockedScreen(status.message);
      return;
    }
  } catch (err) {
    console.warn('[Partner Status Check Error]', err);
  }

  // Load rotational prompt & natural opening message
  try {
    const session = await api(`/api/chat/session-prompt?partner_name=${encodeURIComponent(partnerName)}`);
    if (session && session.chatted_today) {
      markPartnerChattedToday(partnerName);
      showLockedScreen(session.message);
      return;
    }

    if (session && session.intro_message) {
      currentPartnerPromptId = session.prompt_id;
      // Message 1 of 11: Opening prompt from partner
      totalMessages = 1;
      updateMessageProgressUI();
      partnerConversationHistory.push({ role: 'bot', text: session.intro_message });
      addMessage({
        sender: partnerName,
        isMine: false,
        text: session.intro_message,
      });
    } else {
      const defaultIntro = `Jambo mwalimu! Habari yako? Naitwa ${partnerName}. Nimefurahi sana kuunganishwa na wewe leo! Unaendeleaje huko Tanzania?`;
      totalMessages = 1;
      updateMessageProgressUI();
      partnerConversationHistory.push({ role: 'bot', text: defaultIntro });
      addMessage({
        sender: partnerName,
        isMine: false,
        text: defaultIntro,
      });
    }
  } catch (err) {
    console.warn('[Session Prompt Load]', err);
    const defaultIntro = `Jambo mwalimu! Habari yako? Naitwa ${partnerName}. Nimefurahi sana kuunganishwa na wewe leo! Unaendeleaje huko Tanzania?`;
    totalMessages = 1;
    updateMessageProgressUI();
    partnerConversationHistory.push({ role: 'bot', text: defaultIntro });
    addMessage({
      sender: partnerName,
      isMine: false,
      text: defaultIntro,
    });
  }

  startTimer();
}

function startTimer() {
  updateTimerUI();
  timerInterval = setInterval(() => {
    secondsElapsed++;
    const remaining = Math.max(0, totalSeconds - secondsElapsed);
    updateTimerUI(remaining);
  }, 1000);
}

function updateTimerUI(remaining = totalSeconds) {
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  if (timerEl) {
    timerEl.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
}

async function claimEarnings() {
  if (isCredited) return;
  isCredited = true;
  if (timerInterval) clearInterval(timerInterval);

  // Lock this partner until the next day
  markPartnerChattedToday(partnerName);

  const minutesSpent = Math.max(1, Math.ceil(secondsElapsed / 60));
  const amountToCredit = targetAmount || 20000;

  if (finishBtn) {
    finishBtn.disabled = true;
    finishBtn.textContent = 'Inalipwa…';
  }

  try {
    const res = await api('/api/chat/credit', {
      method: 'POST',
      body: JSON.stringify({
        partner_name: partnerName,
        minutes_spent: minutesSpent,
        amount_tsh: amountToCredit,
      }),
    });

    if (payoutAmountBadge) {
      payoutAmountBadge.textContent = moneyTZS(amountToCredit);
    }

    if (payoutModalDesc) {
      payoutModalDesc.innerHTML = `
        Umefanikiwa kupokea <strong>${moneyTZS(amountToCredit)}</strong> kwenye pochi yako ya ChatPay kwa kukamilisha mazungumzo 11 na <strong>${partnerName}</strong>.<br><br>
        Salio lako la sasa ni <strong>${moneyTZS(res.new_balance_tsh || amountToCredit)}</strong>.<br><br>
        <span style="display:inline-block;padding:8px 12px;background:#182824;border-radius:6px;border:1px solid #283c34;color:#f5bd58;font-size:12px">
          🔒 Mazungumzo na <strong>${partnerName}</strong> yatafunguliwa tena <strong>kesho</strong>. Unaweza kuchat na wazungu wengine waliopo live sasa hivi!
        </span>
      `;
    }

    if (payoutModal) payoutModal.classList.add('show');
    showToast(`🎉 Hongera! ${res.message || 'Pesa imeingia kwenye pochi yako!'}`);
  } catch (err) {
    console.warn('[Claim Earnings Error]', err);
    if (payoutAmountBadge) {
      payoutAmountBadge.textContent = moneyTZS(amountToCredit);
    }
    if (payoutModal) payoutModal.classList.add('show');
    showToast(`Taarifa: ${err.message}`);
  }
}

if (finishBtn) {
  finishBtn.addEventListener('click', () => {
    if (totalMessages < MAX_MESSAGES) {
      showToast(`⚠️ Bado ujumbe ${MAX_MESSAGES - totalMessages} ili kukamilisha mazungumzo na kupokea pesa (Ujumbe ${totalMessages}/${MAX_MESSAGES}). Endelea kuchat!`);
      return;
    }
    claimEarnings();
  });
}

// ────────────────────────────────────────────────────────────────────────────
// Message Submission
// ────────────────────────────────────────────────────────────────────────────
if (form) {
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    if (totalMessages >= MAX_MESSAGES) {
      showToast('Mazungumzo yamekamilika kikamilifu (Ujumbe 11/11)!');
      return;
    }

    input.value = '';

    if (isBookingMode && conversationId) {
      // 1. Send to server conversation endpoint
      addMessage({
        sender: user ? user.name : 'Wewe',
        isMine: true,
        text,
      });

      try {
        const sent = await api(`/api/conversations/${conversationId}/messages`, {
          method: 'POST',
          body: JSON.stringify({ body: text }),
        });
        if (messages.length) {
          messages[messages.length - 1].id = sent.id;
        }
      } catch (err) {
        showToast(`Haikutumwa: ${err.message}`);
      }
    } else {
      // 2. Foreign partner bot mode
      totalMessages++;
      updateMessageProgressUI();

      addMessage({
        sender: user ? user.name : 'Wewe',
        isMine: true,
        text,
      });

      // Track teacher's message in history
      partnerConversationHistory.push({ role: 'teacher', text });

      // Disable input while partner is typing
      if (input) input.disabled = true;

      // Typing indicator delay — makes it feel human
      const typingDelay = 900 + Math.floor(Math.random() * 800);

      setTimeout(async () => {
        try {
          const res = await api('/api/chat/bot-reply', {
            method: 'POST',
            body: JSON.stringify({
              partner_name: partnerName,
              user_message: text,
              topic: topic,
              prompt_id: currentPartnerPromptId,
              chat_history: partnerConversationHistory,
            }),
          });
          if (res && res.prompt_id) {
            currentPartnerPromptId = res.prompt_id;
          }
          const reply = res.reply || '';

          // Add partner message (advancing message count)
          totalMessages++;
          updateMessageProgressUI();

          partnerConversationHistory.push({ role: 'bot', text: reply });
          addMessage({
            sender: partnerName,
            isMine: false,
            text: reply,
          });

          // Check if 11th message is reached
          if (totalMessages >= MAX_MESSAGES) {
            closeChatroom();
            playMoneyReceivedSound();
            claimEarnings();
          } else {
            if (input) {
              input.disabled = false;
              input.focus();
            }
          }
        } catch (err) {
          console.warn('[Bot Reply Error]', err);
          if (input) {
            input.disabled = false;
            input.focus();
          }
        }
      }, typingDelay);
    }
  });
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  if (isBookingMode) {
    initBookingChat();
  } else {
    initPartnerChat();
  }
});

