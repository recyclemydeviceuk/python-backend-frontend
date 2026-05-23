// The public website and the FastAPI backend are served from the same origin
// (cashmymobile.co.uk on production, localhost:8000 in dev). Using a relative
// '/api' URL keeps the contact form working everywhere without hard-coding
// the deploy URL — that was the cause of the "Failed to fetch" error customers
// were seeing on the contact page after the Render service URL changed.
const API_BASE = '/api';


async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = localStorage.getItem('adminAuthToken') || localStorage.getItem('authToken');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    const res = await fetch(url, { ...options, headers });
    // Try to parse JSON; some 4xx errors may not include a body
    let data;
    try {
      data = await res.json();
    } catch (parseErr) {
      data = { success: res.ok, message: res.statusText };
    }
    if (!res.ok && data.success === undefined) data.success = false;
    return data;
  } catch (err) {
    console.error(`API error [${path}]:`, err);
    return {
      success: false,
      message: 'Could not reach the server. Please check your internet connection and try again.',
      error: err.message || 'Network error',
    };
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
