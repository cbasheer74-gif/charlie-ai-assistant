/* ==========================================================================
   CHARLIE AI Assistant Landing Page Script
   Interactive HUD, Live Simulator, Comparison Filters, and FAQ
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  initSimulator();
  initPromptPlayground();
  initHardwareCalculator();
  initFaqAccordion();
  initDynamicWaveform();
  initSmoothScroll();
  initDownloadHandlers();
  initAuthModal();
  initSystemCompatibilityDetection();
  initSkillDirectoryFilter();
  initPricingCheckout();
});

/* --------------------------------------------------------------------------
   Interactive Task Simulator
   -------------------------------------------------------------------------- */
const SIMULATOR_DATA = {
  filmora: {
    command: 'charlie "Edit raw_footage.mp4 in Filmora, apply cinematic lut, add subtitle track, and export a 60-second vertical YouTube Short."',
    status: 'OPTIMIZED TASK GRAPH: Filmora14AutomationPipeline [Nodes: 6, Workers: 2]',
    logs: [
      '[0.12s] Hooked Filmora 14 COM API process session.',
      '[0.84s] Imported 4K ProRes media to timeline Track 1.',
      '[1.30s] Applied auto-reframe to 9:16 vertical aspect ratio.',
      '[1.95s] Whisper transcription generated synchronized dynamic captions.',
      '[2.40s] Hardware NVENC GPU render initiated (1080x1920 @ 60fps).',
      '[3.82s] SUCCESS: Render complete. File saved to /exports/shorts_master.mp4'
    ],
    metric: 'Rendering time: 3.8s · 100% Autonomous'
  },
  coding: {
    command: 'charlie "Inspect engine/router.py, locate async WebSocket bottleneck, add backpressure buffering, and verify with pytest."',
    status: 'CODEBASE COPILOT: Local Multi-Agent Workspace Inspection',
    logs: [
      '[0.08s] Scanned repository AST (48 python files indexed).',
      '[0.45s] Identified WebSocket queue lock contention in engine/router.py:L142.',
      '[0.98s] Synthesized async queue buffer with asyncio.PriorityQueue.',
      '[1.52s] Applied atomic dry-run diff and ran 14 test cases.',
      '[2.10s] Tests verified: 14 passed in 0.18s. Zero regressions.'
    ],
    metric: 'Code refactor verified · 0 hallucinations'
  },
  voice: {
    command: 'charlie "Switch persona to Female voice and give me today\'s priority morning briefing."',
    status: 'DUAL-NEURAL PERSONA ENGINE: Seamless Voice & Identity Switch',
    logs: [
      '[0.05s] Voice gate authorized: Female neural voice unlocked.',
      '[0.11s] Persona profile loaded: Female avatar HUD synchronized.',
      '[0.24s] Speech synthesis rendered with expressive inflection (EdgeTTS/Local).',
      '[0.35s] CHARLIE speaking: "Good morning! You have 3 urgent emails and your code build is green."'
    ],
    metric: 'Latency: 120ms · 100% Local TTS available'
  },
  spreadsheet: {
    command: 'charlie "Calculate Q3 revenue trends from sales.xlsx, generate profit projections, and format summary sheet."',
    status: 'OFFICE AUTOMATION: Local Excel / OpenPyXL Data Agent',
    logs: [
      '[0.10s] Excel workbook opened in memory buffer.',
      '[0.32s] Cleaned null values and computed MoM revenue growth (+24.8%).',
      '[0.65s] Applied financial conditional formatting and generated forecast chart.',
      '[0.88s] SUCCESS: Saved workbook to sales_q3_summary.xlsx.'
    ],
    metric: 'Execution time: 0.88s · Offline safe'
  }
};

function initSimulator() {
  const tabs = document.querySelectorAll('.sim-tab');
  const termCommand = document.getElementById('sim-command');
  const termStatus = document.getElementById('sim-status');
  const termLogs = document.getElementById('sim-logs');
  const termMetric = document.getElementById('sim-metric');

  if (!tabs.length || !termCommand) return;

  function loadDemo(key) {
    const data = SIMULATOR_DATA[key];
    if (!data) return;

    termCommand.textContent = data.command;
    termStatus.textContent = data.status;
    termMetric.textContent = data.metric;

    termLogs.innerHTML = '';
    data.logs.forEach((log, i) => {
      const p = document.createElement('div');
      p.className = 'term-line';
      p.style.opacity = '0';
      p.style.transform = 'translateX(-6px)';
      p.style.transition = 'all 0.25s ease';
      
      const timeMatch = log.match(/^\[([^\]]+)\]\s*(.*)$/);
      let timeHtml = '';
      let msgText = log;
      if (timeMatch) {
        timeHtml = `<span class="exec-time-badge">${timeMatch[1]}</span>`;
        msgText = timeMatch[2];
      }
      p.innerHTML = `${timeHtml}<span class="exec-log-text">${msgText}</span>`;
      termLogs.appendChild(p);

      setTimeout(() => {
        p.style.opacity = '1';
        p.style.transform = 'translateX(0)';
      }, i * 90);
    });
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const key = tab.getAttribute('data-demo');
      loadDemo(key);
    });
  });

  // Initial load
  loadDemo('filmora');
}

/* --------------------------------------------------------------------------
   Dynamic Waveform Visualizer
   -------------------------------------------------------------------------- */
function initDynamicWaveform() {
  const waveBars = document.querySelectorAll('.wave-bar');
  if (!waveBars.length) return;

  setInterval(() => {
    waveBars.forEach(bar => {
      const randHeight = Math.floor(Math.random() * 45) + 15;
      bar.style.height = `${randHeight}px`;
    });
  }, 180);
}

/* --------------------------------------------------------------------------
   FAQ Accordion
   -------------------------------------------------------------------------- */
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(item => {
    const question = item.querySelector('.faq-question');
    if (question) {
      question.addEventListener('click', () => {
        const isOpen = item.classList.contains('open');
        faqItems.forEach(i => i.classList.remove('open'));
        if (!isOpen) {
          item.classList.add('open');
        }
      });
    }
  });
}

/* --------------------------------------------------------------------------
   Smooth Scroll
   -------------------------------------------------------------------------- */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
}

/* --------------------------------------------------------------------------
   Download Flow & Holographic HUD Modal
   -------------------------------------------------------------------------- */
function initDownloadHandlers() {
  const modal = document.getElementById('download-modal');
  const closeBtn = document.getElementById('modal-close-btn');
  const closeDot = document.getElementById('modal-close-dot');
  const gotItBtn = document.getElementById('modal-got-it-btn');
  const progressBar = document.getElementById('modal-progress-fill');
  const statusText = document.getElementById('modal-status-text');
  const filenameDisplay = document.getElementById('modal-filename-display');
  const downloadBtns = document.querySelectorAll('.download-trigger-btn');

  function closeModal() {
    if (modal) {
      modal.classList.remove('active');
      modal.setAttribute('aria-hidden', 'true');
    }
    const authModal = document.getElementById('auth-modal');
    if (!authModal || !authModal.classList.contains('is-open')) {
      document.body.classList.remove('modal-open');
      document.documentElement.classList.remove('modal-open');
    }
  }

  function openModal(filename) {
    if (!modal) return;
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');

    const name = filename || 'CHARLIE-Setup.exe';

    if (filenameDisplay) {
      filenameDisplay.innerHTML = `Downloading <strong>${name}</strong> (151 MB)`;
    }

    if (progressBar) progressBar.style.width = '0%';
    if (statusText) statusText.textContent = 'Preparing installation package...';

    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');

    // Smooth status sequence
    setTimeout(() => {
      if (progressBar) progressBar.style.width = '45%';
      if (statusText) statusText.textContent = 'Starting download...';
    }, 250);

    setTimeout(() => {
      if (progressBar) progressBar.style.width = '80%';
      if (statusText) statusText.textContent = 'Transferring installer...';
    }, 600);

    setTimeout(() => {
      if (progressBar) progressBar.style.width = '100%';
      if (statusText) statusText.textContent = 'Download started. Follow the steps below.';
    }, 950);
  }

  // Hook all download buttons
  downloadBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const file = btn.getAttribute('data-file') || 'CHARLIE-Setup.exe';
      const targetHref = btn.getAttribute('href');

      // Trigger modal
      openModal(file);

      // Programmatically trigger download if needed (only when not a direct file link)
      if (!targetHref || targetHref.startsWith('#')) {
        e.preventDefault();
        const a = document.createElement('a');
        a.href = 'downloads/' + file;
        a.download = file;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    });
  });

  // Close handlers
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (closeDot) closeDot.addEventListener('click', closeModal);
  if (gotItBtn) gotItBtn.addEventListener('click', closeModal);

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
    modal.addEventListener('wheel', (e) => {
      if (e.target === modal) e.preventDefault();
    }, { passive: false });
    modal.addEventListener('touchmove', (e) => {
      if (e.target === modal) e.preventDefault();
    }, { passive: false });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
      closeModal();
    }
  });
}

/* --------------------------------------------------------------------------
   Toast Notifications
   -------------------------------------------------------------------------- */
function showToast(message, isSuccess = true) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast-message';
  const icon = isSuccess ? '✓' : 'ℹ';
  toast.innerHTML = `<span style="color: var(--cyan-primary); font-size: 14px;">${icon}</span> <span>${message}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px) scale(0.95)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

/* --------------------------------------------------------------------------
   Authentication Modal & Session Management
   -------------------------------------------------------------------------- */
function initAuthModal() {
  const authModal = document.getElementById('auth-modal');
  const closeBtn = document.getElementById('auth-close-btn');
  const tabSignIn = document.getElementById('tab-btn-signin');
  const tabSignUp = document.getElementById('tab-btn-signup');
  const heading = document.getElementById('auth-heading');
  const subheading = document.getElementById('auth-subheading');
  const groupName = document.getElementById('group-name');
  const submitBtn = document.getElementById('btn-submit-auth');
  const authForm = document.getElementById('auth-form');
  const pwToggle = document.getElementById('pw-toggle');
  const pwInput = document.getElementById('auth-password');
  const headerSignIn = document.getElementById('btn-header-signin');
  const headerSignUp = document.getElementById('btn-header-signup');
  const userProfile = document.getElementById('header-user-profile');
  const userAvatar = document.getElementById('header-user-avatar');
  const userEmail = document.getElementById('header-user-email');
  const logoutBtn = document.getElementById('btn-header-logout');

  if (!authModal) return;

  function updateHeaderAuth(user) {
    if (user) {
      if (headerSignIn) headerSignIn.style.display = 'none';
      if (headerSignUp) headerSignUp.style.display = 'none';
      if (userProfile) {
        userProfile.style.display = 'flex';
        const initials = (user.name || user.email || 'JD').substring(0, 2).toUpperCase();
        if (userAvatar) userAvatar.textContent = initials;
        if (userEmail) userEmail.textContent = user.email;
      }
    } else {
      if (headerSignIn) headerSignIn.style.display = '';
      if (headerSignUp) headerSignUp.style.display = '';
      if (userProfile) userProfile.style.display = 'none';
    }
  }

  // Check saved session
  try {
    const saved = localStorage.getItem('charlie_auth_user');
    if (saved) {
      updateHeaderAuth(JSON.parse(saved));
    }
  } catch (_) {}

  // Open modal
  function openAuth(mode = 'signin') {
    authModal.classList.add('is-open');
    authModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
    switchTab(mode);
  }

  // Close modal
  function closeAuth() {
    authModal.classList.remove('is-open');
    authModal.setAttribute('aria-hidden', 'true');
    const downloadModal = document.getElementById('download-modal');
    if (!downloadModal || !downloadModal.classList.contains('active')) {
      document.body.classList.remove('modal-open');
      document.documentElement.classList.remove('modal-open');
    }
    if (window.location.hash === '#signin' || window.location.hash === '#signup') {
      history.replaceState(null, null, ' ');
    }
  }

  // Tab switching
  function switchTab(mode) {
    if (mode === 'signup') {
      if (tabSignUp) tabSignUp.classList.add('active');
      if (tabSignIn) tabSignIn.classList.remove('active');
      if (groupName) groupName.style.display = 'flex';
      if (heading) heading.textContent = 'Create CHARLIE Account';
      if (subheading) subheading.textContent = 'Get 10 min daily access or activate your commercial license.';
      if (submitBtn) submitBtn.textContent = 'Create Free Account';
    } else {
      if (tabSignIn) tabSignIn.classList.add('active');
      if (tabSignUp) tabSignUp.classList.remove('active');
      if (groupName) groupName.style.display = 'none';
      if (heading) heading.textContent = 'Welcome Back to CHARLIE';
      if (subheading) subheading.textContent = 'Sync your licenses, custom agents, and preferences across devices.';
      if (submitBtn) submitBtn.textContent = 'Sign In to CHARLIE';
    }
  }

  // Hook all auth-open triggers
  document.querySelectorAll('.auth-open-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const mode = btn.getAttribute('data-tab') || 'signin';
      openAuth(mode);
    });
  });

  if (tabSignIn) tabSignIn.addEventListener('click', () => switchTab('signin'));
  if (tabSignUp) tabSignUp.addEventListener('click', () => switchTab('signup'));
  if (closeBtn) closeBtn.addEventListener('click', closeAuth);

  authModal.addEventListener('click', (e) => {
    if (e.target === authModal) closeAuth();
  });

  authModal.addEventListener('wheel', (e) => {
    if (e.target === authModal) e.preventDefault();
  }, { passive: false });

  authModal.addEventListener('touchmove', (e) => {
    if (e.target === authModal) e.preventDefault();
  }, { passive: false });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && authModal.classList.contains('is-open')) {
      closeAuth();
    }
  });

  // Password visibility toggle
  if (pwToggle && pwInput) {
    pwToggle.addEventListener('click', () => {
      pwInput.type = pwInput.type === 'password' ? 'text' : 'password';
      pwToggle.textContent = pwInput.type === 'password' ? '👁' : '🔒';
    });
  }

  // Social OAuth click handlers
  document.querySelectorAll('.btn-social-auth').forEach(btn => {
    btn.addEventListener('click', () => {
      const provider = btn.getAttribute('data-provider') || 'OAuth';
      btn.style.opacity = '0.6';
      btn.style.pointerEvents = 'none';

      showToast(`Connecting via ${provider}...`);

      setTimeout(() => {
        const mockUser = {
          name: `${provider} Creator`,
          email: `user@${provider.toLowerCase()}.com`,
          provider: provider
        };
        try {
          localStorage.setItem('charlie_auth_user', JSON.stringify(mockUser));
        } catch (_) {}

        updateHeaderAuth(mockUser);
        btn.style.opacity = '';
        btn.style.pointerEvents = '';
        closeAuth();
        showToast(`Welcome! Signed in with ${provider}.`);
      }, 700);
    });
  });

  // Form submit handler
  if (authForm) {
    authForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('auth-email');
      const nameInput = document.getElementById('auth-name');
      const pwInput = document.getElementById('auth-password');
      const email = emailInput ? emailInput.value.trim() : '';
      const password = pwInput ? pwInput.value : '';
      const name = (nameInput && nameInput.value) ? nameInput.value.trim() : email.split('@')[0];
      const isSignUp = tabSignUp && tabSignUp.classList.contains('active');

      if (!email || !password) {
        showToast('Please enter both email and password.');
        return;
      }

      if (submitBtn) {
        submitBtn.textContent = isSignUp ? 'Creating Account...' : 'Authenticating...';
        submitBtn.disabled = true;
      }

      try {
        const endpoint = isSignUp ? '/auth/register' : '/auth/login';
        const payload = isSignUp
          ? { email, password, display_name: name || 'CHARLIE User' }
          : { email, password };

        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!data.success) {
          showToast(`Error: ${data.error || 'Authentication failed'}`);
          if (submitBtn) {
            submitBtn.textContent = isSignUp ? 'Create Free Account' : 'Sign In to CHARLIE';
            submitBtn.disabled = false;
          }
          return;
        }

        const userData = data.data || { email, name };
        if (userData.access_token) {
          localStorage.setItem('charlie_access_token', userData.access_token);
          if (userData.refresh_token) localStorage.setItem('charlie_refresh_token', userData.refresh_token);
        }
        localStorage.setItem('charlie_auth_user', JSON.stringify(userData));
        updateHeaderAuth(userData);
        closeAuth();
        showToast(isSignUp ? `Welcome ${userData.display_name || email}! Starter 10m/day active.` : `Welcome back, ${userData.display_name || email}!`);

        const pendingPlan = sessionStorage.getItem('pending_checkout_plan');
        if (pendingPlan) {
          sessionStorage.removeItem('pending_checkout_plan');
          initiateCheckout(pendingPlan);
        }
      } catch (err) {
        const user = { email, name, plan: 'STARTER' };
        localStorage.setItem('charlie_auth_user', JSON.stringify(user));
        updateHeaderAuth(user);
        closeAuth();
        showToast(`Signed in as ${email}.`);
      } finally {
        if (submitBtn) {
          submitBtn.textContent = isSignUp ? 'Create Free Account' : 'Sign In to CHARLIE';
          submitBtn.disabled = false;
        }
      }
    });
  }

  // Logout handler
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      try {
        localStorage.removeItem('charlie_auth_user');
        localStorage.removeItem('charlie_access_token');
        localStorage.removeItem('charlie_refresh_token');
      } catch (_) {}
      updateHeaderAuth(null);
      showToast('Signed out of CHARLIE workspace.');
    });
  }


  // Auto-open if URL has hash
  if (window.location.hash === '#signin') {
    openAuth('signin');
  } else if (window.location.hash === '#signup') {
    openAuth('signup');
  }
}

/* --------------------------------------------------------------------------
   System Compatibility Hardware Detection
   -------------------------------------------------------------------------- */
function initSystemCompatibilityDetection() {
  const detectTitle = document.getElementById('client-os-detect');
  const detectSub = document.getElementById('client-os-status');
  const detectBadge = document.getElementById('client-os-badge');
  if (!detectTitle || !detectSub || !detectBadge) return;

  const ua = navigator.userAgent || '';
  let osName = 'Windows 64-bit';
  let isWindows = true;

  if (ua.indexOf('Mac') !== -1) {
    osName = 'macOS (Apple Silicon & Intel)';
    isWindows = false;
  } else if (ua.indexOf('Linux') !== -1) {
    osName = 'Linux (x86_64 / ARM64)';
    isWindows = false;
  } else if (ua.indexOf('Win') !== -1) {
    osName = 'Windows 10 / 11 (64-bit)';
    isWindows = true;
  }

  const memory = (navigator.deviceMemory && navigator.deviceMemory >= 8)
    ? `${navigator.deviceMemory} GB RAM detected`
    : '8 GB+ RAM recommended';
  const cores = navigator.hardwareConcurrency
    ? `${navigator.hardwareConcurrency} CPU threads detected`
    : 'Multi-core CPU detected';

  detectTitle.textContent = `Your Machine: ${osName}`;
  detectSub.textContent = `${cores} • ${memory} • 100% Fully Compatible with CHARLIE AI Desktop`;
  detectBadge.textContent = '✓ System Ready';
  detectBadge.className = 'compat-status-pill ready';
}

/* --------------------------------------------------------------------------
   Skill Directory Category Filter
   -------------------------------------------------------------------------- */
function initSkillDirectoryFilter() {
  const filterBtns = document.querySelectorAll('.skill-filter-btn');
  const skillCards = document.querySelectorAll('.skill-item-card');
  if (!filterBtns.length || !skillCards.length) return;

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const filter = btn.getAttribute('data-filter') || 'all';

      skillCards.forEach(card => {
        const cat = card.getAttribute('data-category');
        if (filter === 'all' || cat === filter) {
          card.classList.remove('is-hidden');
        } else {
          card.classList.add('is-hidden');
        }
      });
    });
  });
}

/* --------------------------------------------------------------------------
   Commercial Pricing Checkout Integration
   -------------------------------------------------------------------------- */
async function initiateCheckout(plan) {
  const token = localStorage.getItem('charlie_access_token');
  const user = localStorage.getItem('charlie_auth_user');

  if (!token && !user) {
    sessionStorage.setItem('pending_checkout_plan', plan);
    showToast(`Sign in or create an account to activate ${plan}.`);
    const signinBtn = document.getElementById('btn-header-signin');
    if (signinBtn) signinBtn.click();
    return;
  }

  showToast(`Creating order for ${plan}...`);
  try {
    const res = await fetch('/payment/create-order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ plan })
    });
    const orderData = await res.json();
    if (!orderData.success) {
      showToast(`Order failed: ${orderData.error}`);
      return;
    }

    const order = orderData.data;
    showToast(`Order created: ${order.order_id} (₹${order.amount_inr}). Secure server verification ready.`);
  } catch (e) {
    showToast(`Checkout initiated for ${plan}. Connect to licensing server.`);
  }
}

function initPricingCheckout() {
  const planMap = {
    'plan-basic': 'BASIC',
    'plan-pro': 'PRO',
    'plan-pro-plus': 'PRO_PLUS',
    'plan-annual-pro': 'ANNUAL_PRO'
  };

  Object.entries(planMap).forEach(([id, plan]) => {
    const card = document.getElementById(id);
    if (!card) return;
    const btn = card.querySelector('.btn');
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        initiateCheckout(plan);
      });
    }
  });
}

/* --------------------------------------------------------------------------
   Feature 1: Interactive Live Prompt Playground Logic
   -------------------------------------------------------------------------- */
function initPromptPlayground() {
  const form = document.getElementById('playground-form');
  const input = document.getElementById('playground-input');
  const resultCard = document.getElementById('playground-result');
  const skillBadge = document.getElementById('result-skill-badge');
  const dagDesc = document.getElementById('result-dag-desc');
  const stepsList = document.getElementById('result-steps-list');
  const latencyTag = document.getElementById('playground-latency');
  const presets = document.querySelectorAll('.preset-pill');

  if (!form || !input || !resultCard) return;

  function routePrompt(text) {
    const q = text.toLowerCase();
    let badge = 'Core Desktop Skill';
    let dag = 'TaskGraph: Verify Safety Sandbox → Dispatch Native Worker → Capture Output';
    let steps = [
      'Tokenized natural language intent into structured parameters.',
      'Resolved dependencies in local registry cache.',
      'Local execution completed successfully with 0 cloud leakage.'
    ];

    if (q.includes('video') || q.includes('filmora') || q.includes('short') || q.includes('pause') || q.includes('cut')) {
      badge = 'COM API · Filmora 14 Studio';
      dag = 'DAG: Import Media → Silence Filter (Whisper) → Reframe 9:16 → Dynamic Captions → NVENC 4K Export';
      steps = [
        '[0.05s] Hooked Filmora 14 Studio session via COM interop.',
        '[0.42s] Filtered 15 silent pauses (>400ms threshold).',
        '[1.10s] Synchronized dynamic colored word-level subtitle overlay.',
        '[2.20s] Hardware NVENC GPU batch export rendered to /exports/video.mp4.'
      ];
    } else if (q.includes('code') || q.includes('refactor') || q.includes('sql') || q.includes('audit') || q.includes('jwt') || q.includes('bug')) {
      badge = 'Codebase Copilot · AST Parser';
      dag = 'DAG: AST Parse → Vulnerability Search → Generate Atomic Diff → Run Pytest Suite';
      steps = [
        '[0.04s] Indexed repository AST tree (no cloud upload).',
        '[0.31s] Located target method signature and simulated parameterized patch.',
        '[0.75s] Dry-run verification passed 14 unit test assertions with 0 errors.',
        '[0.95s] Ready to commit or inspect staged changes.'
      ];
    } else if (q.includes('voice') || q.includes('female') || q.includes('male') || q.includes('persona') || q.includes('brief')) {
      badge = 'Neural Speech · Persona Engine';
      dag = 'DAG: Persona Switch → Pitch/Inflection Profile → Synthesize TTS → Stream to Audio Buffer';
      steps = [
        '[0.03s] Voice profile switched instantly without application restart.',
        '[0.08s] Loaded localized acoustic neural weights.',
        '[0.12s] Audio stream active: "Good morning! Standing by for your instructions."'
      ];
    } else if (q.includes('excel') || q.includes('csv') || q.includes('sheet') || q.includes('margin') || q.includes('forecast')) {
      badge = 'Office Automation · OpenPyXL';
      dag = 'DAG: Ingest Raw Sheets → Normalize Missing Rows → Compute Financial Formulas → Draw Chart';
      steps = [
        '[0.06s] Parsed input tabular data in memory buffer.',
        '[0.28s] Injected dynamic formula series & conditional formatting.',
        '[0.55s] Generated interactive burn rate graph into workbook.'
      ];
    }

    resultCard.style.display = 'block';
    if (skillBadge) skillBadge.textContent = badge;
    if (dagDesc) dagDesc.textContent = dag;
    if (stepsList) {
      stepsList.innerHTML = '';
      steps.forEach((s, idx) => {
        const row = document.createElement('div');
        row.className = 'result-step-row';
        row.innerHTML = `<span class="result-step-tag">[Step 0${idx+1}]</span> <span>${s}</span>`;
        stepsList.appendChild(row);
      });
    }

    const mockLatency = (Math.random() * 0.03 + 0.02).toFixed(2);
    if (latencyTag) latencyTag.textContent = `Routing Latency: ${mockLatency}s`;
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (input.value.trim()) {
      routePrompt(input.value.trim());
    }
  });

  presets.forEach(p => {
    p.addEventListener('click', () => {
      const pr = p.getAttribute('data-prompt');
      if (pr) {
        input.value = pr;
        routePrompt(pr);
      }
    });
  });

  // Initial trigger
  routePrompt(input.value);
}

/* --------------------------------------------------------------------------
   Feature 3: Interactive Hardware Performance Calculator Logic
   -------------------------------------------------------------------------- */
function initHardwareCalculator() {
  const ramEl = document.getElementById('calc-ram');
  const gpuEl = document.getElementById('calc-gpu');
  const storageEl = document.getElementById('calc-storage');
  const workloadEl = document.getElementById('calc-workload');

  const resLatency = document.getElementById('calc-res-latency');
  const resLatencySub = document.getElementById('calc-res-latency-sub');
  const resFps = document.getElementById('calc-res-fps');
  const resFpsSub = document.getElementById('calc-res-fps-sub');
  const resRender = document.getElementById('calc-res-render');
  const resRenderSub = document.getElementById('calc-res-render-sub');
  const resTier = document.getElementById('calc-res-tier');
  const resTierSub = document.getElementById('calc-res-tier-sub');

  if (!ramEl || !gpuEl || !resLatency) return;

  function updateEstimates() {
    const ram = parseInt(ramEl.value, 10);
    const gpu = gpuEl.value;
    const storage = storageEl.value;
    const workload = workloadEl.value;

    let latency = 120;
    let fps = 120;
    let renderSec = 5.0;
    let tierText = '100% Native';

    // GPU factors
    if (gpu === 'integrated') {
      fps = 48;
      renderSec = 14.5;
      latency += 35;
    } else if (gpu === 'gtx') {
      fps = 85;
      renderSec = 6.8;
      latency += 10;
    } else if (gpu === 'rtx30') {
      fps = 136;
      renderSec = 3.8;
      latency = 110;
    } else if (gpu === 'rtx40') {
      fps = 240;
      renderSec = 1.9;
      latency = 95;
    } else if (gpu === 'apple') {
      fps = 120;
      renderSec = 3.4;
      latency = 105;
    }

    // RAM factors
    if (ram < 16) {
      latency += 20;
      tierText = 'Hybrid / Lightweight';
    } else if (ram >= 32) {
      tierText = 'Full Local 70B Quantized';
    }

    // Storage factors
    if (storage === 'hdd') {
      renderSec += 4.5;
      latency += 40;
    } else if (storage === 'sata') {
      renderSec += 1.2;
    }

    // Workload adjustments
    if (workload === 'video') {
      resRenderSub.textContent = 'Hardware NVENC 4K export';
    } else if (workload === 'voice') {
      latency = Math.max(80, latency - 15);
      resRenderSub.textContent = 'Voice priority pipeline';
    } else if (workload === 'coding') {
      resRenderSub.textContent = 'Multi-agent AST dry-run';
    } else if (workload === 'offline') {
      tierText = '100% Disconnected Air-Gapped';
    }

    if (resLatency) resLatency.textContent = `${latency} ms`;
    if (resLatencySub) resLatencySub.textContent = latency < 120 ? 'Instant conversational response' : 'Smooth local transcription';

    if (resFps) resFps.textContent = `${fps.toFixed(1)} FPS`;
    if (resFpsSub) resFpsSub.textContent = fps >= 120 ? 'Silky high-refresh HUD' : 'Fluid standard display';

    if (resRender) resRender.textContent = `${renderSec.toFixed(1)} s`;
    if (resTier) resTier.textContent = tierText;
    if (resTierSub) resTierSub.textContent = `${ram}GB RAM · ${gpu.toUpperCase()} hardware accelerated`;
  }

  [ramEl, gpuEl, storageEl, workloadEl].forEach(ctrl => {
    if (ctrl) ctrl.addEventListener('change', updateEstimates);
  });

  updateEstimates();
}





