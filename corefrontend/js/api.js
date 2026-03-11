const _isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const _isRender = window.location.hostname.endsWith('.onrender.com');
const API_BASE = _isLocal
  ? 'http://localhost:8000/api'
  : _isRender
    ? '/api'
    : 'https://backend-cmm-m609.onrender.com/api';


async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = localStorage.getItem('adminAuthToken') || localStorage.getItem('authToken');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();
    return data;
  } catch (err) {
    console.error(`API error [${path}]:`, err);
    return { success: false, message: err.message || 'Network error' };
  }
}

/* ── DEVICES ── */
const deviceApi = {
  async getAll(params = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null) q.append(k, v); });
    return apiFetch(`/devices?${q.toString()}`);
  },
  async getById(id) { return apiFetch(`/devices/${id}`); },
};

/* ── PRICING ── */
const pricingApi = {
  async getAll() { return apiFetch('/pricing'); },
  async getByDevice(deviceId) { return apiFetch(`/pricing/device/${deviceId}`); },
};

/* ── UTILITIES ── */
const utilitiesApi = {
  async getStorageOptions() { return apiFetch('/utilities/storage-options'); },
  async getNetworks() { return apiFetch('/utilities/networks'); },
  async getDeviceConditions() { return apiFetch('/utilities/device-conditions'); },
};

/* ── ORDERS ── */
const orderApi = {
  async create(payload) {
    return apiFetch('/orders', { method: 'POST', body: JSON.stringify(payload) });
  },
};

/* ── CONTACT ── */
const contactApi = {
  async submit(payload) {
    return apiFetch('/contact', { method: 'POST', body: JSON.stringify(payload) });
  },
};

/* ── COUNTER OFFERS ── */
const counterOfferApi = {
  async getByToken(token) { return apiFetch(`/counter-offers/token/${token}`); },
  async accept(token) { return apiFetch(`/counter-offers/token/${token}/accept`, { method: 'POST' }); },
  async reject(token) { return apiFetch(`/counter-offers/token/${token}/reject`, { method: 'POST' }); },
};
