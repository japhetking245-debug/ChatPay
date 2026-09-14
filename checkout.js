/* ────────────────────────────────────────────────────────────────────────────
   checkout.js  —  HarakaPay Collection API (USSD-PUSH) checkout flow
   ──────────────────────────────────────────────────────────────────────────── */
'use strict';

const token    = localStorage.getItem('talkroom_token');
const bookingId = new URLSearchParams(location.search).get('booking');

// DOM refs ─────────────────────────────────────────────────────────────────
const $msg         = document.querySelector('#payment-message');
const $payBtn      = document.querySelector('#pay-button');
const $retryBtn    = document.querySelector('#retry-button');
const $cancelBtn   = document.querySelector('#cancel-button');
const $phoneInput  = document.querySelector('#phone-input');
const $phoneDisplay = document.querySelector('#phone-display');
const $waitingStatus = document.querySelector('#waiting-status');
const $paymentStatus = document.querySelector('#payment-status');
const $failedDesc   = document.querySelector('#failed-desc');

// Sections
const $stepForm    = document.querySelector('#step-form');
const $stepWaiting = document.querySelector('#step-waiting');
const $stepSuccess = document.querySelector('#step-success');
const $stepFailed  = document.querySelector('#step-failed');

let booking = null;
let payment = null;
let pollTimer = null;

// ── helpers ────────────────────────────────────────────────────────────────
function money(amount, currency = 'TZS') {
  try {
    return new Intl.NumberFormat('sw-TZ', { style: 'currency', currency }).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString()}`;
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
    let msg = data.detail || 'Request failed. Please try again.';
    if (Array.isArray(msg)) {
      msg = msg.map(e => `${e.loc ? e.loc.filter(x => x !== 'body').join('.') + ': ' : ''}${e.msg || JSON.stringify(e)}`).join('; ');
    } else if (typeof msg === 'object') {
      msg = JSON.stringify(msg);
    }
    throw new Error(msg);
  }
  return data;
}

function show(section) {
  [$stepForm, $stepWaiting, $stepSuccess, $stepFailed].forEach(el => {
    el.style.display = 'none';
  });
  section.style.display = '';
}

// ── load booking details ───────────────────────────────────────────────────
async function loadBooking() {
  if (!token || !bookingId) {
    location.href = '/auth.html';
    return;
  }
  try {
    booking = await api(`/api/bookings/${bookingId}`);
    document.querySelector('#teacher-name').textContent  = booking.teacher_name;
    document.querySelector('#session-price').textContent = money(booking.amount_cents, booking.currency);
    document.querySelector('#total-price').textContent   = money(booking.amount_cents, booking.currency);
  } catch (err) {
    $msg.textContent = err.message;
  }
}

// ── initiate USSD-PUSH ─────────────────────────────────────────────────────
$payBtn.addEventListener('click', async () => {
  if (!booking) return;

  const phone = $phoneInput.value.trim().replace(/\D/g, '');
  if (!phone || phone.length < 9 || phone.length > 13) {
    $msg.textContent = 'Please enter a valid mobile money number (e.g. 0712345678 or 255784123456).';
    $phoneInput.focus();
    return;
  }

  $msg.textContent = '';
  $payBtn.disabled = true;
  $payBtn.innerHTML = 'Sending payment request… <span class="spinner"></span>';

  try {
    payment = await api(`/api/bookings/${booking.id}/payment`, {
      method: 'POST',
      body: JSON.stringify({ provider: 'harakapay', phone_number: phone }),
    });

    // Show waiting screen
    $phoneDisplay.textContent = phone;
    $paymentStatus.textContent = '⏳ Awaiting PIN…';
    show($stepWaiting);
    startPolling();
  } catch (err) {
    $msg.textContent = err.message;
    $payBtn.disabled = false;
    $payBtn.innerHTML = 'Send payment request <span>→</span>';
  }
});

// ── polling ────────────────────────────────────────────────────────────────
let pollCount = 0;
const MAX_POLLS = 60; // ~5 minutes at 5-second intervals

function startPolling() {
  pollCount = 0;
  clearInterval(pollTimer);
  pollTimer = setInterval(checkStatus, 5000);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

async function checkStatus() {
  if (!payment) return;
  pollCount++;

  if (pollCount > MAX_POLLS) {
    stopPolling();
    $waitingStatus.textContent = 'Timed out waiting for payment. Please try again.';
    setTimeout(() => show($stepFailed), 1500);
    return;
  }

  try {
    const updated = await api(`/api/payments/${payment.id}/status`);
    const localStatus = updated.status;          // 'pending' | 'paid' | 'failed'
    const ussdStatus  = updated.ussd_status || ''; // 'PROCESSING' | 'SUCCESS' | 'FAILED' | …

    // Update sidebar badge
    $paymentStatus.textContent = ussdStatus || localStatus;

    if (localStatus === 'paid' || ussdStatus === 'SUCCESS' || ussdStatus === 'SETTLED') {
      stopPolling();
      $paymentStatus.textContent = '✅ Paid!';
      show($stepSuccess);
      return;
    }

    if (localStatus === 'failed' || localStatus === 'cancelled' || ussdStatus === 'FAILED' || ussdStatus === 'CANCELLED') {
      stopPolling();
      $paymentStatus.textContent = '❌ Payment failed';
      $failedDesc.textContent = 'The payment was not completed or was rejected. Please try again.';
      show($stepFailed);
      return;
    }

    // Still processing — update status text
    const elapsed = pollCount * 5;
    $waitingStatus.textContent = `Waiting for you to enter your PIN… (${elapsed}s)`;
  } catch {
    // Network blip — keep polling silently
  }
}

// ── cancel / retry ─────────────────────────────────────────────────────────
$cancelBtn.addEventListener('click', async () => {
  if (!payment) return;
  $cancelBtn.disabled = true;
  try {
    await api(`/api/payments/${payment.id}/cancel`, { method: 'POST' });
  } catch (err) {
    $waitingStatus.textContent = err.message;
    $cancelBtn.disabled = false;
    return;
  }
  stopPolling();
  payment = null;
  $payBtn.disabled = false;
  $payBtn.innerHTML = 'Send payment request <span>→</span>';
  $paymentStatus.textContent = 'Ready to pay';
  $msg.textContent = 'Payment request cancelled. Do not enter your PIN if the earlier USSD prompt is still open.';
  $cancelBtn.disabled = false;
  show($stepForm);
});

$retryBtn.addEventListener('click', () => {
  show($stepForm);
  $payBtn.disabled = false;
  $payBtn.innerHTML = 'Send payment request <span>→</span>';
  $paymentStatus.textContent = 'Ready to pay';
});

// ── init ───────────────────────────────────────────────────────────────────
loadBooking();
