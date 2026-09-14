'use strict';
const token = localStorage.getItem('talkroom_token');
const user = JSON.parse(localStorage.getItem('talkroom_user') || 'null');
const form = document.querySelector('#teacher-profile-form');
const error = document.querySelector('#teacher-profile-error');
const submit = form.querySelector('button[type="submit"]');
if (!token || !user || user.role !== 'teacher') location.replace('/auth.html?mode=login');
if (user?.teacher_status !== 'active') location.replace('/teacher-enrollment.html');
async function api(path, options = {}) { const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) } }); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || 'Hitilafu imetokea.'); return data; }
(async () => { try { const info = await api('/api/teacher/onboarding'); for (const key of ['name', 'city', 'bio', 'payout_phone_number']) form.elements[key].value = info[key] || ''; if (info.completed) location.replace('/teacher.html'); } catch (err) { error.textContent = err.message; } })();
form.addEventListener('submit', async event => { event.preventDefault(); error.textContent = ''; const data = Object.fromEntries(new FormData(form)); submit.disabled = true; submit.textContent = 'Inahifadhi...'; try { const result = await api('/api/teacher/onboarding', { method: 'PUT', body: JSON.stringify(data) }); localStorage.setItem('talkroom_token', result.access_token); localStorage.setItem('talkroom_user', JSON.stringify(result.user)); location.replace('/teacher.html'); } catch (err) { error.textContent = err.message; submit.disabled = false; submit.innerHTML = 'Hifadhi na Endelea <span>→</span>'; } });
