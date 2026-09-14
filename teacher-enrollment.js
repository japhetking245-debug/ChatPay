'use strict';
const token = localStorage.getItem('talkroom_token');
const user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');
const phone = document.querySelector('#join-phone');
const pay = document.querySelector('#join-pay');
const message = document.querySelector('#join-message');
const form = document.querySelector('#enrollment-form');
const waiting = document.querySelector('#enrollment-waiting');
const status = document.querySelector('#join-status');
const badge = document.querySelector('#join-badge');
const cancel = document.querySelector('#join-cancel');
let payment, timer, attempts = 0;

if (!token || !user || user.role !== 'teacher') location.replace('/auth.html?mode=login');
if (user?.teacher_status === 'active') location.replace('/teacher.html');
phone.value = user?.phone_number || '';

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Hitilafu ya malipo. Jaribu tena.');
  return data;
}
function startPolling() { timer = setInterval(check, 5000); }
async function check() {
  if (!payment || ++attempts > 60) { clearInterval(timer); status.textContent = 'Muda umeisha. Tafadhali jaribu tena.'; return; }
  try {
    const update = await api(`/api/teacher/enrollment/payment/${payment.id}/status`);
    badge.textContent = update.ussd_status || update.status;
    if (update.status === 'paid' || update.teacher_status === 'active') {
      clearInterval(timer); user.teacher_status = 'active'; user.phone_number = phone.value; localStorage.setItem('talkroom_user', JSON.stringify(user));
      status.textContent = 'Malipo yamethibitishwa. Tunakupeleka kwenye dashboard yako...';
      setTimeout(() => location.replace('/teacher-profile.html'), 900);
    } else if (update.status === 'failed' || update.status === 'cancelled') { clearInterval(timer); form.hidden = false; waiting.hidden = true; pay.disabled = false; message.textContent = 'Malipo yameghairiwa au hayakufanikiwa. Jaribu tena.'; }
  } catch { status.textContent = 'Tunaendelea kusubiri uthibitisho wa HarakaPay...'; }
}
pay.addEventListener('click', async () => {
  const number = phone.value.trim();
  if (number.replace(/\D/g, '').length < 9) { message.textContent = 'Weka namba halali ya mobile money.'; phone.focus(); return; }
  pay.disabled = true; message.textContent = '';
  try { payment = await api('/api/teacher/enrollment/payment', { method: 'POST', body: JSON.stringify({ provider: 'harakapay', phone_number: number }) }); form.hidden = true; waiting.hidden = false; badge.textContent = 'Awaiting PIN'; startPolling(); }
  catch (error) { message.textContent = error.message; pay.disabled = false; }
});

cancel.addEventListener('click', async () => {
  if (!payment) return;
  cancel.disabled = true;
  try {
    await api(`/api/teacher/enrollment/payment/${payment.id}/cancel`, { method: 'POST' });
    clearInterval(timer);
    payment = null;
    waiting.hidden = true;
    form.hidden = false;
    pay.disabled = false;
    message.textContent = 'Ombi la malipo limeghairiwa. Usibofye PIN kwenye USSD ya awali ikiwa bado ipo.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    cancel.disabled = false;
  }
});
