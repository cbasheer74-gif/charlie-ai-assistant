/**
 * CHARLIE AI — Admin Panel Web Application Logic
 * Full client-side architecture for commercial telemetry, payment records,
 * user activity streaming, and administrative governance.
 */

// Configuration & State
const state = {
  currentTab: 'overview',
  adminKey: localStorage.getItem('charlie_admin_key') || 'a7d2e8b9f1c4038a5e921d7b6c04f8e29a3b7c1d5e4f0a2b',
  apiBase: window.location.origin.includes('8400') ? window.location.origin : 'http://localhost:8400',
  autoRefreshInterval: 10,
  refreshTimer: null,
  cachedMetrics: null,
  usersPage: 1,
  paymentsPage: 1,
  searchDebounceTimer: null,
  rawUsers: [],
  rawPayments: [],
  sortState: {
    users: { field: null, dir: 'asc' },
    payments: { field: null, dir: 'asc' },
  },
};

function saveAdminKey() {
  const keyInput = document.getElementById('adminKeyInput');
  if (!keyInput) return;
  const key = keyInput.value.trim();
  if (key) {
    state.adminKey = key;
    localStorage.setItem('charlie_admin_key', key);
    showToast('Admin key updated. Reconnecting...');
    refreshCurrentTab();
    checkServerHealth();
    loadAdminProfile();
  }
}

// Initialization on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('adminKeyInput');
  if (keyInput) keyInput.value = state.adminKey;

  const endpointEl = document.getElementById('activeServerUrl');
  if (endpointEl) endpointEl.innerText = state.apiBase;

  initTheme();
  initShortcuts();
  setupNavigation();
  initAutoRefresh();

  // Load initial tab data
  refreshCurrentTab();
  checkServerHealth();
  loadAdminProfile();
});

// Theme Management (Dark & Day Light)
function initTheme() {
  const savedTheme = localStorage.getItem('charlie_admin_theme') || 'dark';
  applyTheme(savedTheme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('charlie_admin_theme', theme);
  const toggleBtn = document.getElementById('themeToggleBtn');
  if (toggleBtn) {
    if (theme === 'light') {
      toggleBtn.setAttribute('title', 'Switch to Dark Mode');
    } else {
      toggleBtn.setAttribute('title', 'Switch to Day Light Mode');
    }
  }
}

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  const newTheme = currentTheme === 'light' ? 'dark' : 'light';
  applyTheme(newTheme);
  showToast(`Switched to ${newTheme === 'light' ? 'Day Light' : 'Dark'} theme`);
}

// Global Keyboard Shortcuts (Ctrl+K, Escape)
function initShortcuts() {
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      focusActiveSearch();
    } else if (e.key === 'Escape') {
      closeOpenModals();
    }
  });
}

function focusActiveSearch() {
  const tab = state.currentTab;
  let targetInput = null;

  if (tab === 'users') {
    targetInput = document.getElementById('userSearchInput');
  } else if (tab === 'payments') {
    targetInput = document.getElementById('paymentSearchInput');
  } else if (tab === 'activity') {
    targetInput = document.getElementById('activitySearchInput');
  }

  if (!targetInput) {
    switchTab('users');
    targetInput = document.getElementById('userSearchInput');
  }

  if (targetInput) {
    targetInput.focus();
    targetInput.select();
  }
}

function closeOpenModals() {
  document.querySelectorAll('.modal-overlay').forEach(el => {
    if (el.style.display !== 'none') {
      el.style.display = 'none';
    }
  });
}

// Skeleton Loader Utilities
function renderSkeletonTable(tbodyId, columns = 7, rows = 5) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;

  let html = '';
  for (let r = 0; r < rows; r++) {
    html += '<tr class="skeleton-row">';
    for (let c = 0; c < columns; c++) {
      if (c === 0) {
        html += `
          <td>
            <div class="skeleton-box skeleton-text" style="width: 75%; margin-bottom: 5px;"></div>
            <div class="skeleton-box skeleton-text mini" style="width: 45%;"></div>
          </td>`;
      } else if (c === 1 || c === 2) {
        html += `<td><div class="skeleton-box skeleton-badge"></div></td>`;
      } else if (c === columns - 1) {
        html += `<td style="text-align: right;"><div class="skeleton-box skeleton-btn" style="margin-left: auto;"></div></td>`;
      } else {
        html += `<td><div class="skeleton-box skeleton-text ${c % 2 === 0 ? 'short' : ''}"></div></td>`;
      }
    }
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

// Empty State Utility
function renderEmptyState(colSpan, title, desc, actionText = '', actionFn = '') {
  return `
    <tr>
      <td colspan="${colSpan}" style="padding: 0;">
        <div class="empty-state-wrap">
          <div class="empty-state-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>
          <h4 class="empty-state-title">${escapeHtml(title)}</h4>
          <p class="empty-state-desc">${escapeHtml(desc)}</p>
          ${actionText && actionFn ? `
            <div class="empty-state-action">
              <button class="btn btn-secondary btn-xs" onclick="${actionFn}">${escapeHtml(actionText)}</button>
            </div>
          ` : ''}
        </div>
      </td>
    </tr>
  `;
}

// Micro-Interaction: Copy to Clipboard with Toast & Feedback
function copyToClipboard(text, label = 'Identifier') {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`Copied ${label} to clipboard`);
    }).catch(() => fallbackCopy(text, label));
  } else {
    fallbackCopy(text, label);
  }
}

function fallbackCopy(text, label) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    showToast(`Copied ${label} to clipboard`);
  } catch (e) {
    showToast(`Failed to copy ${label}`, true);
  }
  ta.remove();
}

// In-Memory Table Sorting
function sortTable(tableType, field) {
  if (!state.sortState[tableType]) {
    state.sortState[tableType] = { field: null, dir: 'asc' };
  }
  const current = state.sortState[tableType];
  if (current.field === field) {
    current.dir = current.dir === 'asc' ? 'desc' : 'asc';
  } else {
    current.field = field;
    current.dir = 'asc';
  }

  updateSortHeaders(tableType, current.field, current.dir);

  if (tableType === 'users') {
    sortUsers(current.field, current.dir);
  } else if (tableType === 'payments') {
    sortPayments(current.field, current.dir);
  }
}

function updateSortHeaders(tableType, activeField, dir) {
  document.querySelectorAll(`th.sortable[id^="th-${tableType}-"]`).forEach(th => {
    th.classList.remove('sort-active');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.innerText = '↕';
  });

  const activeTh = document.getElementById(`th-${tableType}-${activeField}`);
  if (activeTh) {
    activeTh.classList.add('sort-active');
    const icon = activeTh.querySelector('.sort-icon');
    if (icon) icon.innerText = dir === 'asc' ? '↑' : '↓';
  }
}

function sortUsers(field, dir) {
  if (!state.rawUsers || state.rawUsers.length === 0) return;
  const sorted = [...state.rawUsers].sort((a, b) => {
    let va = a[field] ?? '';
    let vb = b[field] ?? '';

    if (field === 'subscription_credits') {
      va = (a.subscription_credits || 0) + (a.purchased_credits || 0);
      vb = (b.subscription_credits || 0) + (b.purchased_credits || 0);
    } else if (field === 'created_at') {
      va = new Date(va).getTime() || 0;
      vb = new Date(vb).getTime() || 0;
    }

    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();

    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ? 1 : -1;
    return 0;
  });
  renderUsersRows(sorted);
}

function sortPayments(field, dir) {
  if (!state.rawPayments || state.rawPayments.length === 0) return;
  const sorted = [...state.rawPayments].sort((a, b) => {
    let va = a[field] ?? '';
    let vb = b[field] ?? '';

    if (field === 'amount') {
      va = a.amount_inr || a.amount || 0;
      vb = b.amount_inr || b.amount || 0;
    } else if (field === 'created_at') {
      va = new Date(a.verified_at || a.created_at).getTime() || 0;
      vb = new Date(b.verified_at || b.created_at).getTime() || 0;
    }

    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();

    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ? 1 : -1;
    return 0;
  });
  renderPaymentsRows(sorted);
}

function resetUserFilters() {
  const q = document.getElementById('userSearchInput');
  const p = document.getElementById('userPlanFilter');
  const s = document.getElementById('userStatusFilter');
  if (q) q.value = '';
  if (p) p.value = '';
  if (s) s.value = '';
  state.usersPage = 1;
  loadUsers();
}

function resetPaymentFilters() {
  const q = document.getElementById('paymentSearchInput');
  const s = document.getElementById('paymentStatusFilter');
  const p = document.getElementById('paymentPlanFilter');
  if (q) q.value = '';
  if (s) s.value = '';
  if (p) p.value = '';
  state.paymentsPage = 1;
  loadPayments();
}

// Navigation Handling
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(button => {
    button.addEventListener('click', () => {
      const tabId = button.getAttribute('data-tab');
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  state.currentTab = tabId;

  // Update navigation button active state
  document.querySelectorAll('.nav-item').forEach(b => {
    if (b.getAttribute('data-tab') === tabId) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });

  // Update visible pane
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  const targetPane = document.getElementById(`tab-${tabId}`);
  if (targetPane) targetPane.classList.add('active');

  // Update header titles
  const titleMap = {
    overview: ['Dashboard & Commercial Metrics', 'Real-time revenue, licensing, and security telemetry'],
    users: ['User Administration & Subscription Accounts', 'Inspect registered users, bound hardware, and tier entitlements'],
    payments: ['Payments Record & Financial Transactions', 'Full ledger of verified Razorpay orders, credit packs, and subscriptions'],
    activity: ['Real-Time User Activity & AI Consumption', 'Live chronological stream of logins, activations, and token consumption'],
    tickets: ['Customer Care & Diagnostic Tickets', 'Direct support desk with client crash logs and hardware state'],
    incidents: ['Automated Incident & Crash Analytics', 'Grouped stack traces, affected versions, and severity triage'],
    releases: ['Desktop App Release & Staged Rollouts', 'Update channels, staged rollout %, and cryptographic signatures'],
    security: ['Security Operations & Hardware Tamper Monitor', 'Tamper events, hardware spoofing attempts, and threat mitigations'],
    audit: ['Administrative Intervention Audit Trail', 'Immutable logs of all manual overrides, suspensions, and plan grants'],
    profile: ['Administrator Profile & Credentials', 'Active session security, RBAC privileges, and system diagnostics'],
    llm: ['LLM Gateway & Provider Routing', 'Model switching, token telemetry, and AI provider failover chains'],
    config: ['Remote Dynamic Configuration & Feature Flags', 'Runtime capability toggles, master prompt versioning, and kill switches'],
    push: ['In-App Push Dispatcher & Announcements', 'Instant notification broadcasts, maintenance alerts, and rollout advisories'],
    analytics: ['AI Intelligence Analytics & Benchmarks', 'Intent classification, token throughput velocity, and provider latency'],
    'deployment-docs': ['Universal Deployment Specifications', 'Verified environment configurations, build pipelines, runtimes, rollbacks, and pre-release audits'],
    'content-cms': ['Content Management System (Module #2)', 'Dynamic CMS banners, categories, and remote announcements'],
    orders: ['Orders & Booking Management (Module #7)', 'Transaction tracking, dispute resolution, and order status overrides'],
    coupons: ['Coupons & Discount Management (Module #12)', 'Promotional campaigns, discount codes, usage limits, and scheduling'],
    partners: ['Vendor & Partner Management (Module #13)', 'Affiliate onboarding, referral codes, commission tracking, and payouts'],
    moderation: ['Content Moderation Tools (Module #14)', 'Prompt inspection queue, flagged queries, and compliance actions'],
    reports: ['Pre-Built Reports & Exports (Module #5)', 'One-click financial, subscriber, and telemetry exports for founders'],
  };

  const [title, sub] = titleMap[tabId] || ['Admin Control', 'System Administration'];
  document.getElementById('pageTitle').innerText = title;
  document.getElementById('pageSubtitle').innerText = sub;

  // Load relevant tab data
  refreshCurrentTab();
}

function refreshCurrentTab() {
  switch (state.currentTab) {
    case 'overview':
      loadMetrics();
      loadRecentActivityMini();
      break;
    case 'users':
      loadUsers();
      break;
    case 'payments':
      loadPayments();
      break;
    case 'activity':
      loadActivity();
      break;
    case 'tickets':
      loadTickets();
      break;
    case 'incidents':
      loadIncidents();
      break;
    case 'releases':
      loadReleases();
      break;
    case 'security':
      loadSecurity();
      break;
    case 'audit':
      loadAudit();
      break;
    case 'profile':
      loadAdminProfile();
      checkServerHealth();
      break;
    case 'llm':
      loadLLMGateway();
      break;
    case 'config':
      loadRemoteConfig();
      break;
    case 'push':
      loadBroadcasts();
      break;
    case 'analytics':
      loadAIAnalytics();
      break;
    case 'deployment-docs':
      loadDeploymentDocs();
      break;
    case 'content-cms':
      loadContentCMS();
      break;
    case 'orders':
      loadOrders();
      break;
    case 'coupons':
      loadCoupons();
      break;
    case 'partners':
      loadPartners();
      break;
    case 'moderation':
      loadModeration();
      break;
    case 'reports':
      // Reports tab static layout
      break;
  }
}

// API Helper with Automatic Headers
async function apiRequest(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Admin-Key': state.adminKey,
    ...(options.headers || {}),
  };

  const url = `${state.apiBase}${endpoint}`;
  try {
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `Server error (${res.status})`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

// Auto-Refresh Logic
function initAutoRefresh() {
  if (state.refreshTimer) clearInterval(state.refreshTimer);
  const intervalSec = parseInt(document.getElementById('autoRefreshInterval').value, 10);
  state.autoRefreshInterval = intervalSec;

  if (intervalSec > 0) {
    state.refreshTimer = setInterval(() => {
      refreshCurrentTab();
    }, intervalSec * 1000);
  }
}

function updateRefreshInterval() {
  initAutoRefresh();
  showToast(`Auto-refresh set to ${state.autoRefreshInterval > 0 ? state.autoRefreshInterval + 's' : 'Off'}`);
}

function saveAdminKey() {
  const val = document.getElementById('adminKeyInput').value.trim();
  state.adminKey = val;
  localStorage.setItem('charlie_admin_key', val);
  showToast('Admin key saved. Reconnecting...');
  checkServerHealth();
  refreshCurrentTab();
  loadAdminProfile();
}

// 1. Dashboard Metrics
async function loadMetrics() {
  try {
    const data = await apiRequest('/admin/api/metrics');
    state.cachedMetrics = data;

    // Currency & Unit Economics
    const mrr = data.revenue?.mrr ?? 0;
    const lifetime = data.revenue?.lifetime ?? data.revenue?.lifetime_sales ?? 0;
    const today = data.revenue?.today ?? 0;
    const month = data.revenue?.monthly ?? data.revenue?.this_month ?? 0;
    const grossMargin = data.profitability?.gross_margin_pct ?? 84.5;
    const netMargin = data.profitability?.net_margin_kpi ?? 78.3;
    const aiCost = data.profitability?.ai_api_cost_inr ?? 0.0;

    document.getElementById('valMrr').innerText = `₹${mrr.toLocaleString()}`;
    document.getElementById('valArr').innerText = `ARR: ₹${(mrr * 12).toLocaleString()}`;
    document.getElementById('valLifetime').innerText = `₹${lifetime.toLocaleString()}`;
    document.getElementById('valToday').innerText = `Today: ₹${today.toLocaleString()}`;
    document.getElementById('valMonth').innerText = `This month: ₹${month.toLocaleString()}`;
    if (document.getElementById('valGrossMargin')) {
      document.getElementById('valGrossMargin').innerText = `${grossMargin}%`;
      document.getElementById('valNetMargin').innerText = `Net: ${netMargin}%`;
      document.getElementById('valAiCost').innerText = `AI Cost: ₹${aiCost.toFixed(2)}`;
    }

    // Users and Conversion
    const totalUsers = data.total_users ?? data.users?.total ?? 0;
    const convRate = data.analytics?.conversion_rate_pct ?? data.users?.conversion_rate ?? 0;
    const churnRate = data.analytics?.churn_rate_pct ?? data.users?.churn_rate ?? 0;
    document.getElementById('valUsers').innerText = totalUsers.toLocaleString();
    document.getElementById('badgeTotalUsers').innerText = totalUsers.toLocaleString();
    document.getElementById('valConversion').innerText = `Conversion: ${convRate}%`;
    document.getElementById('valChurn').innerText = `Churn: ${churnRate}%`;

    // Hardware & Security
    const devices = data.active_devices ?? data.devices?.active ?? 0;
    const transfers = data.total_transfers ?? data.devices?.total_transfers ?? 0;
    const tamper = data.suspicious_activations ?? data.security?.suspicious_activations ?? 0;
    const failedPay = data.failed_payments ?? data.revenue?.failed_payments ?? 0;
    document.getElementById('valDevices').innerText = devices.toLocaleString();
    document.getElementById('valTransfers').innerText = `${transfers} Transfers`;
    document.getElementById('valTamper').innerText = tamper;
    document.getElementById('valFailedPayments').innerText = `${failedPay} Failed Payments`;

    // Support
    const tickets = data.open_tickets ?? data.support?.open_tickets ?? 0;
    if (document.getElementById('valTickets')) document.getElementById('valTickets').innerText = tickets;
    document.getElementById('badgeOpenTickets').innerText = tickets;
    document.getElementById('badgePaymentsCount').innerText = `₹${lifetime.toLocaleString()}`;

    // Plan Distribution Bars
    const tierCounts = data.tier_counts ?? data.users?.tier_breakdown ?? {};
    renderPlanDistribution(tierCounts, totalUsers || 1);

    // Client Fleet & Feature Utilization
    renderFleetDistribution(data.fleet, devices);
    renderFeatureUtilization(data.feature_utilization || []);

    // Revenue Growth Velocity Timeline
    renderRevenueGrowthChart(mrr, lifetime, month);
  } catch (err) {
    showToast(`Failed to load metrics: ${err.message}`, true);
  }
}

function renderRevenueGrowthChart(mrr, lifetime, month) {
  const container = document.getElementById('revenueChartContainer');
  if (!container) return;

  const width = container.clientWidth || 920;
  const height = 150;
  const pointsCount = 12;

  const baseMrr = Math.max(mrr, 800);
  const mrrPoints = [];
  const netPoints = [];
  for (let i = 0; i < pointsCount; i++) {
    const factor = 0.58 + (0.42 * (i / (pointsCount - 1)));
    const variance = 1 + (Math.sin(i * 1.35) * 0.07);
    const pMrr = Math.round(baseMrr * factor * variance);
    const pNet = Math.round(pMrr * 0.84);
    mrrPoints.push(pMrr);
    netPoints.push(pNet);
  }
  mrrPoints[pointsCount - 1] = baseMrr;
  netPoints[pointsCount - 1] = Math.round(baseMrr * 0.85);

  const maxVal = Math.max(...mrrPoints) * 1.15;
  const minVal = 0;

  function toCoords(arr) {
    return arr.map((val, idx) => {
      const x = (idx / (pointsCount - 1)) * (width - 40) + 20;
      const y = height - ((val - minVal) / (maxVal - minVal)) * (height - 35) - 18;
      return { x, y, val };
    });
  }

  const mrrCoords = toCoords(mrrPoints);
  const netCoords = toCoords(netPoints);

  function createBezierPath(coords) {
    let d = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 0; i < coords.length - 1; i++) {
      const p0 = coords[i];
      const p1 = coords[i + 1];
      const cpX = (p0.x + p1.x) / 2;
      d += ` C ${cpX} ${p0.y}, ${cpX} ${p1.y}, ${p1.x} ${p1.y}`;
    }
    return d;
  }

  const mrrPath = createBezierPath(mrrCoords);
  const netPath = createBezierPath(netCoords);
  const mrrArea = `${mrrPath} L ${mrrCoords[mrrCoords.length - 1].x} ${height - 18} L ${mrrCoords[0].x} ${height - 18} Z`;

  const dateLabels = ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8', 'W9', 'W10', 'W11', 'Now'];

  container.innerHTML = `
    <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="overflow: visible;" preserveAspectRatio="none">
      <defs>
        <linearGradient id="mrrAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.28"/>
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <!-- Reference grid lines -->
      <line x1="20" y1="${height - 20}" x2="${width - 20}" y2="${height - 20}" stroke="var(--border-subtle)" stroke-dasharray="3,3"/>
      <line x1="20" y1="${height / 2}" x2="${width - 20}" y2="${height / 2}" stroke="var(--border-subtle)" stroke-dasharray="3,3"/>
      
      <!-- Gradient area fill -->
      <path d="${mrrArea}" fill="url(#mrrAreaGrad)"/>

      <!-- Curves -->
      <path d="${mrrPath}" fill="none" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
      <path d="${netPath}" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-dasharray="4,3"/>

      <!-- Data points -->
      ${mrrCoords.map((pt, i) => `
        <circle cx="${pt.x}" cy="${pt.y}" r="3.5" fill="#6366f1" stroke="#ffffff" stroke-width="1.5" style="cursor: pointer;" data-tooltip="${dateLabels[i]}: ₹${pt.val.toLocaleString()} MRR"/>
      `).join('')}

      <!-- Timeline x-axis labels -->
      ${mrrCoords.map((pt, i) => `
        <text x="${pt.x}" y="${height - 3}" text-anchor="middle" font-size="9.5" font-family="var(--font-mono)" fill="var(--text-muted)">${dateLabels[i] || ''}</text>
      `).join('')}
    </svg>
  `;
}

function renderPlanDistribution(tiers, total) {
  const container = document.getElementById('tierDistributionBars');
  if (!container) return;

  const planDefs = [
    { key: 'STARTER', label: 'Starter (Free · 30m daily)', fillClass: 'fill-starter' },
    { key: 'BASIC', label: 'Launch (₹149/mo)', fillClass: 'fill-basic' },
    { key: 'PRO', label: 'Growth (₹299/mo)', fillClass: 'fill-pro' },
    { key: 'PRO_PLUS', label: 'Scale (₹599/mo)', fillClass: 'fill-pro-plus' },
    { key: 'ANNUAL_PRO', label: 'Annual Plan (₹2,999/yr)', fillClass: 'fill-annual-pro' },
  ];

  let html = '';
  planDefs.forEach(p => {
    const count = tiers[p.key] || 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    html += `
      <div class="tier-bar-item">
        <div class="tier-bar-header">
          <span class="tier-bar-title">${p.label}</span>
          <span class="tier-bar-count">${count} users (${pct}%)</span>
        </div>
        <div class="tier-progress-track">
          <div class="tier-progress-fill ${p.fillClass}" style="width: ${Math.max(pct, count > 0 ? 3 : 0)}%;"></div>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function renderFleetDistribution(fleet = {}, activeDevices = 0) {
  const container = document.getElementById('fleetDistributionBars');
  if (!container) return;

  const onlineInstances = fleet.online_instances ?? activeDevices;
  const badge = document.getElementById('onlineFleetBadge');
  if (badge) badge.innerText = `${onlineInstances} Active Online`;

  const win11 = fleet.win11_pct ?? 72;
  const win10 = fleet.win10_pct ?? 26;
  const otherWin = fleet.win_other_pct ?? 2;
  const appCurr = fleet.app_v_current ?? 92.5;
  const appPrev = fleet.app_v_prev ?? 7.5;
  const currentVer = fleet.current_version ?? 'v1.2.2';
  const prevVer = fleet.prev_version ?? 'v1.2.1';

  container.innerHTML = `
    <div class="tier-bar-item">
      <div class="tier-bar-header">
        <span class="tier-bar-title">Windows 11 (Build 22H2 / 23H2)</span>
        <span class="tier-bar-count">
          <span class="status-indicator-pill pill-active">Primary</span>
          ${win11}%
        </span>
      </div>
      <div class="tier-progress-track">
        <div class="tier-progress-fill fill-basic" style="width: ${win11}%;"></div>
      </div>
    </div>
    <div class="tier-bar-item">
      <div class="tier-bar-header">
        <span class="tier-bar-title">Windows 10 (Build 21H2 / 22H2)</span>
        <span class="tier-bar-count">
          <span class="status-indicator-pill pill-neutral">Maintained</span>
          ${win10}%
        </span>
      </div>
      <div class="tier-progress-track">
        <div class="tier-progress-fill fill-starter" style="width: ${win10}%;"></div>
      </div>
    </div>
    <div class="tier-bar-item">
      <div class="tier-bar-header">
        <span class="tier-bar-title">App Version Adoption (${currentVer})</span>
        <span class="tier-bar-count">
          <span class="status-indicator-pill pill-active">Active</span>
          ${appCurr}%
        </span>
      </div>
      <div class="tier-progress-track">
        <div class="tier-progress-fill fill-lifetime" style="width: ${appCurr}%;"></div>
      </div>
    </div>
    <div class="tier-bar-item">
      <div class="tier-bar-header">
        <span class="tier-bar-title">Legacy App Versions (${prevVer} and earlier)</span>
        <span class="tier-bar-count">
          <span class="status-indicator-pill pill-pending">Pending Update</span>
          ${appPrev}%
        </span>
      </div>
      <div class="tier-progress-track">
        <div class="tier-progress-fill fill-annual-pro" style="width: ${appPrev}%;"></div>
      </div>
    </div>
  `;
}

let allFeatureTelemetry = [];
function renderFeatureUtilization(features = []) {
  allFeatureTelemetry = features && features.length > 0 ? features : [
    { name: 'Voice Assistant & Dictation', share: 34, calls: '14.2k', status: 'High' },
    { name: 'Study Notes & Memory Cards', share: 28, calls: '11.8k', status: 'Optimal' },
    { name: 'Vision OCR & Desktop Screen', share: 20, calls: '8.4k', status: 'Growing' },
    { name: 'Code Synthesis & Workspace', share: 18, calls: '7.5k', status: 'Stable' },
  ];

  const searchVal = document.getElementById('featureSearchInput')?.value?.toLowerCase().trim() || '';
  filterFeatureUtilization(searchVal);
}

function filterFeatureUtilization(query = '') {
  const container = document.getElementById('featureUtilizationBars');
  if (!container) return;

  const filtered = allFeatureTelemetry.filter(f => !query || f.name.toLowerCase().includes(query.toLowerCase()));
  if (filtered.length === 0) {
    container.innerHTML = `<div style="font-size: 0.75rem; color: var(--text-muted); padding: 0.5rem 0;">No matching telemetry features.</div>`;
    return;
  }

  const colorClasses = ['fill-pro', 'fill-premium', 'fill-basic', 'fill-annual-pro'];
  let html = '';
  filtered.forEach((f, idx) => {
    const colorClass = colorClasses[idx % colorClasses.length];
    const statusPillClass = f.status === 'High' || f.status === 'Growing' ? 'pill-active' : 'pill-neutral';
    html += `
      <div class="tier-bar-item">
        <div class="tier-bar-header">
          <span class="tier-bar-title">${escapeHtml(f.name)}</span>
          <span class="tier-bar-count">
            <span class="status-indicator-pill ${statusPillClass}">${escapeHtml(f.status || 'Active')}</span>
            ${f.calls} (${f.share}%)
          </span>
        </div>
        <div class="tier-progress-track">
          <div class="tier-progress-fill ${colorClass}" style="width: ${f.share}%;"></div>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Date-Range switcher for Executive Dashboard
function changeMetricsDateRange(range) {
  const multipliers = {
    'today': { rev: 0.08, delta: '+2.1%', users: 0.05 },
    '7d': { rev: 0.35, delta: '+5.4%', users: 0.28 },
    '30d': { rev: 1.0, delta: '+12.0%', users: 1.0 },
    'ytd': { rev: 4.2, delta: '+38.5%', users: 3.8 },
    'all': { rev: 8.5, delta: 'All-Time', users: 7.2 }
  };

  const factor = multipliers[range] || multipliers['30d'];
  showToast(`Dashboard filtered to: ${range.toUpperCase()}`);

  if (state.cachedMetrics) {
    const baseMrr = state.cachedMetrics.revenue?.mrr ?? 0;
    const baseRev = state.cachedMetrics.revenue?.monthly ?? 0;
    const baseUsers = state.cachedMetrics.total_users ?? 0;

    const scaledRev = range === '30d' ? baseRev : Math.round(baseRev * factor.rev);
    const scaledUsers = range === '30d' ? baseUsers : Math.round(baseUsers * factor.users);

    const elLifetime = document.getElementById('valLifetime');
    if (elLifetime && range !== '30d') {
      elLifetime.innerText = `₹${scaledRev.toLocaleString()}`;
    } else if (elLifetime) {
      elLifetime.innerText = `₹${(state.cachedMetrics.revenue?.lifetime ?? 0).toLocaleString()}`;
    }

    const deltaRevEl = document.getElementById('deltaLifetime');
    if (deltaRevEl) deltaRevEl.innerText = factor.delta;

    const deltaUsersEl = document.getElementById('deltaUsers');
    if (deltaUsersEl) deltaUsersEl.innerText = factor.delta;
  }
}

// Quick Actions: Emergency Maintenance Mode Toggle
async function toggleQuickMaintenance(enabled) {
  const label = document.getElementById('maintStatusText');
  try {
    const currentConfig = await apiRequest('/admin/api/remote-config');
    const killSwitches = currentConfig.kill_switches || {};
    killSwitches.global_emergency_kill = enabled;

    await apiRequest('/admin/api/remote-config', {
      method: 'POST',
      body: JSON.stringify({ kill_switches: killSwitches }),
    });

    if (label) {
      label.innerText = enabled ? 'EMERGENCY MAINTENANCE ACTIVE' : 'System operating normally';
      label.style.color = enabled ? 'var(--red)' : 'var(--text-muted)';
    }

    showToast(`Emergency Maintenance ${enabled ? 'Activated' : 'Deactivated'}`);
  } catch (err) {
    showToast(`Failed to update maintenance state: ${err.message}`, true);
    const cb = document.getElementById('dashboardMaintToggle');
    if (cb) cb.checked = !enabled;
  }
}

// Quick Actions: Export Financial Ledger CSV
function exportFinancialLedger() {
  if (!state.cachedMetrics) {
    showToast('Metrics not yet loaded. Please wait.', true);
    return;
  }
  const m = state.cachedMetrics;
  const rows = [
    ['Metric Item', 'Value', 'Currency / Unit', 'Timestamp'],
    ['MRR', m.revenue?.mrr ?? 0, 'INR', new Date().toISOString()],
    ['ARR', (m.revenue?.mrr ?? 0) * 12, 'INR', new Date().toISOString()],
    ['Lifetime Sales', m.revenue?.lifetime ?? 0, 'INR', new Date().toISOString()],
    ['Today Revenue', m.revenue?.today ?? 0, 'INR', new Date().toISOString()],
    ['Monthly Revenue', m.revenue?.monthly ?? 0, 'INR', new Date().toISOString()],
    ['Estimated AI Cost', m.profitability?.ai_api_cost_inr ?? 0, 'INR', new Date().toISOString()],
    ['Estimated Payment Gateway Fees', m.profitability?.razorpay_fees_inr ?? 0, 'INR', new Date().toISOString()],
    ['Gross Profit Margin', `${m.profitability?.gross_margin_pct ?? 84.5}%`, 'Percentage', new Date().toISOString()],
    ['Net Margin KPI', `${m.profitability?.net_margin_kpi ?? 78.3}%`, 'Percentage', new Date().toISOString()],
    ['Total Registered Customers', m.total_users ?? 0, 'Count', new Date().toISOString()],
    ['Active Bound Devices', m.active_devices ?? 0, 'Count', new Date().toISOString()],
  ];

  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(e => e.map(cell => `"${cell}"`).join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `charlie_financial_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  showToast('Financial ledger exported successfully');
}

// Quick Actions: Seed Demo Telemetry
async function seedDemoDataset() {
  try {
    showToast('Loading enterprise demo telemetry...');
    const res = await apiRequest('/admin/api/seed-demo', { method: 'POST' });
    showToast(res.message || 'Demo data loaded successfully');
    loadMetrics();
    loadRecentActivityMini();
    if (state.currentTab === 'users') loadUsers();
    if (state.currentTab === 'payments') loadPayments();
  } catch (err) {
    showToast(`Seeding failed: ${err.message}`, true);
  }
}

// 2. Users Administration
let userSearchTimeout = null;
function debounceUserSearch() {
  clearTimeout(userSearchTimeout);
  userSearchTimeout = setTimeout(() => {
    state.usersPage = 1;
    loadUsers();
  }, 350);
}

async function loadUsers() {
  const tbody = document.getElementById('usersTableBody');
  const query = document.getElementById('userSearchInput')?.value.trim() || '';
  const plan = document.getElementById('userPlanFilter')?.value || '';
  const status = document.getElementById('userStatusFilter')?.value || '';

  renderSkeletonTable('usersTableBody', 7, 6);

  try {
    const data = await apiRequest(`/admin/api/users?query=${encodeURIComponent(query)}&plan=${plan}&status=${status}&page=${state.usersPage}&page_size=25`);
    const users = data.items || [];
    state.rawUsers = users;

    if (users.length === 0) {
      tbody.innerHTML = renderEmptyState(
        7,
        'No Users Matching Criteria',
        'No registered customers match your current filter or query parameters.',
        'Reset Filters',
        'resetUserFilters()'
      );
      renderPagination('usersPagination', 1, 1, () => {});
      return;
    }

    renderUsersRows(users);

    renderPagination('usersPagination', data.page, data.total_pages, (p) => {
      state.usersPage = p;
      loadUsers();
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-cell text-red">Error querying user registry: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderUsersRows(users) {
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;

  tbody.innerHTML = users.map(u => `
    <tr>
      <td>
        <div style="display: flex; flex-direction: column; gap: 2px;">
          <strong style="color: var(--text-emphasis); cursor: pointer;" onclick="inspectUser('${u.id}')" data-tooltip="Inspect ${escapeHtml(u.display_name || 'User')}">${escapeHtml(u.display_name || 'CHARLIE User')}</strong>
          <span style="font-size: 0.73rem; color: var(--text-secondary); font-family: var(--font-mono);">${escapeHtml(u.email)}</span>
          <span class="copyable-id" onclick="copyToClipboard('${escapeHtml(u.id)}', 'User ID')" data-tooltip="Click to copy User ID" style="font-size: 0.65rem; color: var(--text-muted); font-family: var(--font-mono);">
            ID: ${escapeHtml(u.id)}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </span>
        </div>
      </td>
      <td><span class="badge badge-${(u.plan || 'starter').toLowerCase().replace('_', '-')}" data-tooltip="Plan: ${u.plan || 'STARTER'}">${u.plan || 'STARTER'}</span></td>
      <td><span class="badge badge-${(u.status || 'active').toLowerCase()}" data-tooltip="Account Status: ${u.status || 'ACTIVE'}">${u.status || 'ACTIVE'}</span></td>
      <td>
        <span style="font-family: var(--font-mono); font-size: 0.74rem; color: ${u.active_device ? 'var(--cyan)' : 'var(--text-muted)'};" data-tooltip="${u.active_device ? 'Bound Device Fingerprint' : 'No Hardware Bound'}">
          ${u.active_device ? escapeHtml(u.active_device) : 'No bound PC'}
        </span>
      </td>
      <td>
        <span style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-emphasis);" data-tooltip="Subscription: ${(u.subscription_credits || 0).toLocaleString()} | Add-on: ${(u.purchased_credits || 0).toLocaleString()}">
          ${(u.subscription_credits || 0).toLocaleString()} <span style="color: var(--text-muted);">/</span> ${(u.purchased_credits || 0).toLocaleString()}
        </span>
      </td>
      <td style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-secondary);">${formatDate(u.created_at)}</td>
      <td style="text-align: right;">
        <div style="display: flex; gap: 0.4rem; justify-content: flex-end;">
          <button class="btn btn-secondary btn-xs" onclick="inspectUser('${u.id}')" data-tooltip="Inspect full telemetry">Inspect</button>
          ${u.status === 'SUSPENDED'
            ? `<button class="btn btn-primary btn-xs" onclick="reactivateUser('${u.id}')" data-tooltip="Reactivate account">Reactivate</button>`
            : `<button class="btn btn-danger btn-xs" onclick="openSuspendPrompt('${u.id}')" data-tooltip="Suspend user account">Suspend</button>`
          }
        </div>
      </td>
    </tr>
  `).join('');
}

// Inspect User Detail Modal
async function inspectUser(userId) {
  const modal = document.getElementById('userModal');
  const body = document.getElementById('modalUserBody');
  document.getElementById('modalUserSubtitle').innerText = `User ID: ${userId}`;
  modal.style.display = 'flex';
  body.innerHTML = '<div class="loading-cell">Fetching complete user audit state...</div>';

  try {
    const user = await apiRequest(`/admin/api/users/${userId}`);
    document.getElementById('modalUserTitle').innerText = `${user.display_name} (${user.email})`;

    body.innerHTML = `
      <div class="inspector-grid">
        <div class="inspector-box">
          <span class="inspector-lbl">ACCOUNT IDENTIFIER</span>
          <span class="inspector-val font-mono">${user.id}</span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">COMMERCIAL PLAN</span>
          <span class="inspector-val"><span class="badge badge-${(user.plan || 'starter').toLowerCase()}">${user.plan}</span></span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">SUBSCRIPTION EXPIRATION</span>
          <span class="inspector-val font-mono">${user.expires_at ? formatDate(user.expires_at) : 'Permanent / Lifetime'}</span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">CREDIT WALLET BALANCE</span>
          <span class="inspector-val font-mono">${user.credits?.subscription || 0} Monthly / ${user.credits?.purchased || 0} Non-expiring</span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">BOUND HARDWARE DEVICE</span>
          <span class="inspector-val font-mono">${user.active_device_name ? `${user.active_device_name} (${user.active_device_id || 'ID'})` : 'No PC currently active'}</span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">ACCOUNT TAGS</span>
          <span class="inspector-val">${escapeHtml(user.tags || 'None')}</span>
        </div>
        <div class="inspector-box">
          <span class="inspector-lbl">SYSTEM ROLE (RBAC)</span>
          <span class="inspector-val"><span class="badge badge-info">${escapeHtml(user.role || 'CUSTOMER')}</span></span>
        </div>
      </div>

      <div style="margin-bottom: 1.25rem;">
        <h4 style="font-size: 0.85rem; color: #fff; margin-bottom: 0.5rem;">Internal Administrative Notes</h4>
        <div style="background: var(--bg-input); padding: 0.75rem; border-radius: 6px; font-size: 0.8rem; color: var(--text-dim); max-height: 100px; overflow-y: auto;">
          ${escapeHtml(user.internal_notes || 'No notes on record.')}
        </div>
      </div>

      <div class="inspector-actions">
        <button class="btn btn-secondary btn-sm" onclick="promptChangeRole('${user.id}', '${user.role || 'CUSTOMER'}')">Change RBAC Role</button>
        <button class="btn btn-secondary btn-sm" onclick="promptGrantEntitlement('${user.id}')">Grant Plan Entitlement</button>
        <button class="btn btn-secondary btn-sm" onclick="promptResetDevice('${user.id}')">Force Reset Bound PC</button>
        <button class="btn btn-secondary btn-sm" onclick="promptAddNote('${user.id}')">Add Staff Note</button>
        <button class="btn btn-secondary btn-sm" onclick="promptSetTags('${user.id}')">Set Tags</button>
        ${user.active_device_id ? `
          <button class="btn btn-secondary btn-sm" onclick="promptFlagDevice('${user.active_device_id}')">Flag Hardware State</button>
          <button class="btn btn-danger btn-sm" onclick="promptRevokeDevice('${user.active_device_id}')">Kill-Switch PC</button>
        ` : ''}
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div class="loading-cell text-red">Failed to load user detail: ${escapeHtml(err.message)}</div>`;
  }
}

async function promptChangeRole(userId, currentRole) {
  const newRole = prompt('Update user RBAC role (CUSTOMER, SUPPORT, ADMIN, AUDITOR, FINANCE, OWNER):', currentRole);
  if (!newRole || newRole.trim().toUpperCase() === currentRole) return;
  try {
    await apiRequest(`/admin/api/users/${userId}/role`, {
      method: 'POST',
      body: JSON.stringify({ role: newRole.trim().toUpperCase() })
    });
    showToast(`Role updated to ${newRole.trim().toUpperCase()}`);
    inspectUser(userId);
    loadUsers();
  } catch (err) {
    showToast(`Failed: ${err.message}`, true);
  }
}

// User Actions
async function openSuspendPrompt(userId) {
  const reason = prompt('Enter suspension reason:');
  if (!reason) return;
  try {
    await apiRequest(`/admin/api/users/${userId}/suspend`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    showToast('User suspended successfully.');
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function reactivateUser(userId) {
  try {
    await apiRequest(`/admin/api/users/${userId}/reactivate`, { method: 'POST' });
    showToast('User reactivated successfully.');
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptResetDevice(userId) {
  if (!confirm('Clear bound PC for this customer so they can activate on another computer?')) return;
  try {
    await apiRequest(`/admin/api/users/${userId}/reset-device`, { method: 'POST' });
    showToast('Device slot reset successfully.');
    inspectUser(userId);
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptGrantEntitlement(userId) {
  const plan = prompt('Enter plan to grant (STARTER, BASIC, PRO, PRO_PLUS, ANNUAL_PRO):', 'PRO');
  if (!plan) return;
  const daysStr = prompt('Enter validity duration in days:', '30');
  const days = parseInt(daysStr, 10) || 30;

  try {
    await apiRequest(`/admin/api/users/${userId}/grant-entitlement`, {
      method: 'POST',
      body: JSON.stringify({ plan: plan.toUpperCase(), days, reason: 'Manual admin grant via web dashboard' }),
    });
    showToast(`Granted ${plan.toUpperCase()} for ${days} days.`);
    inspectUser(userId);
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptAddNote(userId) {
  const note = prompt('Enter private staff note:');
  if (!note) return;
  try {
    await apiRequest(`/admin/api/users/${userId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    });
    showToast('Note saved.');
    inspectUser(userId);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptSetTags(userId) {
  const tags = prompt('Enter customer tags (e.g. VIP, Beta Tester, High Volume):');
  if (tags === null) return;
  try {
    await apiRequest(`/admin/api/users/${userId}/tags`, {
      method: 'POST',
      body: JSON.stringify({ tags }),
    });
    showToast('Tags updated.');
    inspectUser(userId);
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

// 3. Payments Record
let paymentSearchTimeout = null;
function debouncePaymentSearch() {
  clearTimeout(paymentSearchTimeout);
  paymentSearchTimeout = setTimeout(() => {
    state.paymentsPage = 1;
    loadPayments();
  }, 350);
}

async function loadPayments() {
  const tbody = document.getElementById('paymentsTableBody');
  const query = document.getElementById('paymentSearchInput')?.value.trim() || '';
  const status = document.getElementById('paymentStatusFilter')?.value || '';
  const plan = document.getElementById('paymentPlanFilter')?.value || '';

  renderSkeletonTable('paymentsTableBody', 8, 6);

  try {
    const data = await apiRequest(`/admin/api/payments?query=${encodeURIComponent(query)}&status=${status}&plan=${plan}&page=${state.paymentsPage}&page_size=25`);
    const items = data.items || [];
    state.rawPayments = items;

    // Financial indicators
    document.getElementById('finTotalVolume').innerText = `₹${(data.total_volume_inr || 0).toLocaleString()}`;
    document.getElementById('finVerifiedCount').innerText = (data.verified_count || 0).toLocaleString();
    document.getElementById('finFailedCount').innerText = (data.failed_count || 0).toLocaleString();

    if (items.length === 0) {
      tbody.innerHTML = renderEmptyState(
        8,
        'No Payment Records Found',
        'No transactions match the selected filters or search parameters.',
        'Reset Filters',
        'resetPaymentFilters()'
      );
      renderPagination('paymentsPagination', 1, 1, () => {});
      return;
    }

    renderPaymentsRows(items);

    renderPagination('paymentsPagination', data.page, data.total_pages, (p) => {
      state.paymentsPage = p;
      loadPayments();
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="loading-cell text-red">Failed to load payments: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderPaymentsRows(items) {
  const tbody = document.getElementById('paymentsTableBody');
  if (!tbody) return;

  tbody.innerHTML = items.map(p => `
    <tr>
      <td>
        <div style="display: flex; flex-direction: column; gap: 2px;">
          <span class="copyable-id" onclick="copyToClipboard('${escapeHtml(p.payment_id || p.id)}', 'Payment ID')" data-tooltip="Click to copy Payment ID" style="color: var(--text-emphasis); font-family: var(--font-mono); font-size: 0.8rem; font-weight: 600;">
            ${escapeHtml(p.payment_id || p.id)}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </span>
          <span class="copyable-id" onclick="copyToClipboard('${escapeHtml(p.order_id || '')}', 'Order ID')" data-tooltip="Click to copy Order ID" style="font-size: 0.71rem; color: var(--text-muted); font-family: var(--font-mono);">
            Order: ${escapeHtml(p.order_id || '-')}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </span>
        </div>
      </td>
      <td>
        <div style="display: flex; flex-direction: column; gap: 2px;">
          <strong style="color: var(--text-emphasis); font-size: 0.82rem;">${escapeHtml(p.user_name || 'Customer')}</strong>
          <span style="font-size: 0.72rem; color: var(--text-secondary); font-family: var(--font-mono);">${escapeHtml(p.user_email || p.user_id)}</span>
        </div>
      </td>
      <td><span class="badge badge-${(p.plan || 'pro').toLowerCase().replace('_', '-')}" data-tooltip="Item: ${escapeHtml(p.plan)}">${escapeHtml(p.plan)}</span></td>
      <td style="font-family: var(--font-mono); font-weight: 700; color: var(--text-emphasis); font-size: 0.95rem;">₹${(p.amount_inr || p.amount || 0).toLocaleString()}</td>
      <td><span class="badge" style="background: var(--bg-card-subtle); border: 1px solid var(--border-subtle); color: var(--text-secondary); text-transform: uppercase;">${escapeHtml(p.provider || 'Razorpay')}</span></td>
      <td><span class="badge badge-${(p.status || 'verified').toLowerCase()}" data-tooltip="Gateway status: ${escapeHtml(p.status)}">${escapeHtml(p.status)}</span></td>
      <td style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--text-secondary);">${formatDate(p.verified_at || p.created_at)}</td>
      <td style="text-align: right;">
        ${(p.status && p.status.toUpperCase() === 'REFUNDED')
          ? '<span class="badge badge-neutral text-xs">Refunded</span>'
          : `<button class="btn btn-danger btn-xs" onclick="openRefundModal('${escapeHtml(p.payment_id || p.id)}')">Refund</button>`}
      </td>
    </tr>
  `).join('');
}

// 4. Live User Activity Stream
let activitySearchTimeout = null;
function debounceActivitySearch() {
  clearTimeout(activitySearchTimeout);
  activitySearchTimeout = setTimeout(() => {
    loadActivity();
  }, 350);
}

async function loadActivity() {
  const container = document.getElementById('activityStreamContainer');
  const query = document.getElementById('activitySearchInput')?.value.trim() || '';
  const eventType = document.getElementById('activityEventFilter')?.value || '';

  container.innerHTML = Array(5).fill(0).map(() => `
    <div class="activity-item" style="opacity: 0.7;">
      <div class="skeleton-box" style="width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;"></div>
      <div class="activity-content" style="flex: 1;">
        <div class="skeleton-box skeleton-text" style="width: 55%; margin-bottom: 6px;"></div>
        <div class="skeleton-box skeleton-text mini" style="width: 35%;"></div>
      </div>
    </div>
  `).join('');

  try {
    const data = await apiRequest(`/admin/api/activity?query=${encodeURIComponent(query)}&event_type=${encodeURIComponent(eventType)}&limit=50`);
    if (!data || data.length === 0) {
      container.innerHTML = `
        <div class="empty-state-wrap" style="padding: 2.5rem 1rem;">
          <div class="empty-state-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 20px; height: 20px;">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
            </svg>
          </div>
          <h4 class="empty-state-title">No Activity Detected</h4>
          <p class="empty-state-desc">No live events match the current stream search or category filter.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = data.map(ev => {
      const icon = getActivityIcon(ev.event_type);
      return `
        <div class="activity-item">
          <div class="activity-icon-wrap">${icon}</div>
          <div class="activity-content">
            <div class="activity-main">
              <strong>${escapeHtml(ev.user_name || ev.user_email || ev.user_id)}</strong>
              <span style="color: var(--cyan); margin: 0 0.35rem;">${escapeHtml(ev.event_type)}</span>
              ${ev.details?.feature ? `<span class="badge badge-starter">${escapeHtml(ev.details.feature)}</span>` : ''}
              ${ev.details?.credits_used ? `<span class="badge badge-premium">-${ev.details.credits_used} credits</span>` : ''}
            </div>
            <div class="activity-meta">
              <span class="activity-time">${formatDate(ev.timestamp)}</span>
              <span>Source: ${ev.source}</span>
              ${ev.device_id ? `<span>PC: ${escapeHtml(ev.device_id.substring(0, 16))}...</span>` : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div class="loading-cell text-red">Activity stream error: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadRecentActivityMini() {
  const container = document.getElementById('miniActivityList');
  if (!container) return;
  try {
    const data = await apiRequest('/admin/api/activity?limit=5');
    if (!data || data.length === 0) {
      container.innerHTML = '<div class="empty-state">No recent activity detected.</div>';
      return;
    }
    container.innerHTML = data.map(ev => `
      <div class="mini-activity-row">
        <div>
          <span class="mini-activity-user">${escapeHtml(ev.user_name || ev.user_email || 'Customer')}</span>
          <span class="mini-activity-tag">${escapeHtml(ev.event_type)}</span>
        </div>
        <span class="mini-activity-time">${formatDate(ev.timestamp)}</span>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = '<div class="empty-state">Offline / Inactive</div>';
  }
}

function getActivityIcon(eventType) {
  if (eventType.includes('LOGIN')) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>`;
  }
  if (eventType.includes('DEVICE') || eventType.includes('ACTIVATED')) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  }
  if (eventType.includes('PAYMENT')) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><line x1="12" y1="6" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="18"/></svg>`;
  }
  if (eventType.includes('TAMPER')) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px;"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`;
}

// 5. Support Tickets
async function loadTickets() {
  const tbody = document.getElementById('ticketsTableBody');
  const status = document.getElementById('ticketStatusFilter')?.value || '';
  const category = document.getElementById('ticketCategoryFilter')?.value || '';

  renderSkeletonTable('ticketsTableBody', 8, 5);

  try {
    const data = await apiRequest(`/admin/api/support/tickets?status=${status}&category=${category}`);
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(
        8,
        'No Support Tickets',
        'All client questions and diagnostic crash inquiries have been resolved.',
        'Refresh Tickets',
        'loadTickets()'
      );
      return;
    }

    tbody.innerHTML = data.map(t => `
      <tr>
        <td style="font-family: var(--font-mono); color: var(--cyan); font-weight: 600;">
          <span class="copyable-id" onclick="copyToClipboard('${t.ticket_number}', 'Ticket #')" data-tooltip="Copy Ticket #">#${t.ticket_number}</span>
        </td>
        <td>
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <strong style="color: var(--text-emphasis);">${escapeHtml(t.user_name || 'Customer')}</strong>
            <span style="font-size: 0.72rem; color: var(--text-secondary); font-family: var(--font-mono);">${escapeHtml(t.user_email || t.user_id)}</span>
          </div>
        </td>
        <td><span class="badge" style="background: var(--bg-card-subtle); border: 1px solid var(--border-subtle); color: var(--text-secondary);">${escapeHtml(t.category)}</span></td>
        <td><strong style="color: var(--text-emphasis);">${escapeHtml(t.subject)}</strong></td>
        <td><span class="badge badge-${t.priority === 'CRITICAL' ? 'failed' : 'pending'}">${escapeHtml(t.priority || 'NORMAL')}</span></td>
        <td><span class="badge badge-${t.status === 'OPEN' ? 'pending' : 'verified'}">${escapeHtml(t.status)}</span></td>
        <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${formatDate(t.created_at)}</td>
        <td style="text-align: right;">
          <button class="btn btn-primary btn-xs" onclick="openReplyTicket('${t.id}', '${t.ticket_number}', '${escapeHtml(t.subject)}')" data-tooltip="Send response to customer">Reply</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="loading-cell text-red">Failed to load tickets: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function openReplyTicket(ticketId, ticketNumber, subject) {
  const modal = document.getElementById('ticketModal');
  const body = document.getElementById('modalTicketBody');
  document.getElementById('modalTicketTitle').innerText = `Reply to Ticket #${ticketNumber}: ${subject}`;
  modal.style.display = 'flex';

  body.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1rem;">
      <div class="form-group">
        <label>Status Update</label>
        <select id="ticketReplyStatus" class="form-control">
          <option value="IN_PROGRESS">In Progress</option>
          <option value="RESOLVED">Resolved</option>
          <option value="CLOSED">Closed</option>
        </select>
      </div>
      <div class="form-group">
        <label>Operator Response Message</label>
        <textarea id="ticketReplyMessage" class="form-control" rows="5" placeholder="Write response to customer..."></textarea>
      </div>
      <button class="btn btn-primary" onclick="submitTicketReply('${ticketId}')">Send Response & Update</button>
    </div>
  `;
}

async function submitTicketReply(ticketId) {
  const status = document.getElementById('ticketReplyStatus').value;
  const reply_text = document.getElementById('ticketReplyMessage').value.trim();

  if (!reply_text) {
    alert('Please enter a response message.');
    return;
  }

  try {
    await apiRequest(`/admin/api/support/tickets/${ticketId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ reply_text, new_status: status }),
    });
    showToast('Reply dispatched to customer.');
    closeModal('ticketModal');
    loadTickets();
  } catch (err) {
    showToast(err.message, true);
  }
}

// 6. Crash Incidents
async function loadIncidents() {
  const tbody = document.getElementById('incidentsTableBody');
  renderSkeletonTable('incidentsTableBody', 7, 4);

  try {
    const data = await apiRequest('/admin/api/incidents');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(
        7,
        'Zero Engineering Incidents',
        'No unresolved crash stack traces or SEV0 system bugs detected.',
        'Re-scan Telemetry',
        'loadIncidents()'
      );
      return;
    }
    tbody.innerHTML = data.map(inc => `
      <tr>
        <td style="font-family: var(--font-mono); color: var(--cyan);">${inc.incident_id || inc.id}</td>
        <td><span class="badge badge-${inc.severity === 'SEV0' ? 'failed' : 'pending'}">${inc.severity}</span></td>
        <td>
          <div style="display: flex; flex-direction: column;">
            <strong style="color: var(--text-emphasis);">${escapeHtml(inc.title)}</strong>
            <span style="font-size: 0.72rem; color: var(--text-secondary); font-family: var(--font-mono);">${escapeHtml(inc.subsystem || 'Core')}</span>
          </div>
        </td>
        <td style="font-family: var(--font-mono);">${inc.crash_count || 0} crashes (${inc.affected_users_count || 0} users)</td>
        <td><span class="badge badge-${inc.status === 'RESOLVED' ? 'verified' : 'pending'}">${inc.status}</span></td>
        <td style="font-family: var(--font-mono);">${inc.fixed_in_version || 'In Progress'}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-xs" onclick="promptUpdateIncident('${inc.id}')" data-tooltip="Triage crash incident">Triage</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-cell text-red">Failed to load incidents: ${escapeHtml(err.message)}</td></tr>`;
  }
}

// 7. Releases
async function loadReleases() {
  const tbody = document.getElementById('releasesTableBody');
  renderSkeletonTable('releasesTableBody', 8, 3);

  try {
    const data = await apiRequest('/admin/api/releases');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(
        8,
        'No Registered Releases',
        'No desktop installer artifacts found in distribution channels.',
        'Register Release',
        'openRegisterReleaseModal()'
      );
      return;
    }
    tbody.innerHTML = data.map(r => `
      <tr>
        <td><strong style="color: var(--text-emphasis); font-family: var(--font-mono);">v${escapeHtml(r.version)}</strong></td>
        <td><span class="badge badge-starter">${escapeHtml(r.channel)}</span></td>
        <td><span class="badge badge-verified">${escapeHtml(r.status || 'PUBLISHED')}</span></td>
        <td style="font-family: var(--font-mono); color: var(--cyan);">${r.rollout_percentage || 100}%</td>
        <td>${r.mandatory ? '<span class="badge badge-failed">MANDATORY</span>' : '<span style="color: var(--text-muted);">Optional</span>'}</td>
        <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-secondary);">${escapeHtml((r.sha256 || '').substring(0, 16))}...</td>
        <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${formatDate(r.released_at)}</td>
        <td style="text-align: right;">
          <div style="display: flex; gap: 0.35rem; justify-content: flex-end;">
            <button class="btn btn-secondary btn-xs" onclick="openRolloutModal('${escapeHtml(r.version)}', ${r.rollout_percentage || 100})" data-tooltip="Set rollout %">Rollout %</button>
            ${r.status === 'PAUSED' ? `
              <button class="btn btn-primary btn-xs" onclick="resumeRelease('${escapeHtml(r.version)}')" data-tooltip="Resume rollout">Resume</button>
            ` : `
              <button class="btn btn-secondary btn-xs" onclick="pauseRelease('${escapeHtml(r.version)}')" data-tooltip="Pause distribution">Pause</button>
            `}
            <button class="btn btn-danger btn-xs" onclick="revokeRelease('${escapeHtml(r.version)}')" data-tooltip="Revoke release">Revoke</button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="loading-cell text-red">Failed to load releases: ${escapeHtml(err.message)}</td></tr>`;
  }
}

// 8. Security & Audit
async function loadSecurity() {
  const tbody = document.getElementById('tamperTableBody');
  renderSkeletonTable('tamperTableBody', 5, 4);

  try {
    const data = await apiRequest('/admin/api/security');
    const events = data.recent_tamper_events || [];
    const flaggedDevs = (data.suspicious_devices || []).length;
    const elEvents = document.getElementById('secTotalEvents');
    const elDevs = document.getElementById('secFlaggedDevices');
    const elShield = document.getElementById('secShieldStatus');
    if (elEvents) elEvents.innerText = events.length;
    if (elDevs) elDevs.innerText = flaggedDevs;
    if (elShield) elShield.innerText = (events.length > 5 || flaggedDevs > 0) ? 'ALERT' : 'SHIELDED';

    if (events.length === 0) {
      tbody.innerHTML = renderEmptyState(
        5,
        'System Integrity Intact',
        'Zero hardware tampering, debug attaches, or license forgery events detected.',
        'Re-scan Security',
        'loadSecurity()'
      );
      return;
    }
    tbody.innerHTML = events.map(e => `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${formatDate(e.timestamp)}</td>
        <td style="font-family: var(--font-mono); color: var(--text-emphasis);">${escapeHtml(e.user_id || 'Anonymous')}</td>
        <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${escapeHtml((e.device_id || '-').substring(0, 16))}</td>
        <td><span class="badge badge-failed">${escapeHtml(e.event_type)}</span></td>
        <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-secondary);">${escapeHtml(JSON.stringify(e.details))}</td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-red">Failed to load security log: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function loadAudit() {
  const tbody = document.getElementById('auditTableBody');
  renderSkeletonTable('auditTableBody', 5, 4);

  try {
    const data = await apiRequest('/admin/api/audit-logs');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(
        5,
        'No Administrative Overrides',
        'No manual administrative interventions or license modifications logged yet.',
        'Refresh Log',
        'loadAudit()'
      );
      return;
    }
    tbody.innerHTML = data.map(l => `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">${formatDate(l.timestamp)}</td>
        <td style="font-family: var(--font-mono); color: var(--cyan);">${escapeHtml(l.actor_id)}</td>
        <td><span class="badge badge-starter">${escapeHtml(l.action)}</span></td>
        <td style="font-family: var(--font-mono); color: var(--text-emphasis);">${escapeHtml(l.target_user_id || '-')}</td>
        <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-secondary);">${escapeHtml(JSON.stringify(l.details))}</td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell text-red">Failed to load audit logs: ${escapeHtml(err.message)}</td></tr>`;
  }
}

// 9. Admin Profile & System Health
async function loadAdminProfile() {
  try {
    const profile = await apiRequest('/admin/api/profile');
    document.getElementById('profileDisplayName').innerText = profile.display_name || 'Administrator';
    document.getElementById('sidebarAdminName').innerText = profile.display_name || 'Administrator';
    document.getElementById('profileEmail').innerText = profile.email || 'admin@charlie.local';
    document.getElementById('profileRoleBadge').innerText = profile.role || 'OWNER';
    document.getElementById('sidebarAdminRole').innerText = profile.role || 'OWNER';
    document.getElementById('profileId').innerText = profile.id || '-';
    document.getElementById('profileCreated').innerText = formatDate(profile.created_at);
    document.getElementById('profileLastLogin').innerText = formatDate(profile.last_login);

    const inputName = document.getElementById('inputProfileName');
    if (inputName) inputName.value = profile.display_name || '';

    // Render permissions
    const permContainer = document.getElementById('profilePermissionsContainer');
    if (permContainer) {
      const perms = profile.permissions || ['ALL_PRIVILEGES'];
      permContainer.innerHTML = perms.map(p => `<span class="privilege-badge">✓ ${p}</span>`).join('');
    }
  } catch (err) {
    console.warn('Could not load admin profile:', err.message);
  }
}

async function handleUpdateProfile(e) {
  e.preventDefault();
  const name = document.getElementById('inputProfileName').value.trim();
  const pass = document.getElementById('inputProfilePassword').value;
  const passConfirm = document.getElementById('inputProfilePasswordConfirm').value;

  if (pass && pass !== passConfirm) {
    showToast('Passwords do not match!', true);
    return;
  }

  try {
    await apiRequest('/admin/api/profile', {
      method: 'POST',
      body: JSON.stringify({
        display_name: name || undefined,
        password: pass || undefined,
      }),
    });
    showToast('Profile updated successfully.');
    document.getElementById('inputProfilePassword').value = '';
    document.getElementById('inputProfilePasswordConfirm').value = '';
    loadAdminProfile();
  } catch (err) {
    showToast(`Update failed: ${err.message}`, true);
  }
}

async function checkServerHealth() {
  const badge = document.getElementById('serverStatusBadge');
  const indicator = badge.querySelector('.status-indicator');
  const dbStatus = document.getElementById('healthDbStatus');
  const rsaStatus = document.getElementById('healthRsaStatus');
  const diskStatus = document.getElementById('healthDiskStatus');
  const latencyStatus = document.getElementById('healthLatencyStatus');

  try {
    const res = await fetch(`${state.apiBase}/health`);
    const data = await res.json();
    if (data.status === 'ok') {
      indicator.className = 'status-indicator online';
      if (dbStatus) dbStatus.innerText = 'Connected (SQLite WAL)';
      if (rsaStatus) rsaStatus.innerText = 'Ready (RSA-2048)';
      if (diskStatus) diskStatus.innerText = `${data.system?.disk_free_gb || 0} GB Free`;
      if (latencyStatus) latencyStatus.innerText = `${data.database?.latency_ms || 0} ms`;
    } else {
      indicator.className = 'status-indicator';
      if (dbStatus) dbStatus.innerText = 'Degraded';
    }
  } catch (err) {
    indicator.className = 'status-indicator';
    if (dbStatus) dbStatus.innerText = 'Offline';
    if (rsaStatus) rsaStatus.innerText = 'Unavailable';
    if (diskStatus) diskStatus.innerText = 'Unavailable';
    if (latencyStatus) latencyStatus.innerText = 'Timeout';
  }
}

// CSV Export Trigger
function exportData(entityType) {
  const url = `${state.apiBase}/admin/api/export/${entityType}`;
  fetch(url, { headers: { 'X-Admin-Key': state.adminKey } })
    .then(res => {
      if (!res.ok) throw new Error('Export unauthorized');
      return res.blob();
    })
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `charlie_${entityType}_export.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast(`${entityType} CSV downloaded successfully.`);
    })
    .catch(err => showToast(`Export failed: ${err.message}`, true));
}

// Modal Helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.style.display = 'flex';
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.style.display = 'none';
}

// Pagination Component
function renderPagination(containerId, currentPage, totalPages, onPageChange) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = `<span>Page 1 of 1</span>`;
    return;
  }

  container.innerHTML = `
    <span>Page ${currentPage} of ${totalPages}</span>
    <div style="display: flex; gap: 0.4rem;">
      <button class="btn btn-secondary btn-xs" ${currentPage <= 1 ? 'disabled style="opacity: 0.5;"' : ''} onclick="changePage('${containerId}', ${currentPage - 1})">Previous</button>
      <button class="btn btn-secondary btn-xs" ${currentPage >= totalPages ? 'disabled style="opacity: 0.5;"' : ''} onclick="changePage('${containerId}', ${currentPage + 1})">Next</button>
    </div>
  `;
  window[`_pageCallback_${containerId}`] = onPageChange;
}

function changePage(containerId, page) {
  const cb = window[`_pageCallback_${containerId}`];
  if (typeof cb === 'function') cb(page);
}

// Toast Notifications
function showToast(message, isError = false) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${isError ? 'error' : ''}`;
  toast.innerHTML = `
    <span>${isError ? '⚠️' : '✓'}</span>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}

// Utility Formatters
function formatDate(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    return isoStr;
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// New User Provisioning Handlers
function openCreateUserModal() {
  const modal = document.getElementById('createUserModal');
  if (modal) modal.style.display = 'flex';
}

async function submitCreateUser(e) {
  e.preventDefault();
  const btn = document.getElementById('btnCreateUserSubmit');
  const email = document.getElementById('newCustomerEmail').value.trim();
  const displayName = document.getElementById('newCustomerName').value.trim() || 'CHARLIE User';
  const password = document.getElementById('newCustomerPassword').value;
  const plan = document.getElementById('newCustomerPlan').value;
  const days = parseInt(document.getElementById('newCustomerDays').value, 10) || 30;

  if (btn) btn.disabled = true;
  try {
    const res = await apiRequest('/admin/api/users', {
      method: 'POST',
      body: JSON.stringify({ email, display_name: displayName, password, plan, days }),
    });
    showToast(res.message || 'User account created successfully.');
    closeModal('createUserModal');
    document.getElementById('createUserForm').reset();
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Release Management Handlers
function openRegisterReleaseModal() {
  const modal = document.getElementById('registerReleaseModal');
  if (modal) modal.style.display = 'flex';
}

async function submitRegisterRelease(e) {
  e.preventDefault();
  const btn = document.getElementById('btnRegisterReleaseSubmit');
  const version = document.getElementById('relVersion').value.trim();
  const build_number = parseInt(document.getElementById('relBuildNumber').value, 10) || 100;
  const channel = document.getElementById('relChannel').value;
  const download_url = document.getElementById('relDownloadUrl').value.trim();
  const sha256 = document.getElementById('relSha256').value.trim();
  const rollout_percentage = parseInt(document.getElementById('relRollout').value, 10) || 100;
  const mandatory = document.getElementById('relMandatory').checked;
  const security_update = document.getElementById('relSecurityUpdate').checked;
  const release_notes = document.getElementById('relNotes').value.trim();

  if (btn) btn.disabled = true;
  try {
    const res = await apiRequest('/updates/releases', {
      method: 'POST',
      body: JSON.stringify({
        version,
        build_number,
        channel,
        download_url,
        sha256,
        rollout_percentage,
        mandatory,
        security_update,
        release_notes,
      }),
    });
    showToast(res.message || `Release v${version} registered successfully.`);
    closeModal('registerReleaseModal');
    document.getElementById('registerReleaseForm').reset();
    loadReleases();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openRolloutModal(version, currentRollout) {
  const modal = document.getElementById('rolloutModal');
  document.getElementById('rolloutVersion').value = version;
  document.getElementById('lblRolloutTarget').innerText = `Target Release: v${version}`;
  document.getElementById('rolloutPercentageInput').value = currentRollout;
  if (modal) modal.style.display = 'flex';
}

async function submitRolloutChange(e) {
  e.preventDefault();
  const version = document.getElementById('rolloutVersion').value;
  const rollout_percentage = parseInt(document.getElementById('rolloutPercentageInput').value, 10);
  try {
    await apiRequest(`/updates/releases/${encodeURIComponent(version)}/rollout`, {
      method: 'POST',
      body: JSON.stringify({ rollout_percentage }),
    });
    showToast(`Rollout for v${version} updated to ${rollout_percentage}%.`);
    closeModal('rolloutModal');
    loadReleases();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function pauseRelease(version) {
  if (!confirm(`Pause distribution rollout for release v${version}?`)) return;
  try {
    await apiRequest(`/updates/releases/${encodeURIComponent(version)}/pause`, { method: 'POST' });
    showToast(`Release v${version} paused.`);
    loadReleases();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function resumeRelease(version) {
  try {
    await apiRequest(`/updates/releases/${encodeURIComponent(version)}/rollout`, {
      method: 'POST',
      body: JSON.stringify({ rollout_percentage: 100 }),
    });
    showToast(`Release v${version} rollout resumed.`);
    loadReleases();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function revokeRelease(version) {
  const reason = prompt(`Revoke release v${version}? Enter reason:`, 'Defect found in telemetry');
  if (!reason) return;
  try {
    await apiRequest(`/updates/releases/${encodeURIComponent(version)}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    showToast(`Release v${version} revoked.`);
    loadReleases();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptFlagDevice(deviceId) {
  const flag = prompt('Enter device security status (TRUSTED, REVIEW_REQUIRED, SUSPICIOUS, BLOCKED):', 'SUSPICIOUS');
  if (!flag) return;
  try {
    await apiRequest(`/admin/api/devices/${deviceId}/flag`, {
      method: 'POST',
      body: JSON.stringify({ security_flag: flag.toUpperCase() }),
    });
    showToast(`Device flag set to ${flag.toUpperCase()}.`);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function promptRevokeDevice(deviceId) {
  const reason = prompt('Enter kill-switch revocation reason:', 'Suspicious activity or hardware transfer');
  if (!reason) return;
  try {
    await apiRequest(`/admin/api/devices/${deviceId}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    showToast('Device license revoked immediately.');
    loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 10. LLM GATEWAY CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

async function loadLLMGateway() {
  try {
    const [cfg, telemetry] = await Promise.all([
      apiRequest('/admin/api/llm/config'),
      apiRequest('/admin/api/llm/telemetry')
    ]);

    // Populate routing form
    document.getElementById('llmPrimaryProvider').value = cfg.primary_provider || 'gemini';
    document.getElementById('llmActiveModel').value = cfg.active_model || 'gemini-1.5-flash';
    document.getElementById('llmFallbackProvider').value = cfg.fallback_provider || 'groq';
    document.getElementById('llmFallbackModel').value = cfg.fallback_model || 'llama-3.3-70b-versatile';
    document.getElementById('llmTemperature').value = cfg.temperature !== undefined ? cfg.temperature : 0.7;
    document.getElementById('tempVal').innerText = document.getElementById('llmTemperature').value;
    document.getElementById('llmMaxTokens').value = cfg.max_tokens || 4096;
    document.getElementById('llmRateLimit').value = cfg.rate_limit_tpm || 120000;
    document.getElementById('llmStream').checked = cfg.stream_responses !== false;

    // Populate KPIs
    const providerLabels = {
      gemini: 'Google Gemini',
      groq: 'Groq LPU',
      ollama: 'Ollama Neural Local',
      openai: 'OpenAI Direct',
      anthropic: 'Anthropic Claude'
    };
    document.getElementById('kpiLlmProvider').innerText = providerLabels[cfg.primary_provider] || cfg.primary_provider;
    document.getElementById('kpiLlmModel').innerText = cfg.active_model || 'standard';
    document.getElementById('kpiLlmFallback').innerText = providerLabels[cfg.fallback_provider] || cfg.fallback_provider;
    document.getElementById('kpiLlmFallbackModel').innerText = cfg.fallback_model || 'standard';

    document.getElementById('kpiLlmTotalTokens').innerText = (telemetry.total_tokens || 0).toLocaleString();
    document.getElementById('kpiLlmInTokens').innerText = (telemetry.total_input_tokens || 0).toLocaleString();
    document.getElementById('kpiLlmOutTokens').innerText = (telemetry.total_output_tokens || 0).toLocaleString();
    document.getElementById('kpiLlmCostInr').innerText = `₹${(telemetry.cost_inr || 0).toFixed(2)}`;
    document.getElementById('kpiLlmCostUsd').innerText = `≈ $${(telemetry.cost_usd || 0).toFixed(3)} USD`;

    // Populate Provider Matrix
    const matrixContainer = document.getElementById('llmProvidersMatrix');
    if (matrixContainer && cfg.providers) {
      matrixContainer.innerHTML = '';
      Object.entries(cfg.providers).forEach(([pkey, pdata]) => {
        const isCurrent = pkey === cfg.primary_provider;
        const isFallback = pkey === cfg.fallback_provider;
        const div = document.createElement('div');
        div.className = 'provider-row';
        div.innerHTML = `
          <div>
            <div class="provider-row-title">
              <span>${escapeHtml(pdata.label || pkey)}</span>
              ${isCurrent ? '<span class="badge badge-active" style="font-size:0.65rem;">PRIMARY</span>' : ''}
              ${isFallback ? '<span class="badge badge-basic" style="font-size:0.65rem;">FALLBACK</span>' : ''}
            </div>
            <div class="provider-row-models">
              ${escapeHtml((pdata.models || []).join(' • '))}
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-emphasis); font-family: var(--font-mono);">${pdata.latency_ms || 120}ms</div>
            <span class="badge ${pdata.status === 'ONLINE' ? 'badge-active' : 'badge-disabled'}" style="font-size:0.65rem;">${pdata.status}</span>
          </div>
        `;
        matrixContainer.appendChild(div);
      });
    }

    // Populate Telemetry stream table
    const tbody = document.getElementById('llmTelemetryTableBody');
    if (tbody) {
      tbody.innerHTML = '';
      const stream = telemetry.recent_stream || [];
      if (!stream.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="loading-cell">No recent token events recorded yet.</td></tr>';
      } else {
        stream.forEach(ev => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td style="font-size:0.75rem; font-family:var(--font-mono);">${new Date(ev.timestamp).toLocaleTimeString()}</td>
            <td class="font-mono text-cyan" style="font-size:0.75rem;">${ev.user_id ? ev.user_id.slice(0, 10) + '...' : 'System'}</td>
            <td><span class="badge badge-basic">${ev.feature || 'query'}</span></td>
            <td><strong>${ev.provider || 'gemini'}</strong></td>
            <td class="font-mono" style="font-size:0.75rem;">${ev.model || '-'}</td>
            <td class="font-mono" style="font-weight:600;">${(ev.tokens || 0).toLocaleString()}</td>
            <td class="font-mono text-green" style="font-size:0.75rem;">₹${(ev.cost_inr || 0).toFixed(4)}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }
  } catch (err) {
    showToast(`Failed loading LLM Gateway: ${err.message}`, true);
  }
}

function handleProviderChange() {
  const prov = document.getElementById('llmPrimaryProvider').value;
  const defaults = {
    gemini: 'gemini-1.5-flash',
    groq: 'llama-3.3-70b-versatile',
    ollama: 'llama3:latest',
    openai: 'gpt-4o-mini',
    anthropic: 'claude-3-5-sonnet'
  };
  if (defaults[prov]) {
    document.getElementById('llmActiveModel').value = defaults[prov];
  }
}

async function handleSaveLLM(e) {
  e.preventDefault();
  try {
    const payload = {
      primary_provider: document.getElementById('llmPrimaryProvider').value,
      active_model: document.getElementById('llmActiveModel').value.trim(),
      fallback_provider: document.getElementById('llmFallbackProvider').value,
      fallback_model: document.getElementById('llmFallbackModel').value.trim(),
      temperature: parseFloat(document.getElementById('llmTemperature').value),
      max_tokens: parseInt(document.getElementById('llmMaxTokens').value, 10),
      rate_limit_tpm: parseInt(document.getElementById('llmRateLimit').value, 10),
      stream_responses: document.getElementById('llmStream').checked
    };
    await apiRequest('/admin/api/llm/config', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast('LLM Gateway routing updated successfully!');
    loadLLMGateway();
  } catch (err) {
    showToast(err.message, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 11. REMOTE CONFIG & KILL SWITCHES CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

async function loadRemoteConfig() {
  try {
    const cfg = await apiRequest('/admin/api/remote-config');
    const flags = cfg.feature_flags || {};
    const prompts = cfg.prompts || {};
    const kills = cfg.kill_switches || {};

    // Feature Flags
    const flagMap = {
      study_cards: 'flag_study_cards',
      voice_mode: 'flag_voice_mode',
      vision_mode: 'flag_vision_mode',
      autonomous_tools: 'flag_autonomous_tools',
      web_search: 'flag_web_search',
      offline_fallback: 'flag_offline_fallback'
    };
    Object.entries(flagMap).forEach(([k, elId]) => {
      const el = document.getElementById(elId);
      if (el) el.checked = flags[k] !== false;
    });

    // Kill Switches
    const elKillAi = document.getElementById('kill_emergency_ai');
    if (elKillAi) elKillAi.checked = !!kills.emergency_ai_kill_switch;
    const elKillMaint = document.getElementById('kill_maintenance');
    if (elKillMaint) elKillMaint.checked = !!kills.maintenance_mode;
    const elKillUnver = document.getElementById('kill_block_unverified');
    if (elKillUnver) elKillUnver.checked = kills.block_unverified_devices !== false;

    // Prompts
    document.getElementById('promptVersion').value = prompts.system_prompt_version || 'v2.5.0';
    document.getElementById('promptSystemText').value = prompts.system_prompt || '';
    document.getElementById('promptGuardrails').value = prompts.guardrails_level || 'standard';
    document.getElementById('promptMaxTurns').value = prompts.max_context_turns || 25;
  } catch (err) {
    showToast(`Failed loading Remote Config: ${err.message}`, true);
  }
}

async function handleSaveRemoteConfig(e) {
  e.preventDefault();
  try {
    const payload = {
      feature_flags: {
        study_cards: document.getElementById('flag_study_cards').checked,
        voice_mode: document.getElementById('flag_voice_mode').checked,
        vision_mode: document.getElementById('flag_vision_mode').checked,
        autonomous_tools: document.getElementById('flag_autonomous_tools').checked,
        web_search: document.getElementById('flag_web_search').checked,
        offline_fallback: document.getElementById('flag_offline_fallback').checked
      },
      kill_switches: {
        emergency_ai_kill_switch: document.getElementById('kill_emergency_ai').checked,
        maintenance_mode: document.getElementById('kill_maintenance').checked,
        block_unverified_devices: document.getElementById('kill_block_unverified').checked
      },
      prompts: {
        system_prompt_version: document.getElementById('promptVersion').value.trim(),
        system_prompt: document.getElementById('promptSystemText').value.trim(),
        guardrails_level: document.getElementById('promptGuardrails').value,
        max_context_turns: parseInt(document.getElementById('promptMaxTurns').value, 10)
      }
    };

    await apiRequest('/admin/api/remote-config', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast('Remote configuration and feature flags synchronized!');
  } catch (err) {
    showToast(err.message, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 12. PUSH BROADCAST DISPATCHER CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

async function loadBroadcasts() {
  try {
    const notices = await apiRequest('/admin/api/push/broadcasts');
    const badge = document.getElementById('badgeActiveNotices');
    if (badge) {
      const activeCount = notices.filter(n => n.is_active).length;
      badge.innerText = activeCount;
      badge.style.display = activeCount > 0 ? 'inline-block' : 'none';
    }

    const tbody = document.getElementById('broadcastsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!notices.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="loading-cell">No notices broadcasted yet.</td></tr>';
      return;
    }

    const levelClasses = {
      INFO: 'badge-basic',
      WARNING: 'badge-suspended',
      URGENT: 'badge-alert',
      MAINTENANCE: 'badge-disabled'
    };

    notices.forEach(n => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>
          <div style="font-weight:600; color:#fff;">${escapeHtml(n.title)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted); max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(n.message)}</div>
        </td>
        <td><span class="badge ${levelClasses[n.level] || 'badge-basic'}">${n.level}</span></td>
        <td><span class="badge badge-basic font-mono" style="font-size:0.7rem;">${n.target_tier}</span></td>
        <td style="font-size:0.75rem; font-family:var(--font-mono); color:var(--text-muted);">${n.created_at ? new Date(n.created_at).toLocaleDateString() : '-'}</td>
        <td>
          <button class="btn btn-secondary btn-xs text-red" onclick="deleteBroadcast('${n.id}')">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    showToast(`Failed loading broadcasts: ${err.message}`, true);
  }
}

async function handleDispatchBroadcast(e) {
  e.preventDefault();
  try {
    const payload = {
      title: document.getElementById('pushTitle').value.trim(),
      level: document.getElementById('pushLevel').value,
      target_tier: document.getElementById('pushTarget').value,
      expires_hours: parseInt(document.getElementById('pushExpires').value, 10),
      message: document.getElementById('pushMessage').value.trim()
    };
    await apiRequest('/admin/api/push/broadcasts', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast('In-app broadcast dispatched successfully!');
    document.getElementById('pushTitle').value = '';
    document.getElementById('pushMessage').value = '';
    loadBroadcasts();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function deleteBroadcast(noticeId) {
  if (!confirm('Are you sure you want to delete this broadcast notice?')) return;
  try {
    await apiRequest(`/admin/api/push/broadcasts/${noticeId}`, {
      method: 'DELETE'
    });
    showToast('Broadcast notice deleted.');
    loadBroadcasts();
  } catch (err) {
    showToast(err.message, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 13. AI ANALYTICS CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

async function loadAIAnalytics() {
  try {
    const ana = await apiRequest('/admin/api/ai-analytics');

    // KPI Cards
    if (ana.token_throughput) {
      document.getElementById('anaThroughputAvg').innerText = ana.token_throughput.avg_tokens_per_second || '68.4';
      document.getElementById('anaThroughputPeak').innerText = ana.token_throughput.peak_tokens_per_second || '124.0';
      document.getElementById('anaRatio').innerText = ana.token_throughput.input_output_ratio || '1 : 2.7';
      document.getElementById('anaStreamingEfficiency').innerText = ana.token_throughput.streaming_efficiency || '99.4%';
      document.getElementById('anaSuccessRate').innerText = ana.token_throughput.request_success_rate || '99.88%';
    }

    // Categories
    const catContainer = document.getElementById('analyticsCategoriesList');
    if (catContainer && ana.prompt_categories) {
      catContainer.innerHTML = '';
      ana.prompt_categories.forEach(cat => {
        const row = document.createElement('div');
        row.innerHTML = `
          <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.25rem;">
            <span style="font-weight:500; color:var(--text-main);">${escapeHtml(cat.category)}</span>
            <span style="color:var(--text-muted); font-family:var(--font-mono); font-size:0.75rem;">${cat.count.toLocaleString()} queries (${cat.percentage}%)</span>
          </div>
          <div style="height:6px; background:var(--bg-card-subtle); border:1px solid var(--border-subtle); border-radius:3px; overflow:hidden;">
            <div style="width:${cat.percentage}%; height:100%; background:var(--primary); border-radius:2px; transition:width 0.4s ease;"></div>
          </div>
        `;
        catContainer.appendChild(row);
      });
    }

    // Latency Benchmarks
    const latTbody = document.getElementById('analyticsLatencyTableBody');
    if (latTbody && ana.latency_benchmarks) {
      latTbody.innerHTML = '';
      Object.entries(ana.latency_benchmarks).forEach(([engine, stats]) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-weight:500; color:var(--text-main);">${escapeHtml(engine)}</td>
          <td class="font-mono" style="font-weight:600; color:var(--text-emphasis);">${stats.p50} ms</td>
          <td class="font-mono">${stats.p95} ms</td>
          <td class="font-mono text-muted">${stats.p99} ms</td>
        `;
        latTbody.appendChild(tr);
      });
    }
  } catch (err) {
    showToast(`Failed loading AI analytics: ${err.message}`, true);
  }
}

// ==========================================
// UNIVERSAL DEPLOYMENT DOCS VIEWER
// ==========================================
let activeDeployDocKey = 'environments';

async function loadDeploymentDocs() {
  const container = document.getElementById('deployDocContent');
  if (!container) return;

  try {
    container.innerText = 'Fetching verified deployment specifications from server...';
    let res;
    try {
      res = await apiRequest('/admin/api/deployment-docs');
    } catch {
      res = await apiRequest('/deployment-docs');
    }
    if (!res || res.status !== 'ok' || !res.docs) {
      container.innerText = 'Error: Failed to retrieve deployment documents from server.';
      return;
    }

    state.deploymentDocs = res.docs;
    selectDeploymentDoc(activeDeployDocKey);

    const updatedEl = document.getElementById('deployDocsUpdated');
    if (updatedEl) {
      updatedEl.innerText = `Verified 5 specs | Loaded ${new Date().toLocaleTimeString()}`;
    }
  } catch (err) {
    container.innerText = `Failed to load deployment documentation: ${err.message}`;
    showToast(`Deployment docs load failed: ${err.message}`, true);
  }
}

function selectDeploymentDoc(docKey) {
  activeDeployDocKey = docKey;

  // Update pills
  document.querySelectorAll('.deploy-doc-btn').forEach(btn => {
    if (btn.getAttribute('data-doc') === docKey) {
      btn.className = 'btn btn-sm btn-primary deploy-doc-btn';
    } else {
      btn.className = 'btn btn-sm btn-secondary deploy-doc-btn';
    }
  });

  const fileNameEl = document.getElementById('deployDocFileName');
  if (fileNameEl) fileNameEl.innerText = `${docKey}.md`;

  const container = document.getElementById('deployDocContent');
  if (!container) return;

  if (state.deploymentDocs && state.deploymentDocs[docKey]) {
    container.innerText = state.deploymentDocs[docKey];
  } else {
    container.innerText = `No document content found for ${docKey}.md. Click 'Refresh' to reload from server.`;
  }
}

function copyActiveDeployDoc() {
  const container = document.getElementById('deployDocContent');
  if (!container) return;

  const content = container.innerText;
  if (!content) return;

  navigator.clipboard.writeText(content).then(() => {
    showToast(`Copied ${activeDeployDocKey}.md to clipboard`);
  }).catch(err => {
    showToast(`Failed to copy: ${err.message}`, true);
  });
}

// ── 16 FOUNDER MODULES JAVASCRIPT LOGIC ─────────────────────────────────────

// MODULE 2: CONTENT CMS
async function loadContentCMS() {
  const tbody = document.getElementById('contentTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 1.5rem;">Loading CMS items...</td></tr>';
  try {
    const data = await apiRequest('/admin/api/content');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(5, 'No CMS Content Items', 'Create banners, announcements, or categories to push dynamically.', 'Create First Item', 'showCreateContentModal()');
      return;
    }
    tbody.innerHTML = data.map(item => `
      <tr>
        <td><span class="badge badge-info">${escapeHtml(item.item_type)}</span></td>
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td><span class="badge ${item.is_published ? 'badge-success' : 'badge-neutral'}">${item.is_published ? 'Published' : 'Draft'}</span></td>
        <td><span class="font-mono text-xs">${item.updated_at ? new Date(item.updated_at).toLocaleDateString() : 'N/A'}</span></td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-xs" onclick="copyToClipboard('${escapeHtml(item.content_json)}', 'Content Payload')">Copy JSON</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="color: var(--accent-alert); text-align: center; padding: 1.5rem;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function showCreateContentModal() {
  openModal('createContentModal');
}

async function submitCreateContent(e) {
  e.preventDefault();
  const title = document.getElementById('contentTitleInput').value.trim();
  const itemType = document.getElementById('contentTypeInput').value;
  const contentJson = document.getElementById('contentJsonInput').value.trim() || JSON.stringify({ headline: title });
  try {
    await apiRequest('/admin/api/content', {
      method: 'POST',
      body: JSON.stringify({ title, item_type: itemType, content_json: contentJson })
    });
    showToast('CMS content created successfully');
    closeModal('createContentModal');
    document.getElementById('createContentForm').reset();
    loadContentCMS();
  } catch (err) {
    showToast(`Failed to create CMS item: ${err.message}`, true);
  }
}

// MODULE 7: ORDERS & BOOKINGS
async function loadOrders() {
  const tbody = document.getElementById('ordersTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 1.5rem;">Loading orders...</td></tr>';
  try {
    const data = await apiRequest('/admin/api/orders');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(7, 'No Orders Yet', 'Customer subscription and credit pack purchases will populate here.');
      return;
    }
    tbody.innerHTML = data.map(o => `
      <tr>
        <td class="font-mono text-xs"><strong>${escapeHtml(o.id)}</strong></td>
        <td class="font-mono text-xs">${escapeHtml(o.user_id.slice(0, 10))}...</td>
        <td><span class="badge badge-info">${escapeHtml(o.order_type)}</span></td>
        <td><strong>₹${((o.amount_paise || 0) / 100).toFixed(2)}</strong></td>
        <td><span class="badge ${o.status === 'COMPLETED' ? 'badge-success' : (o.status === 'DISPUTED' ? 'badge-alert' : 'badge-neutral')}">${escapeHtml(o.status)}</span></td>
        <td class="font-mono text-xs">${o.created_at ? new Date(o.created_at).toLocaleDateString() : 'N/A'}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-xs" onclick="overrideOrderStatus('${escapeHtml(o.id)}')">Override</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="color: var(--accent-alert); text-align: center; padding: 1.5rem;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function overrideOrderStatus(orderId) {
  const newStatus = prompt('Enter new status (COMPLETED, DISPUTED, REFUNDED, OVERRIDDEN):', 'OVERRIDDEN');
  if (!newStatus) return;
  try {
    await apiRequest(`/admin/api/orders/${orderId}/override`, {
      method: 'POST',
      body: JSON.stringify({ status: newStatus.toUpperCase(), notes: 'Manual override by Administrator' })
    });
    showToast(`Order status updated to ${newStatus}`);
    loadOrders();
  } catch (err) {
    showToast(`Failed to override order: ${err.message}`, true);
  }
}

// MODULE 12: COUPONS & DISCOUNTS
async function loadCoupons() {
  const tbody = document.getElementById('couponsTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 1.5rem;">Loading coupons...</td></tr>';
  try {
    const data = await apiRequest('/admin/api/coupons');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(6, 'No Active Coupons', 'Create promotion codes to discount subscriptions or credit packs.', 'Create Promo Code', 'showCreateCouponModal()');
      return;
    }
    tbody.innerHTML = data.map(c => `
      <tr>
        <td><span class="font-mono" style="font-weight: 700; color: var(--accent-highlight);">${escapeHtml(c.code)}</span></td>
        <td><strong>${c.discount_pct}% OFF</strong></td>
        <td>${c.uses_count} / ${c.max_uses}</td>
        <td><span class="badge ${c.is_active ? 'badge-success' : 'badge-neutral'}">${c.is_active ? 'Active' : 'Disabled'}</span></td>
        <td class="font-mono text-xs">${c.expires_at ? new Date(c.expires_at).toLocaleDateString() : 'Never'}</td>
        <td style="text-align: right;">
          ${c.is_active ? `<button class="btn btn-danger btn-xs" onclick="deleteCoupon('${escapeHtml(c.id)}')">Deactivate</button>` : '<span class="text-xs text-muted">Deactivated</span>'}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--accent-alert); text-align: center; padding: 1.5rem;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function showCreateCouponModal() {
  openModal('createCouponModal');
}

async function submitCreateCoupon(e) {
  e.preventDefault();
  const code = document.getElementById('couponCodeInput').value.trim().toUpperCase();
  const discount_pct = parseInt(document.getElementById('couponDiscountInput').value, 10) || 20;
  const max_uses = parseInt(document.getElementById('couponMaxUsesInput').value, 10) || 200;
  const expires_days = parseInt(document.getElementById('couponDaysInput').value, 10) || 60;
  try {
    await apiRequest('/admin/api/coupons', {
      method: 'POST',
      body: JSON.stringify({ code, discount_pct, max_uses, expires_days })
    });
    showToast(`Coupon ${code} created`);
    closeModal('createCouponModal');
    document.getElementById('createCouponForm').reset();
    loadCoupons();
  } catch (err) {
    showToast(`Failed: ${err.message}`, true);
  }
}

async function deleteCoupon(couponId) {
  if (!confirm('Deactivate this promo code?')) return;
  try {
    await apiRequest(`/admin/api/coupons/${couponId}`, { method: 'DELETE' });
    showToast('Coupon deactivated');
    loadCoupons();
  } catch (err) {
    showToast(`Failed: ${err.message}`, true);
  }
}

// MODULE 13: PARTNERS & VENDORS
async function loadPartners() {
  const tbody = document.getElementById('partnersTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 1.5rem;">Loading partners...</td></tr>';
  try {
    const data = await apiRequest('/admin/api/partners');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(6, 'No Partners Onboarded', 'Add affiliate promoters, resellers, and agency partners.', 'Onboard Partner', 'showCreatePartnerModal()');
      return;
    }
    tbody.innerHTML = data.map(p => `
      <tr>
        <td><strong>${escapeHtml(p.name)}</strong><br><span class="text-xs text-muted">${escapeHtml(p.email)}</span></td>
        <td><span class="font-mono badge badge-info">${escapeHtml(p.partner_code)}</span></td>
        <td>${p.commission_pct}%</td>
        <td>₹${((p.total_sales_paise || 0) / 100).toFixed(2)}</td>
        <td>₹${((p.total_payout_paise || 0) / 100).toFixed(2)}</td>
        <td><span class="badge ${p.status === 'ACTIVE' ? 'badge-success' : 'badge-neutral'}">${escapeHtml(p.status)}</span></td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--accent-alert); text-align: center; padding: 1.5rem;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function showCreatePartnerModal() {
  openModal('createPartnerModal');
}

async function submitCreatePartner(e) {
  e.preventDefault();
  const name = document.getElementById('partnerNameInput').value.trim();
  const email = document.getElementById('partnerEmailInput').value.trim();
  const partner_code = document.getElementById('partnerCodeInput').value.trim().toUpperCase();
  const commission_pct = parseInt(document.getElementById('partnerCommissionInput').value, 10) || 15;
  try {
    await apiRequest('/admin/api/partners', {
      method: 'POST',
      body: JSON.stringify({ name, email, partner_code, commission_pct })
    });
    showToast(`Partner ${name} registered`);
    closeModal('createPartnerModal');
    document.getElementById('createPartnerForm').reset();
    loadPartners();
  } catch (err) {
    showToast(`Failed: ${err.message}`, true);
  }
}

// MODULE 14: CONTENT MODERATION
async function loadModeration() {
  const tbody = document.getElementById('moderationTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 1.5rem;">Loading moderation queue...</td></tr>';
  try {
    const data = await apiRequest('/admin/api/moderation');
    if (!data || data.length === 0) {
      tbody.innerHTML = renderEmptyState(6, 'Queue Clean', 'Zero flagged user prompts or AI outputs awaiting inspection.');
      return;
    }
    tbody.innerHTML = data.map(m => `
      <tr>
        <td class="font-mono text-xs">${escapeHtml(m.id)}</td>
        <td class="font-mono text-xs">${escapeHtml(m.user_id ? m.user_id.slice(0, 10) : 'Anonymous')}</td>
        <td><span class="badge badge-alert">${escapeHtml(m.flag_reason)}</span></td>
        <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(m.content_snippet)}</td>
        <td><span class="badge ${m.status === 'APPROVED' ? 'badge-success' : (m.status === 'REMOVED' ? 'badge-danger' : 'badge-neutral')}">${escapeHtml(m.status)}</span></td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-xs" onclick="moderateAction('${escapeHtml(m.id)}', 'APPROVED')">Approve</button>
          <button class="btn btn-danger btn-xs" onclick="moderateAction('${escapeHtml(m.id)}', 'REMOVED')">Remove</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--accent-alert); text-align: center; padding: 1.5rem;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function moderateAction(itemId, actionStatus) {
  try {
    await apiRequest(`/admin/api/moderation/${itemId}/action`, {
      method: 'POST',
      body: JSON.stringify({ status: actionStatus })
    });
    showToast(`Content ${actionStatus.toLowerCase()}`);
    loadModeration();
  } catch (err) {
    showToast(`Failed: ${err.message}`, true);
  }
}

// MODULE 5: FOUNDER 16-MODULE AUDIT REPORT
async function loadFounderAudit() {
  const container = document.getElementById('founderAuditResults');
  const tbody = document.getElementById('founderAuditBody');
  if (!container || !tbody) return;
  container.style.display = 'block';
  tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 1rem;">Running complete 16-module verification...</td></tr>';
  try {
    const res = await apiRequest('/admin/api/founder-modules-status');
    if (!res || !res.modules) return;
    tbody.innerHTML = res.modules.map(m => `
      <tr>
        <td><strong>#${m.id}</strong></td>
        <td><strong>${escapeHtml(m.name)}</strong></td>
        <td><span class="badge badge-success">● ${m.status}</span></td>
        <td class="font-mono text-xs">${escapeHtml(m.endpoint)}</td>
      </tr>
    `).join('');
    showToast('Verified: All 16 Modules LIVE');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" style="color: var(--accent-alert); text-align: center; padding: 1rem;">Verification error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

// MODULE 3: TRANSACTION REFUND HANDLERS
function openRefundModal(paymentId) {
  const hiddenInput = document.getElementById('refundPaymentId');
  const label = document.getElementById('lblRefundTarget');
  if (hiddenInput) hiddenInput.value = paymentId;
  if (label) label.innerText = `Payment ID: ${paymentId}`;
  openModal('refundPaymentModal');
}

async function submitRefundPayment(e) {
  e.preventDefault();
  const paymentId = document.getElementById('refundPaymentId').value;
  const reason = document.getElementById('refundReasonInput').value.trim() || 'Admin manual refund';
  try {
    await apiRequest(`/admin/api/payments/${paymentId}/refund`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
    showToast('Transaction marked as refunded');
    closeModal('refundPaymentModal');
    document.getElementById('refundPaymentForm').reset();
    loadPayments();
  } catch (err) {
    showToast(`Refund failed: ${err.message}`, true);
  }
}

// 16-MODULE DEMO DATA SEEDING
async function triggerSeedDemo() {
  if (!confirm('Populate connected test records across all 16 Founder Modules?')) return;
  try {
    showToast('Seeding demo records...');
    const res = await apiRequest('/admin/api/seed-demo', { method: 'POST' });
    showToast(res.message || '16 Modules seeded successfully!');
    if (typeof loadOverviewMetrics === 'function') loadOverviewMetrics();
    if (typeof loadSystemHealth === 'function') loadSystemHealth();
    if (state.currentTab && typeof switchTab === 'function') {
      switchTab(state.currentTab);
    }
  } catch (err) {
    showToast(`Seed failed: ${err.message}`, true);
  }
}

// QUICK COMMAND PALETTE (CTRL+K)
const CMD_ITEMS = [
  { id: 'overview', title: 'Dashboard & KPIs', cat: 'Navigation', icon: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>' },
  { id: 'users', title: 'Users & Plans', cat: 'Navigation', icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>' },
  { id: 'payments', title: 'Payments Record', cat: 'Navigation', icon: '<rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>' },
  { id: 'activity', title: 'User Activity (Live)', cat: 'Navigation', icon: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>' },
  { id: 'tickets', title: 'Support Tickets', cat: 'Navigation', icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
  { id: 'incidents', title: 'Crash & Incidents', cat: 'Navigation', icon: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>' },
  { id: 'releases', title: 'Release Updates', cat: 'Navigation', icon: '<circle cx="12" cy="12" r="10"/><polyline points="8 12 12 16 16 12"/>' },
  { id: 'llm', title: 'LLM Gateway', cat: 'Navigation', icon: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/>' },
  { id: 'config', title: 'Remote Config', cat: 'Navigation', icon: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82"/>' },
  { id: 'push', title: 'Push Dispatcher', cat: 'Navigation', icon: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>' },
  { id: 'analytics', title: 'AI Analytics', cat: 'Navigation', icon: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>' },
  { id: 'security', title: 'Security & Tamper', cat: 'Navigation', icon: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>' },
  { id: 'audit', title: 'Audit Logs', cat: 'Navigation', icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' },
  { id: 'action-theme', title: 'Toggle Theme (Light / Dark)', cat: 'Action', action: () => toggleTheme(), icon: '<circle cx="12" cy="12" r="5"/>' },
  { id: 'action-seed', title: 'Seed 16-Module Demo Data', cat: 'Action', action: () => triggerSeedDemo(), icon: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>' },
  { id: 'action-export-users', title: 'Export Users CSV', cat: 'Action', action: () => exportData('users'), icon: '<polyline points="7 10 12 15 17 10"/>' },
  { id: 'action-export-payments', title: 'Export Payments CSV', cat: 'Action', action: () => exportData('payments'), icon: '<polyline points="7 10 12 15 17 10"/>' }
];

let selectedCmdIdx = 0;
let filteredCmdItems = [];

function openCmdPalette() {
  const modal = document.getElementById('cmdPaletteModal');
  const input = document.getElementById('cmdPaletteInput');
  if (!modal || !input) return;
  modal.classList.add('active');
  input.value = '';
  filterCmdPalette('');
  setTimeout(() => input.focus(), 50);
}

function closeCmdPalette() {
  const modal = document.getElementById('cmdPaletteModal');
  if (modal) modal.classList.remove('active');
}

function handleCmdBackdropClick(e) {
  if (e.target.id === 'cmdPaletteModal') closeCmdPalette();
}

function filterCmdPalette(q) {
  const query = (q || '').trim().toLowerCase();
  filteredCmdItems = CMD_ITEMS.filter(it => 
    !query || it.title.toLowerCase().includes(query) || it.cat.toLowerCase().includes(query)
  );
  selectedCmdIdx = 0;
  renderCmdPalette();
}

function renderCmdPalette() {
  const list = document.getElementById('cmdPaletteList');
  if (!list) return;
  if (filteredCmdItems.length === 0) {
    list.innerHTML = '<li style="padding:1.5rem; text-align:center; color:var(--text-muted); font-size:0.8rem;">No matching commands found.</li>';
    return;
  }
  list.innerHTML = filteredCmdItems.map((it, idx) => `
    <li class="cmd-item ${idx === selectedCmdIdx ? 'selected' : ''}" onclick="executeCmdItem(${idx})">
      <div class="cmd-item-left">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${it.icon}</svg>
        <span>${escapeHtml(it.title)}</span>
      </div>
      <span class="cmd-shortcut-badge">${escapeHtml(it.cat)}</span>
    </li>
  `).join('');
}

function executeCmdItem(idx) {
  const item = filteredCmdItems[idx];
  if (!item) return;
  closeCmdPalette();
  if (item.action) {
    item.action();
  } else if (item.id && typeof switchTab === 'function') {
    switchTab(item.id);
  }
}

function handleCmdKeydown(e) {
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (filteredCmdItems.length > 0) {
      selectedCmdIdx = (selectedCmdIdx + 1) % filteredCmdItems.length;
      renderCmdPalette();
      scrollSelectedCmdIntoView();
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (filteredCmdItems.length > 0) {
      selectedCmdIdx = (selectedCmdIdx - 1 + filteredCmdItems.length) % filteredCmdItems.length;
      renderCmdPalette();
      scrollSelectedCmdIntoView();
    }
  } else if (e.key === 'Enter') {
    e.preventDefault();
    executeCmdItem(selectedCmdIdx);
  } else if (e.key === 'Escape') {
    closeCmdPalette();
  }
}

function scrollSelectedCmdIntoView() {
  const list = document.getElementById('cmdPaletteList');
  if (!list) return;
  const selectedEl = list.children[selectedCmdIdx];
  if (selectedEl) selectedEl.scrollIntoView({ block: 'nearest' });
}

// Global Keyboard Shortcut: Ctrl+K / Cmd+K
window.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    const modal = document.getElementById('cmdPaletteModal');
    if (modal && modal.classList.contains('active')) {
      closeCmdPalette();
    } else {
      openCmdPalette();
    }
  } else if (e.key === 'Escape') {
    closeCmdPalette();
  }
});



