// api.js — shared helper for talking to the backend from every
// admin panel page. Keeping this in one file means we only have to
// get the "attach the login token to every request" logic right once.

const API_BASE = ""; // same origin, since the API serves this panel too

function getToken() {
    return localStorage.getItem("admin_token");
}

function requireLogin() {
    if (!getToken()) {
        window.location.href = "/admin-panel/index.html";
    }
}

async function apiRequest(path, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    const response = await fetch(API_BASE + path, { ...options, headers });

    if (response.status === 401) {
        // Token expired or invalid — send back to login
        localStorage.removeItem("admin_token");
        window.location.href = "/admin-panel/index.html";
        throw new Error("Not authenticated");
    }

    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${response.status})`);
    }

    return response.json();
}

function logout() {
    localStorage.removeItem("admin_token");
    window.location.href = "/admin-panel/index.html";
}
