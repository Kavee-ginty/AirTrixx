const adminPages = [
  "Dashboard",
  "Signals",
  "Keyboard",
  "Wristband",
  "Wrist Cursor",
  "Visualiser",
  "Wrist Rules",
  "Mappings",
  "Testing",
  "Camera & Servo",
  "Gesture Recorder",
  "Auto Mapper",
  "Audio Dock",
  "Firmware",
  "Settings",
  "Data / Logs",
];
const clientPages = ["Dashboard", "Mappings", "Settings"];

const navGroups = {
  admin: [
    { label: "GENERAL", pages: ["Dashboard", "Signals", "Mappings", "Settings"] },
    {
      label: "TOOLS",
      pages: [
        "Keyboard",
        "Wristband",
        "Wrist Cursor",
        "Visualiser",
        "Wrist Rules",
        "Testing",
        "Camera & Servo",
        "Gesture Recorder",
        "Auto Mapper",
        "Audio Dock",
        "Firmware",
      ],
    },
    { label: "SUPPORT", pages: ["Data / Logs"] },
  ],
  client: [{ label: "GENERAL", pages: ["Dashboard", "Mappings", "Settings"] }],
};

const state = {
  data: null,
  activePage: "Dashboard",
  cameraStamp: 0,
  loginError: null,
  sidebarCollapsed: false,
  mappingEditor: null,
  mappingKeyCapture: null,
  mappingImportStatus: "",
};

const MAPPING_COMPARATORS = ["lt", "lte", "gt", "gte", "eq", "neq", "present", "truthy", "falsey", "between"];
const MAPPING_ACTION_TYPES = [
  "keyboard_tap",
  "keyboard_hold",
  "keyboard_text",
  "mouse_click",
  "mouse_hold",
  "mouse_scroll",
];
const MAPPING_MOUSE_BUTTONS = ["left", "right", "middle"];
const MAPPING_KEY_DISPLAY_ALIASES = { "+": "plus", "-": "minus", ",": "comma" };
const MAPPING_KEY_VALUE_ALIASES = { plus: "+", minus: "-", comma: "," };

const THEME_STORAGE_KEY = "airtrixx-theme";
const APP_ICON = "./static/images/airtrixx-icon.svg";

function brandIconMarkup(large = false) {
  const className = large ? "brand-icon brand-icon-lg" : "brand-icon";
  return `<img class="${className}" src="${APP_ICON}" width="36" height="36" alt="AirTrixx" />`;
}

const navIcons = {
  Dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  Signals: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16l3-6 3 4 4-8"/></svg>',
  Keyboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/></svg>',
  Wristband: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2 2"/></svg>',
  "Wrist Cursor": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 4l7 16 2-7 7-2z"/></svg>',
  Visualiser: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16V9M12 16V6M16 16v-4"/></svg>',
  "Wrist Rules": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
  Mappings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  Testing: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
  "Camera & Servo": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
  "Gesture Recorder": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg>',
  "Auto Mapper": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>',
  "Audio Dock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
  Firmware: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>',
  Settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>',
  "Data / Logs": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>',
};

function getStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    /* ignore storage errors */
  }
  return next;
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme || getStoredTheme();
  return applyTheme(current === "dark" ? "light" : "dark");
}

function themeToggleButton() {
  const current = document.documentElement.dataset.theme || getStoredTheme();
  const label = current === "dark" ? "Light mode" : "Dark mode";
  const node = iconButton(label, "btn btn-muted btn-icon-only", () => {
    toggleTheme();
    renderTopbar();
    if (state.data?.auth?.authenticated) {
      if (state.activePage === "Dashboard") pageRoot().dataset.page = "";
      renderPage();
    }
  }, "theme");
  return node;
}

function navIconMarkup(page) {
  const svg = navIcons[page] || '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="4"/></svg>';
  return `<span class="nav-icon" aria-hidden="true">${svg}</span>`;
}

const topbarIcons = {
  camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
  mapper: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  theme: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
  gift: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="8" width="18" height="13" rx="2"/><path d="M12 8V21M3 12h18M12 8c-2-2-4-2-4-4s2-2 4 0 4-2 4 0-2 2-4 0"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M4 12h10M4 17h16"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 10v6M12 7h.01"/></svg>',
};

function iconButton(label, className, onClick, iconKey) {
  const node = el("button", className);
  node.type = "button";
  node.title = label;
  node.setAttribute("aria-label", label);
  node.innerHTML = `<span class="btn-glyph" aria-hidden="true">${topbarIcons[iconKey] || ""}</span>`;
  node.addEventListener("click", onClick);
  return node;
}

function actionButton(label, action, payload = {}, className = "btn btn-muted btn-icon-only", iconKey = "") {
  const node = iconButton(label, className, () => dispatch(action, payload), iconKey);
  return node;
}

function shortPortLabel(port) {
  const device = String(port?.device || port || "");
  const desc = String(port?.description || "").trim();
  if (!device) return "No port";
  const base = device.split("/").pop() || device;
  return desc && desc !== "n/a" ? `${base}` : base;
}

function formatPortOption(port) {
  return shortPortLabel(port);
}

const api = {
  async call(method, ...args) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api[method]) {
      return window.pywebview.api[method](...args);
    }
    return mockApi(method, ...args);
  },
};

function mappingRuleSummaryFromRaw(rule) {
  return {
    id: rule.id,
    enabled: rule.enabled !== false,
    name: rule.name || "Mapping",
    source: rule.source || "",
    condition: rule.comparator || "truthy",
    action: rule.action?.type || "keyboard_tap",
    status: "idle",
    rule,
  };
}

async function mockApi(method, ...args) {
  if (method === "dispatch") {
    const [action, payload] = args;
    if (action === "auth.login") {
      const email = String(payload?.email || payload?.username || "").toLowerCase();
      const password = String(payload?.password || "");
      const username = email.includes("@") ? email.split("@", 1)[0] : email;
      const admin = username === "admin" && password === "admin123";
      const client = username === "client" && password === "client123";
      if (admin || client) {
        mockState.auth = {
          authenticated: true,
          userId: admin ? "mock_admin" : "mock_client",
          email,
          user: admin ? "Admin" : "Client",
          displayName: admin ? "Admin" : "Client",
          role: admin ? "admin" : "client",
          error: "",
          loginHint: mockState.auth.loginHint,
        };
        mockState.cloud = { configured: true, syncStatus: "Preview sync ready", lastSyncedAt: "", error: "" };
        mockState.app.navPages = admin ? adminPages : clientPages;
        mockState.app.activePage = "Dashboard";
      } else {
        mockState.auth.error = "Invalid email or password.";
      }
    }
    if (action === "auth.logout") {
      mockState.auth = { authenticated: false, userId: "", email: "", user: "", role: "", error: "", loginHint: mockState.auth.loginHint };
      mockState.app.navPages = clientPages;
      mockState.app.activePage = "Dashboard";
    }
    if (action === "sync.now") mockState.cloud = { configured: true, syncStatus: "Preview data synced", lastSyncedAt: new Date().toISOString(), error: "" };
    if (action === "nav.set") mockState.app.activePage = payload.page;
    if (action === "mapping.toggle") mockState.mappings.enabled = !mockState.mappings.enabled;
    if (action === "mapping.set_profile") mockState.mappings.activeProfile = payload.profile || mockState.mappings.activeProfile;
    if (action === "mapping.save") mockState.mappings.status = "Saved";
    if (action === "mapping.import_json") {
      try {
        const imported = JSON.parse(payload?.text || "{}");
        if (Number(imported.version) !== 1 || !Array.isArray(imported.profiles)) {
          throw new Error("Selected file is not an AirTrixx mapping JSON file.");
        }
        const profileNames = imported.profiles.map((profile) => profile.name || "Default");
        const activeProfile = profileNames.includes(imported.active_profile) ? imported.active_profile : profileNames[0] || "Default";
        const active = imported.profiles.find((profile) => (profile.name || "Default") === activeProfile) || imported.profiles[0] || {};
        mockState.mappings.activeProfile = activeProfile;
        mockState.mappings.profiles = profileNames.length ? profileNames : ["Default"];
        mockState.mappings.rules = (active.mappings || []).map(mappingRuleSummaryFromRaw);
        mockState.mappings.status = `Imported ${payload?.name || "mapping JSON"}`;
      } catch (error) {
        return { ok: false, error: error.message || String(error) };
      }
    }
    if (action === "mapping.rule.upsert") {
      const rule = payload.rule || {};
      const rules = mockState.mappings.rules || [];
      const index = rules.findIndex((item) => item.id === rule.id);
      const summary = mappingRuleSummaryFromRaw(rule);
      if (index >= 0) rules[index] = summary;
      else rules.push(summary);
      mockState.mappings.rules = rules;
    }
    if (action === "mapping.rule.delete") {
      mockState.mappings.rules = (mockState.mappings.rules || []).filter((item) => item.id !== payload.id);
    }
    if (action === "mapping.rule.toggle") {
      const rule = (mockState.mappings.rules || []).find((item) => item.id === payload.id);
      if (rule) rule.enabled = payload.enabled !== undefined ? Boolean(payload.enabled) : !rule.enabled;
    }
    if (action === "testing.select") {
      mockState.testing.selectedId = payload.id || "";
      mockState.testing.mode = "selected";
      mockState.testing.active = true;
      mockState.testing.status = "Selected test armed.";
      mockState.testing.detected = "Detected: waiting";
      mockState.testing.history.unshift(`[${new Date().toLocaleTimeString()}] Armed selected test.`);
    }
    if (action === "testing.set_mode" || action === "testing.start") {
      mockState.testing.mode = payload.mode === "all" ? "all" : "selected";
      mockState.testing.active = true;
      mockState.testing.status = mockState.testing.mode === "all" ? "All-in-one test armed." : "Selected test armed.";
      mockState.testing.detected = "Detected: waiting";
    }
    if (action === "testing.set_suppress") {
      mockState.testing.outputSuppressed = payload.enabled !== false;
    }
    if (action === "testing.stop") {
      mockState.testing.active = false;
      mockState.testing.status = "Testing stopped.";
      mockState.testing.detected = "Detected: -";
      mockState.testing.history.unshift(`[${new Date().toLocaleTimeString()}] Stopped gesture testing.`);
    }
    if (action === "testing.refresh") {
      mockState.testing.status = "Testing list refreshed.";
    }
    if (action === "camera.toggle_power") mockState.camera.enabled = !mockState.camera.enabled;
    if (action === "serial.connect") mockState.serial.connected = true;
    if (action === "serial.disconnect") mockState.serial.connected = false;
    return { ok: true };
  }
  if (method === "get_camera_frame") return { ok: true, src: null, reason: "Preview unavailable." };
  return JSON.parse(JSON.stringify(mockState));
}

const mockState = {
  app: { name: "AirTrixx", activePage: "Dashboard", navPages: clientPages, userDataDir: "-", runtime: "preview" },
  auth: { authenticated: false, userId: "", email: "", user: "", role: "", error: "", loginHint: "Dummy users: admin/admin123 or client/client123" },
  cloud: { configured: false, syncStatus: "Preview mode", lastSyncedAt: "", error: "" },
  status: [
    { label: "Hub", value: "disconnected", tone: "warn" },
    { label: "Mapper", value: "disabled", tone: "warn" },
    { label: "Camera", value: "no frame", tone: "warn" },
  ],
  serial: { connected: false, connecting: false, port: null, ports: [], sequence: null },
  devices: [
    { key: "wristband", label: "Wristband", status: "ok", detail: "Connected", battery: 82, tone: "ok", image: "components/Wristband.png" },
    { key: "camdock", label: "Cam Dock", status: "ok", detail: "Tracking ready", battery: 64, tone: "ok", image: "components/CamDock.png" },
    { key: "keyboard", label: "Keyboard", status: "warn", detail: "Waiting for Antenna", battery: null, tone: "warn", image: "components/KeyBoardStand.png" },
    { key: "fans", label: "Fans", status: "warn", detail: "Not connected", battery: null, tone: "warn", image: "components/Fans.png" },
    { key: "charging_dock", label: "Charging Dock", status: "ok", detail: "Standby", battery: 91, tone: "ok", image: "components/Charging.png" },
    { key: "audiodock", label: "Audio Dock", status: "ok", detail: "Idle", battery: 73, tone: "ok", image: "components/AudioDock3D.png" },
  ],
  analytics: {
    batteryLevels: [
      { key: "wristband", label: "Wristband", value: 82 },
      { key: "camdock", label: "Cam Dock", value: 64 },
      { key: "charging_dock", label: "Charging Dock", value: 91 },
      { key: "audiodock", label: "Audio Dock", value: 73 },
    ],
    temperatures: { temp1: 28.4, temp2: 31.1 },
    signalGroups: [
      { group: "Wristband", count: 18 },
      { group: "Keyboard", count: 12 },
      { group: "Fans", count: 6 },
    ],
    mapping: { total: 1, enabled: 0, armed: false },
    timeline: Array.from({ length: 24 }, (_, index) => ({
      hub: index % 4 === 0 ? 0 : 1,
      mapper: index % 5 === 0 ? 1 : 0,
      camera: index % 3 === 0 ? 0 : 1,
      temp1: 26 + (index % 6),
      temp2: 28 + (index % 5),
    })),
  },
  camera: { enabled: true, mirror: false, hasFrame: false, autoTracking: true, face: {} },
  fans: { status: "not_connected", fanOn: null, requestedOn: false, temp1: null, temp2: null, battery: null },
  keyboard: {
    status: "Waiting for Antenna",
    predicted_word: null,
    prediction_confidence: 0,
    model_loaded: false,
    model_words: [],
    training_status: "Idle",
    live_prediction_enabled: true,
    tof: {},
    valid: {},
  },
  mappings: {
    enabled: false,
    status: "Waiting for antenna hub",
    activeProfile: "Default",
    profiles: ["Default", "Gaming", "Presentation"],
    sources: ["keyboard.input", "wristband.gesture", "wristband.button", "keyboard.prediction"],
    rules: [
      {
        id: "wrist-click",
        enabled: true,
        name: "Wrist click",
        source: "wristband.gesture",
        condition: "present",
        action: "tap space",
        status: "idle",
        rule: {
          id: "wrist-click",
          name: "Wrist click",
          enabled: true,
          source: "wristband.gesture",
          comparator: "present",
          threshold: true,
          action: { type: "keyboard_tap", keys: ["space"], button: "left" },
        },
      },
      {
        id: "keyboard-enter",
        enabled: true,
        name: "Keyboard enter",
        source: "keyboard.input",
        condition: "truthy",
        action: "tap enter",
        status: "waiting",
        rule: {
          id: "keyboard-enter",
          name: "Keyboard enter",
          enabled: true,
          source: "keyboard.input",
          comparator: "truthy",
          threshold: true,
          action: { type: "keyboard_tap", keys: ["enter"], button: "left" },
        },
      },
    ],
  },
  testing: {
    active: false,
    mode: "selected",
    outputSuppressed: true,
    selectedId: "raw:right_open_palm",
    selectedName: "Right hand open palm",
    status: "Select a gesture to arm an individual test.",
    detected: "Detected: -",
    entries: [
      {
        id: "raw:right_open_palm",
        name: "Right hand open palm",
        type: "Camera",
        trigger: "hands.right.gesture eq open_palm",
        status: "-",
      },
      {
        id: "raw:right_fist",
        name: "Right hand fist",
        type: "Camera",
        trigger: "hands.right.gesture eq closed_fist",
        status: "-",
      },
      {
        id: "mapping:wrist-click",
        name: "Wrist click",
        type: "Mapping",
        trigger: "wristband.gesture present -> tap space",
        status: "-",
      },
    ],
    liveValues: [
      { label: "L gesture", value: "none" },
      { label: "R gesture", value: "none" },
      { label: "L z", value: "- mm" },
      { label: "R z", value: "- mm" },
      { label: "Model", value: "none" },
    ],
    history: [],
  },
  signals: [
    { id: "wristband.gesture", group: "Wristband", label: "Gesture", value: "none" },
    { id: "wristband.button", group: "Wristband", label: "Button", value: "0" },
    { id: "keyboard.input", group: "Keyboard", label: "Input", value: "hello" },
    { id: "keyboard.prediction", group: "Keyboard", label: "Prediction", value: "0.82" },
  ],
  raw: { serial: "{}", snapshot: "{}", servo: "{}" },
  logs: [],
};

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function navGroupConfig() {
  const pages = state.data?.app?.navPages || clientPages;
  const role = state.data?.auth?.role === "admin" ? "admin" : "client";
  const groups = navGroups[role] || navGroups.client;
  return groups
    .map((group) => ({
      label: group.label,
      pages: group.pages.filter((page) => pages.includes(page)),
    }))
    .filter((group) => group.pages.length);
}

function shellMarkup() {
  const collapsed = state.sidebarCollapsed ? "is-collapsed" : "";
  return `
    <aside class="sidebar ${collapsed}">
      <div class="sidebar-head">
        <div class="brand">
          ${brandIconMarkup()}
          <h1>AirTrixx</h1>
        </div>
        <button id="sidebar-toggle" class="sidebar-toggle" type="button" title="Toggle sidebar" aria-label="Toggle sidebar">
          ${topbarIcons.menu}
        </button>
      </div>
      <nav id="nav" class="nav-list"></nav>
      <div class="sidebar-footer">
        <details class="serial-panel" id="serial-panel">
          <summary class="serial-summary">
            <span class="serial-dot" id="serial-dot"></span>
            <span class="serial-summary-text">
              <span class="serial-summary-label">Antenna Hub</span>
              <span class="serial-summary-value" id="serial-summary-value">Not connected</span>
            </span>
          </summary>
          <div class="serial-body">
            <label for="serial-port">Port</label>
            <select id="serial-port"></select>
            <div class="serial-actions">
              <button data-action="serial.refresh" class="btn btn-muted btn-icon-only" title="Refresh ports" aria-label="Refresh ports">
                <span class="btn-glyph" aria-hidden="true">${topbarIcons.refresh}</span>
              </button>
              <button id="serial-connect" class="btn btn-primary serial-connect-btn">Connect</button>
            </div>
          </div>
        </details>
        <button id="serial-quick-connect" class="btn btn-outline btn-outline-block" type="button">Connect Hub</button>
        <p class="sidebar-copy">© ${new Date().getFullYear()} AirTrixx</p>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <label class="search-bar">
          <span class="search-icon" aria-hidden="true">${topbarIcons.search}</span>
          <input type="search" placeholder="Search" aria-label="Search">
          <span class="search-kbd">⌘ + F</span>
        </label>
        <div class="topbar-actions"></div>
      </header>
      <section id="page" class="page"><div class="page-inner"></div></section>
    </main>
  `;
}

function ensureShell() {
  const app = document.querySelector("#app");
  const needsRebuild =
    !app.classList.contains("app-shell") || !document.querySelector("#page .page-inner") || !document.querySelector(".search-bar");
  if (needsRebuild) {
    app.className = "app-shell";
    app.innerHTML = shellMarkup();
    document.querySelector("#sidebar-toggle")?.addEventListener("click", () => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
      document.querySelector(".sidebar")?.classList.toggle("is-collapsed", state.sidebarCollapsed);
    });
    document.querySelector("#serial-quick-connect")?.addEventListener("click", () => {
      const panel = document.querySelector("#serial-panel");
      if (panel) panel.open = true;
      document.querySelector("#serial-connect")?.click();
    });
  } else {
    document.querySelector(".sidebar")?.classList.toggle("is-collapsed", state.sidebarCollapsed);
  }
}

function pageRoot() {
  return document.querySelector("#page .page-inner") || document.querySelector("#page");
}

function renderLogin() {
  const app = document.querySelector("#app");
  const auth = state.data?.auth || {};
  app.className = "login-shell";
  app.innerHTML = "";
  const panel = el("form", "login-panel");
  panel.innerHTML = `
    <div class="brand login-brand">
      ${brandIconMarkup(true)}
      <div>
        <h1>AirTrixx</h1>
      </div>
    </div>
    <div class="field">
      <label>Username</label>
      <input id="login-email" autocomplete="username" value="admin">
    </div>
    <div class="field">
      <label>Password</label>
      <input id="login-pass" type="password" autocomplete="current-password" value="admin123">
    </div>
    <p class="login-error">${escapeText(auth.error || "")}</p>
    <p class="muted">${escapeText(auth.loginHint || "Dummy users: admin/admin123 or client/client123")}</p>
    <button class="btn btn-primary" type="submit">Sign In</button>
  `;
  panel.addEventListener("submit", async (event) => {
    event.preventDefault();
    await dispatch("auth.login", {
      email: document.querySelector("#login-email")?.value || "",
      password: document.querySelector("#login-pass")?.value || "",
    });
  });
  app.append(panel);
}

function pageHeader(title, subtitle = "", actions = []) {
  const header = el("div", "page-header");
  const titleBox = el("div", "page-title");
  titleBox.append(el("h1", "", title));
  if (subtitle) titleBox.append(el("p", "page-subtitle", subtitle));
  const toolbar = el("div", "page-toolbar");
  actions.forEach((action) => toolbar.append(action));
  header.append(titleBox, toolbar);
  return header;
}

function toolbarButton(label, action, payload = {}, className = "btn btn-outline") {
  return button(label, action, payload, className);
}

function button(label, action, payload = {}, className = "btn btn-muted") {
  const node = el("button", className, label);
  node.addEventListener("click", () => dispatch(action, payload));
  return node;
}

function card(title, body, tone = "", extraClass = "") {
  const node = el("article", `card ${tone} ${extraClass}`.trim());
  const header = el("div", "card-header");
  header.append(el("h3", "", title));
  node.append(header, body);
  if (body?.classList?.contains("table-wrap") || body?.querySelector?.(".table-wrap")) {
    node.classList.add("has-table");
  }
  if (body?.classList?.contains("code") || body?.classList?.contains("log-list")) {
    node.classList.add("has-bleed-body");
  }
  return node;
}

function table(headers, rows) {
  const wrap = el("div", "table-wrap");
  const tableNode = el("table");
  const thead = el("thead");
  const tr = el("tr");
  headers.forEach((header) => tr.append(el("th", "", header)));
  thead.append(tr);
  const tbody = el("tbody");
  rows.forEach((row) => {
    const rowNode = el("tr");
    row.forEach((cell) => {
      const td = el("td");
      if (cell instanceof Node) td.append(cell);
      else td.textContent = formatDisplayValue(cell);
      rowNode.append(td);
    });
    tbody.append(rowNode);
  });
  tableNode.append(thead, tbody);
  wrap.append(tableNode);
  return wrap;
}

function formatDisplayValue(input) {
  if (input === null || input === undefined || input === "") return "-";
  if (typeof input === "number") return Number.isInteger(input) ? String(input) : input.toFixed(3);
  if (typeof input === "boolean") return input ? "true" : "false";
  return String(input);
}

function statusPill(label, tone = "warn") {
  return el("span", `status-pill tone-${tone}`, label);
}

function renderNav() {
  ensureShell();
  const nav = document.querySelector("#nav");
  nav.replaceChildren();
  navGroupConfig().forEach((group) => {
    const wrap = el("div", "nav-group");
    wrap.append(el("div", "nav-section-label", group.label));
    group.pages.forEach((page) => {
      const item = el("button", `nav-item ${page === state.activePage ? "active" : ""}`);
      item.title = page;
      item.setAttribute("aria-label", page);
      item.innerHTML = `${navIconMarkup(page)}<span class="nav-label">${escapeText(page)}</span>`;
      item.addEventListener("click", () => dispatch("nav.set", { page }));
      wrap.append(item);
    });
    nav.append(wrap);
  });
}

function renderSerial() {
  ensureShell();
  const data = state.data;
  const select = document.querySelector("#serial-port");
  const selected = select?.value;
  if (!select) return;
  select.replaceChildren();
  const ports = data?.serial?.ports || [];
  if (!ports.length) {
    const empty = el("option", "", "No ports found");
    empty.value = "";
    select.append(empty);
  }
  ports.forEach((port) => {
    const option = el("option", "", formatPortOption(port));
    option.value = port.device;
    option.title = `${port.device}${port.description ? ` — ${port.description}` : ""}`;
    select.append(option);
  });
  if (selected) select.value = selected;
  else if (ports[0]) select.value = ports[0].device;

  const connected = Boolean(data?.serial?.connected);
  const connecting = Boolean(data?.serial?.connecting);
  const connect = document.querySelector("#serial-connect");
  if (connect) {
    connect.textContent = connecting ? "Connecting..." : connected ? "Disconnect" : "Connect";
    connect.classList.toggle("btn-danger", connected);
    connect.classList.toggle("btn-primary", !connected);
    connect.onclick = () => {
      if (connected) dispatch("serial.disconnect");
      else dispatch("serial.connect", { port: select.value || null });
    };
  }

  const summaryValue = document.querySelector("#serial-summary-value");
  if (summaryValue) {
    const activePort = data?.serial?.port || select.value;
    if (connected) summaryValue.textContent = shortPortLabel({ device: activePort });
    else if (activePort) summaryValue.textContent = shortPortLabel({ device: activePort });
    else summaryValue.textContent = ports.length ? "Select port" : "No ports";
  }

  const dot = document.querySelector("#serial-dot");
  if (dot) {
    dot.className = `serial-dot ${connected ? "is-connected" : connecting ? "is-connecting" : ""}`;
  }
}

function renderTopbar() {
  ensureShell();
  const auth = state.data?.auth || {};
  const actions = document.querySelector(".topbar-actions");
  actions.replaceChildren();

  const makeIcon = (label, iconKey, onClick, options = {}) => {
    const node = el("button", `topbar-icon-btn ${options.active ? "is-on" : ""}`.trim());
    node.type = "button";
    node.title = label;
    node.setAttribute("aria-label", label);
    if (options.pressed !== undefined) node.setAttribute("aria-pressed", options.pressed ? "true" : "false");
    node.innerHTML = topbarIcons[iconKey] || "";
    node.addEventListener("click", onClick);
    return node;
  };

  const mappings = state.data?.mappings || {};
  actions.append(
    makeIcon("Offers", "gift", () => {}),
    makeIcon("Notifications", "bell", () => {}),
    makeIcon("Quick actions", "plus", () => {}),
    makeIcon("Toggle theme", "theme", () => {
      toggleTheme();
      renderTopbar();
      if (state.data?.auth?.authenticated) {
        if (state.activePage === "Dashboard") pageRoot().dataset.page = "";
        renderPage();
      }
    }),
    makeIcon("Camera", "camera", () => dispatch("camera.toggle_power")),
    makeIcon(
      mappings.enabled ? "Mapper armed" : "Mapper disabled",
      "mapper",
      () => dispatch("mapping.toggle"),
      { active: Boolean(mappings.enabled), pressed: Boolean(mappings.enabled) },
    ),
  );

  const user = el("div", "user-chip");
  const meta = el("div", "user-meta-wrap");
  meta.append(el("span", "user-name", auth.user || "Guest"), el("span", "user-role", `${formatDisplayValue(auth.role || "guest")} panel`));
  user.append(el("span", "user-avatar", (auth.user || "?").slice(0, 1).toUpperCase()), meta);
  user.addEventListener("click", () => dispatch("auth.logout"));
  user.style.cursor = "pointer";
  user.title = "Logout";
  actions.append(user);
}

function statusStrip(items) {
  const strip = el("div", "status-strip");
  items.forEach((item, index) => {
    const row = el("div", `status-strip-item tone-${item.tone || "warn"}`);
    row.append(
      el("span", "status-strip-dot"),
      el("span", "status-strip-label", item.label),
      el("span", "status-strip-value", formatDisplayValue(item.value)),
    );
    strip.append(row);
    if (index < items.length - 1) strip.append(el("span", "status-strip-divider"));
  });
  return strip;
}

function componentImageSrc(device) {
  if (device?.image) return `./static/images/${device.image}`;
  return "";
}

const batteryGlyph = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 10v4"/></svg>';

function batteryMeter(rawBattery) {
  const hasReading = rawBattery !== null && rawBattery !== undefined && Number.isFinite(Number(rawBattery));
  const level = hasReading ? Math.max(0, Math.min(100, Math.round(Number(rawBattery)))) : null;
  const tone = level === null ? "none" : level >= 50 ? "ok" : level >= 20 ? "warn" : "danger";
  const meter = el("div", `component-card-battery-meter tone-${tone}`);
  const top = el("div", "component-card-battery-top");
  const label = el("span", "component-card-battery-label");
  label.innerHTML = `<span class="component-card-battery-glyph" aria-hidden="true">${batteryGlyph}</span>Battery`;
  top.append(label);
  top.append(el("span", "component-card-battery-value", level === null ? "N/A" : `${level}%`));
  meter.append(top);
  const bar = el("div", "component-card-battery");
  const fill = el("span");
  fill.style.width = `${level === null ? 0 : level}%`;
  bar.append(fill);
  meter.append(bar);
  return meter;
}

function componentGrid(devices) {
  const grid = el("div", "component-grid");
  devices
    .filter((device) => device.image)
    .forEach((device) => {
      const card = el("article", "component-card");
      const head = el("div", "component-card-head");
      const thumb = el("div", "component-card-thumb");
      const img = el("img");
      img.src = componentImageSrc(device);
      img.alt = device.label;
      thumb.append(img);
      head.append(thumb);
      const meta = el("div", "component-card-meta");
      meta.append(el("h3", "component-card-title", device.label));
      meta.append(el("span", `component-card-status tone-${device.tone || "warn"}`, device.status || "-"));
      head.append(meta);
      card.append(head);
      card.append(el("p", "component-card-detail", device.detail || "-"));
      card.append(batteryMeter(device.battery));
      grid.append(card);
    });
  return grid;
}

let dashboardCharts = {
  activity: null,
  temperature: null,
  signals: null,
};

function initChartDefaults() {
  if (typeof Chart === "undefined" || Chart.__airtrixxConfigured) return;
  Chart.defaults.animation = false;
  Chart.defaults.animations = false;
  Chart.defaults.responsiveAnimationDuration = 0;
  Chart.__airtrixxConfigured = true;
}

function destroyDashboardCharts() {
  Object.keys(dashboardCharts).forEach((key) => {
    dashboardCharts[key]?.destroy();
    dashboardCharts[key] = null;
  });
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartPalette() {
  return {
    accent: cssVar("--accent") || "#16a34a",
    accentSoft: cssVar("--accent-soft") || "rgba(22, 163, 74, 0.12)",
    muted: cssVar("--muted") || "#737373",
    line: cssVar("--line") || "#e5e5e5",
    text: cssVar("--text-secondary") || "#525252",
    textMain: cssVar("--text") || "#171717",
    panel: cssVar("--panel") || "#ffffff",
  };
}

function chartBaseOptions() {
  const colors = chartPalette();
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    animations: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 8,
          boxHeight: 8,
          usePointStyle: true,
          color: colors.text,
          padding: 12,
          font: { size: 11, weight: "600" },
        },
      },
      tooltip: {
        backgroundColor: colors.textMain,
        titleColor: colors.panel,
        bodyColor: colors.panel,
        padding: 10,
        cornerRadius: 8,
        displayColors: true,
      },
    },
  };
}

function analyticsPanel(title, bodyNode, extraClass = "") {
  const panel = el("div", `analytics-panel ${extraClass}`.trim());
  panel.append(el("h3", "analytics-title", title), bodyNode);
  return panel;
}

function chartCanvasWrap(className = "", chartKey = "") {
  const wrap = el("div", `chart-canvas-wrap ${className}`.trim());
  const canvas = el("canvas");
  if (chartKey) canvas.dataset.chart = chartKey;
  wrap.append(canvas);
  return { wrap, canvas };
}

function timelineLabels(timeline) {
  const len = timeline.length;
  if (!len) return [];
  return timeline.map((_, index) => {
    if (index === 0) return "Start";
    if (index === len - 1) return "Now";
    return "";
  });
}

function activityLane(timeline, key, level) {
  return timeline.map((sample) => (Number(sample?.[key]) > 0 ? level : 0.05));
}

function activityChartData(timeline) {
  return {
    labels: timelineLabels(timeline),
    datasets: [
      {
        label: "Hub",
        data: activityLane(timeline, "hub", 3),
        stepped: true,
        tension: 0,
        borderColor: chartPalette().accent,
        backgroundColor: chartPalette().accentSoft,
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: "Mapper",
        data: activityLane(timeline, "mapper", 2),
        stepped: true,
        tension: 0,
        borderColor: chartPalette().muted,
        backgroundColor: "transparent",
        fill: false,
        borderWidth: 2,
        borderDash: [5, 4],
        pointRadius: 0,
      },
      {
        label: "Camera",
        data: activityLane(timeline, "camera", 1),
        stepped: true,
        tension: 0,
        borderColor: chartPalette().textMain,
        backgroundColor: "transparent",
        fill: false,
        borderWidth: 2,
        pointRadius: 0,
      },
    ],
  };
}

function activityChartOptions() {
  const colors = chartPalette();
  return {
    ...chartBaseOptions(),
    interaction: { mode: "index", intersect: false },
    scales: {
      x: {
        border: { display: false },
        grid: { display: false },
        ticks: { color: colors.text, maxTicksLimit: 3, font: { size: 10, weight: "600" } },
      },
      y: {
        min: 0,
        max: 3.35,
        border: { display: false },
        ticks: {
          stepSize: 1,
          color: colors.text,
          font: { size: 11, weight: "600" },
          callback: (value) => (value === 3 ? "Hub" : value === 2 ? "Mapper" : value === 1 ? "Camera" : ""),
        },
        grid: { color: colors.line, drawBorder: false },
      },
    },
  };
}

function updateActivityChart(timeline) {
  const chart = dashboardCharts.activity;
  if (!chart || !timeline.length) return;
  chart.data.labels = timelineLabels(timeline);
  chart.data.datasets[0].data = activityLane(timeline, "hub", 3);
  chart.data.datasets[1].data = activityLane(timeline, "mapper", 2);
  chart.data.datasets[2].data = activityLane(timeline, "camera", 1);
  chart.update("none");
}

function mountActivityChart(canvas, timeline) {
  initChartDefaults();
  if (typeof Chart === "undefined" || !timeline.length) return null;
  if (dashboardCharts.activity) {
    updateActivityChart(timeline);
    return dashboardCharts.activity;
  }
  dashboardCharts.activity = new Chart(canvas, {
    type: "line",
    data: activityChartData(timeline),
    options: activityChartOptions(),
  });
  return dashboardCharts.activity;
}

function temperatureChartData(temperatures) {
  const values = [
    typeof temperatures?.temp1 === "number" ? temperatures.temp1 : 0,
    typeof temperatures?.temp2 === "number" ? temperatures.temp2 : 0,
  ];
  const colors = chartPalette();
  return {
    labels: ["Sensor 1", "Sensor 2"],
    datasets: [
      {
        label: "°C",
        data: values,
        backgroundColor: [colors.accent, colors.muted],
        borderRadius: 6,
        borderSkipped: false,
        barThickness: 18,
      },
    ],
  };
}

function temperatureChartOptions() {
  const colors = chartPalette();
  return {
    ...chartBaseOptions(),
    indexAxis: "y",
    plugins: {
      ...chartBaseOptions().plugins,
      legend: { display: false },
      tooltip: {
        ...chartBaseOptions().plugins.tooltip,
        callbacks: {
          label: (ctx) => `${ctx.label}: ${ctx.parsed.x}°C`,
        },
      },
    },
    scales: {
      x: {
        beginAtZero: true,
        suggestedMax: 45,
        border: { display: false },
        grid: { color: colors.line, drawBorder: false },
        ticks: { color: colors.text, font: { size: 11 }, callback: (value) => `${value}°` },
      },
      y: {
        border: { display: false },
        grid: { display: false },
        ticks: { color: colors.text, font: { size: 11, weight: "600" } },
      },
    },
  };
}

function updateTemperatureChart(temperatures) {
  const chart = dashboardCharts.temperature;
  if (!chart) return;
  chart.data.datasets[0].data = temperatureChartData(temperatures).datasets[0].data;
  chart.update("none");
}

function mountTemperatureChart(canvas, temperatures) {
  initChartDefaults();
  if (typeof Chart === "undefined") return null;
  if (dashboardCharts.temperature) {
    updateTemperatureChart(temperatures);
    return dashboardCharts.temperature;
  }
  dashboardCharts.temperature = new Chart(canvas, {
    type: "bar",
    data: temperatureChartData(temperatures),
    options: temperatureChartOptions(),
  });
  return dashboardCharts.temperature;
}

function signalChartData(groups) {
  const colors = chartPalette();
  const palette = [colors.accent, colors.muted, colors.textMain, colors.line, "#525252"];
  return {
    labels: groups.map((group) => group.group),
    datasets: [
      {
        data: groups.map((group) => group.count || 0),
        backgroundColor: groups.map((_, index) => palette[index % palette.length]),
        borderWidth: 0,
        hoverOffset: 4,
      },
    ],
  };
}

function signalChartOptions() {
  return {
    ...chartBaseOptions(),
    cutout: "72%",
    plugins: {
      ...chartBaseOptions().plugins,
      legend: {
        ...chartBaseOptions().plugins.legend,
        position: "bottom",
      },
    },
  };
}

function updateSignalChart(groups) {
  const chart = dashboardCharts.signals;
  if (!chart) return;
  const next = signalChartData(groups);
  chart.data.labels = next.labels;
  chart.data.datasets[0].data = next.datasets[0].data;
  chart.data.datasets[0].backgroundColor = next.datasets[0].backgroundColor;
  chart.update("none");
}

function mountSignalChart(canvas, groups) {
  initChartDefaults();
  if (typeof Chart === "undefined" || !groups.length) return null;
  if (dashboardCharts.signals) {
    updateSignalChart(groups);
    return dashboardCharts.signals;
  }
  dashboardCharts.signals = new Chart(canvas, {
    type: "doughnut",
    data: signalChartData(groups),
    options: signalChartOptions(),
  });
  return dashboardCharts.signals;
}

function mappingStatsBody(mapping) {
  const body = el("div", "mapping-stats");
  body.dataset.panel = "mapping";
  [
    ["Rules", mapping?.total ?? 0],
    ["Enabled", mapping?.enabled ?? 0],
    ["Mapper", mapping?.armed ? "Armed" : "Idle"],
  ].forEach(([label, value]) => {
    const item = el("div", "mapping-stat");
    item.append(el("span", "mapping-stat-label", label), el("strong", "mapping-stat-value", formatDisplayValue(value)));
    body.append(item);
  });
  return body;
}

function mappingStatsPanel(mapping) {
  return analyticsPanel("Mapping overview", mappingStatsBody(mapping), "analytics-panel-stats");
}

function fillAnalyticsSection(slot, isAdmin, analytics) {
  const timeline = analytics?.timeline || [];
  const hasTimeline = timeline.length > 0;
  const hasTemp =
    analytics?.temperatures &&
    (analytics.temperatures.temp1 != null || analytics.temperatures.temp2 != null);
  const hasSignals = (analytics?.signalGroups || []).length > 0;
  const hasMapping = isAdmin && analytics?.mapping;
  if (!hasTimeline && !hasTemp && !hasSignals && !hasMapping) return;

  const section = el("section", "dashboard-section analytics-section");
  section.append(el("h2", "section-title", "Analytics"));
  const grid = el("div", isAdmin ? "analytics-grid analytics-grid-admin" : "analytics-grid analytics-grid-client");

  if (hasTimeline) {
    const { wrap, canvas } = chartCanvasWrap(isAdmin ? "" : "chart-canvas-wide", "activity");
    grid.append(analyticsPanel("System activity", wrap, "analytics-panel-activity"));
    requestAnimationFrame(() => mountActivityChart(canvas, timeline));
  }

  if (isAdmin) {
    if (hasTemp) {
      const { wrap, canvas } = chartCanvasWrap("", "temperature");
      grid.append(analyticsPanel("Fan temperature", wrap, "analytics-panel-temperature"));
      requestAnimationFrame(() => mountTemperatureChart(canvas, analytics.temperatures));
    }
    if (hasSignals) {
      const { wrap, canvas } = chartCanvasWrap("chart-canvas-square", "signals");
      grid.append(analyticsPanel("Signal groups", wrap, "analytics-panel-signals"));
      requestAnimationFrame(() => mountSignalChart(canvas, analytics.signalGroups));
    }
    if (hasMapping) {
      grid.append(mappingStatsPanel(analytics.mapping));
    }
  }

  section.append(grid);
  slot.append(section);
}

function updateMappingStats(mapping) {
  const mappingBody = document.querySelector('[data-panel="mapping"]');
  if (!mappingBody || !mapping) return;
  mappingBody.replaceChildren();
  [
    ["Rules", mapping?.total ?? 0],
    ["Enabled", mapping?.enabled ?? 0],
    ["Mapper", mapping?.armed ? "Armed" : "Idle"],
  ].forEach(([label, value]) => {
    const item = el("div", "mapping-stat");
    item.append(el("span", "mapping-stat-label", label), el("strong", "mapping-stat-value", formatDisplayValue(value)));
    mappingBody.append(item);
  });
}

function updateAnalyticsCharts(analytics, isAdmin) {
  const timeline = analytics?.timeline || [];
  if (timeline.length) updateActivityChart(timeline);
  if (!isAdmin) return;
  if (analytics?.temperatures) updateTemperatureChart(analytics.temperatures);
  if (analytics?.signalGroups?.length) updateSignalChart(analytics.signalGroups);
  updateMappingStats(analytics.mapping);
}

function updateDashboardContent(root, { rebuildAnalytics = false } = {}) {
  const isAdmin = state.data?.auth?.role === "admin";
  const analytics = state.data?.analytics || {};
  const status = state.data?.status || [];
  const devices = state.data?.devices || [];

  const statusSlot = root.querySelector("#dashboard-status");
  if (statusSlot) {
    statusSlot.replaceChildren();
    if (status.length) statusSlot.append(statusStrip(status));
  }

  const analyticsSlot = root.querySelector("#dashboard-analytics");
  if (analyticsSlot) {
    const roleChanged = root.dataset.admin !== (isAdmin ? "1" : "0");
    root.dataset.admin = isAdmin ? "1" : "0";
    const chartsReady =
      analyticsSlot.querySelector(".analytics-section") &&
      (!analytics.timeline?.length || dashboardCharts.activity) &&
      (!isAdmin ||
        ((!analytics.temperatures || analytics.temperatures.temp1 == null && analytics.temperatures.temp2 == null) ||
          dashboardCharts.temperature) &&
        (!(analytics.signalGroups || []).length || dashboardCharts.signals));
    const canUpdate = !rebuildAnalytics && !roleChanged && chartsReady;
    if (canUpdate) {
      updateAnalyticsCharts(analytics, isAdmin);
    } else {
      destroyDashboardCharts();
      analyticsSlot.replaceChildren();
      fillAnalyticsSection(analyticsSlot, isAdmin, analytics);
    }
  }

  const componentsSlot = root.querySelector("#dashboard-components");
  if (componentsSlot) {
    componentsSlot.replaceChildren();
    const illustrated = devices.filter((device) => device.image);
    if (illustrated.length) {
      const section = el("section", "dashboard-section");
      section.append(el("h2", "section-title", "Components"));
      section.append(componentGrid(devices));
      componentsSlot.append(section);
    } else if (!status.length) {
      componentsSlot.append(el("div", "empty", "No data yet."));
    }
  }
}

function renderDashboard(root) {
  destroyDashboardCharts();
  root.dataset.page = "Dashboard";
  root.replaceChildren();
  root.append(
    pageHeader("Dashboard", "", [
      toolbarButton("Toggle Fans", "fans.toggle", {}, "btn btn-primary"),
      toolbarButton("Center Camera", "camera.center"),
      toolbarButton("Tracking", "tracking.toggle"),
    ]),
  );
  const isAdmin = state.data?.auth?.role === "admin";
  const statusSlot = el("div");
  statusSlot.id = "dashboard-status";
  const analyticsSlot = el("div");
  analyticsSlot.id = "dashboard-analytics";
  const componentsSlot = el("div");
  componentsSlot.id = "dashboard-components";
  if (isAdmin) {
    root.append(statusSlot, analyticsSlot, componentsSlot);
  } else {
    root.append(statusSlot, componentsSlot, analyticsSlot);
  }
  updateDashboardContent(root, { rebuildAnalytics: true });
}

function updateDashboard(root) {
  updateDashboardContent(root, { rebuildAnalytics: false });
}

function renderSignals(root) {
  root.append(pageHeader("Live Data", "", []));
  const rows = (state.data?.signals || []).map((signal) => [signal.group, signal.label, signal.id, signal.value]);
  const section = el("section", "page-table");
  section.append(table(["Group", "Signal", "ID", "Value"], rows));
  root.append(section);
}

function renderKeyboard(root) {
  const keyboard = state.data?.keyboard || {};
  root.append(
    pageHeader("Keyboard", "", [
      toolbarButton(keyboard.live_prediction_enabled ? "Live Off" : "Live On", "keyboard.toggle_live"),
      toolbarButton("Calibrate", "keyboard.calibrate"),
    ]),
  );
  const status = el("div", "grid three page-metrics");
  status.append(metricCard("Latest Word", keyboard.predicted_word || "-"));
  status.append(metricCard("Confidence", keyboard.prediction_confidence ? keyboard.prediction_confidence.toFixed(2) : "-"));
  status.append(metricCard("Model", keyboard.model_loaded ? `${(keyboard.model_words || []).length} words` : "Not loaded"));
  root.append(status);

  const form = el("article", "card training-card");
  form.append(el("div", "card-header").append(el("h3", "", "Word Training")));
  const body = el("div", "card-body");
  const grid = el("div", "form-grid");
  grid.innerHTML = `
    <div class="field"><label for="keyboard-words">Words</label><input id="keyboard-words" value="${escapeAttr((keyboard.model_words || ["hello", "world"]).slice(0, 8).join(", "))}"></div>
    <div class="field"><label for="keyboard-reps">Samples / word</label><input id="keyboard-reps" value="3"></div>
    <div class="field"><label for="keyboard-seconds">Timer seconds</label><input id="keyboard-seconds" value="3"></div>
    <div class="field"><label for="keyboard-reset">Options</label><select id="keyboard-reset"><option value="false">Append dataset</option><option value="true">Replace dataset</option></select></div>
  `;
  body.append(grid);
  const actions = el("div", "actions form-actions");
  const startPlan = el("button", "btn btn-primary", "Start Plan");
  startPlan.addEventListener("click", () => dispatch("keyboard.start_training", keyboardPayload()));
  const startTimer = el("button", "btn btn-muted", "Start Timer");
  startTimer.addEventListener("click", () => dispatch("keyboard.start_timer", keyboardPayload()));
  actions.append(
    startPlan,
    button("Record Next", "keyboard.record_next"),
    startTimer,
    button("Train Model", "keyboard.train_model"),
    button("Cancel", "keyboard.cancel_training", {}, "btn btn-danger"),
  );
  body.append(actions, el("p", "training-status muted", keyboard.training_status || "Idle"));
  form.append(body);
  root.append(form);

  const tofRows = Object.keys(keyboard.tof || {}).map((key) => [key, keyboard.tof[key], keyboard.valid?.[key.replace("_mm", "")]]);
  root.append(card("ToF Lanes", table(["Sensor", "Distance mm", "Valid"], tofRows)));
}

function mappingRuleId() {
  return `rule-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function displayMappingKeyToken(token) {
  const value = String(token || "").trim();
  return MAPPING_KEY_DISPLAY_ALIASES[value] || value;
}

function valueMappingKeyToken(token) {
  const value = String(token || "").trim().toLowerCase();
  return MAPPING_KEY_VALUE_ALIASES[value] || value;
}

function keysToText(keys) {
  return Array.isArray(keys) ? keys.filter(Boolean).map(displayMappingKeyToken).join(" + ") : "";
}

function keysFromText(text) {
  return String(text || "")
    .split(/[+,\s]+/)
    .map((part) => valueMappingKeyToken(part))
    .filter(Boolean);
}

function isMappingModifierToken(token) {
  return ["cmd", "ctrl", "alt", "shift"].includes(token);
}

function mappingModifierTokens(event) {
  const tokens = [];
  if (event.metaKey) tokens.push("cmd");
  if (event.ctrlKey) tokens.push("ctrl");
  if (event.altKey) tokens.push("alt");
  if (event.shiftKey) tokens.push("shift");
  return tokens;
}

function dedupeMappingKeyTokens(tokens) {
  const seen = new Set();
  return tokens.filter((token) => {
    if (!token || seen.has(token)) return false;
    seen.add(token);
    return true;
  });
}

function browserKeyToken(event) {
  const key = event.key || "";
  const code = event.code || "";
  const namedKeys = {
    Meta: "cmd",
    OS: "cmd",
    Control: "ctrl",
    Alt: "alt",
    Option: "alt",
    Shift: "shift",
    Escape: "esc",
    Esc: "esc",
    Enter: "enter",
    Return: "enter",
    " ": "space",
    Spacebar: "space",
    Tab: "tab",
    Backspace: "backspace",
    Delete: "delete",
    Insert: "insert",
    Home: "home",
    End: "end",
    PageUp: "page_up",
    PageDown: "page_down",
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
    CapsLock: "caps_lock",
  };
  const codeKeys = {
    Space: "space",
    NumpadEnter: "enter",
    NumpadAdd: "plus",
    NumpadSubtract: "minus",
    NumpadMultiply: "*",
    NumpadDivide: "/",
    NumpadDecimal: ".",
  };
  if (namedKeys[key]) return namedKeys[key];
  if (/^F\d{1,2}$/i.test(key)) return key.toLowerCase();
  if (key.length === 1) {
    const value = key.toLowerCase();
    if (value === "+") return "plus";
    if (value === "-") return "minus";
    if (value === ",") return "comma";
    return value;
  }
  if (codeKeys[code]) return codeKeys[code];
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit\d$/.test(code)) return code.slice(5);
  if (/^Numpad\d$/.test(code)) return code.slice(6);
  return String(key || code)
    .replace(/\s+/g, "_")
    .replace(/-/g, "_")
    .toLowerCase();
}

function stopMappingKeyCapture(message = "") {
  const capture = state.mappingKeyCapture;
  if (!capture) return;
  capture.button?.classList.remove("is-capturing");
  if (capture.button) capture.button.textContent = "Capture";
  if (capture.hint) capture.hint.textContent = message;
  state.mappingKeyCapture = null;
}

function startMappingKeyCapture(input, button, hint, getSelectedModifiers = null) {
  stopMappingKeyCapture();
  state.mappingKeyCapture = { input, button, hint, getSelectedModifiers };
  button.classList.add("is-capturing");
  button.textContent = "Press keys";
  const selected = typeof getSelectedModifiers === "function" ? getSelectedModifiers() : [];
  if (hint) hint.textContent = selected.length ? `${selected.join(" + ")} + ...` : "Waiting for key press...";
  try {
    input.focus({ preventScroll: true });
    input.select();
  } catch {
    input.focus();
  }
}

function applyCapturedMappingKey(event) {
  const capture = state.mappingKeyCapture;
  if (!capture) return false;
  event.preventDefault();
  event.stopPropagation();
  const token = browserKeyToken(event);
  const selectedModifiers = typeof capture.getSelectedModifiers === "function" ? capture.getSelectedModifiers() : [];
  const modifiers = dedupeMappingKeyTokens([...selectedModifiers, ...mappingModifierTokens(event)]);
  if (!token) return true;
  if (isMappingModifierToken(token)) {
    const preview = dedupeMappingKeyTokens([...modifiers, token]);
    if (capture.hint) capture.hint.textContent = preview.length ? `${preview.join(" + ")} + ...` : "Waiting for key press...";
    return true;
  }
  const tokens = dedupeMappingKeyTokens([...modifiers, token]);
  const text = tokens.join(" + ");
  capture.input.value = text;
  capture.input.dispatchEvent(new Event("input", { bubbles: true }));
  stopMappingKeyCapture(`Captured ${text}.`);
  return true;
}

function mappingDraftFromRule(ruleData) {
  const rule = ruleData?.rule || ruleData || {};
  const action = rule.action || {};
  return {
    id: rule.id || mappingRuleId(),
    name: rule.name || "New mapping",
    enabled: rule.enabled !== false,
    source: rule.source || "",
    comparator: rule.comparator || "lt",
    threshold: rule.threshold ?? 100,
    low: rule.low ?? 0,
    high: rule.high ?? 1,
    actionType: action.type || "keyboard_tap",
    keysText: keysToText(action.keys),
    text: action.text || "",
    textSource: action.text_source || "",
    button: action.button || "left",
  };
}

function mappingRulePayloadFromDraft(draft) {
  const threshold = draft.comparator === "truthy" || draft.comparator === "falsey" || draft.comparator === "present"
    ? true
    : Number.isFinite(Number(draft.threshold))
      ? Number(draft.threshold)
      : draft.threshold;
  return {
    id: draft.id,
    name: draft.name || "Mapping",
    enabled: draft.enabled !== false,
    source: draft.source || "",
    comparator: draft.comparator || "lt",
    threshold,
    low: Number(draft.low) || 0,
    high: Number(draft.high) || 1,
    action: {
      type: draft.actionType || "keyboard_tap",
      keys: keysFromText(draft.keysText),
      text: draft.text || "",
      text_source: draft.textSource || "",
      button: draft.button || "left",
    },
  };
}

function openMappingEditor(ruleData, isNew = false) {
  stopMappingKeyCapture();
  state.mappingEditor = { isNew, draft: mappingDraftFromRule(ruleData) };
  renderPage();
}

function closeMappingEditor() {
  stopMappingKeyCapture();
  state.mappingEditor = null;
  renderPage();
}

function saveMappingEditor(draft) {
  stopMappingKeyCapture();
  state.mappingEditor = null;
  return dispatch("mapping.rule.upsert", { rule: mappingRulePayloadFromDraft(draft) });
}

async function importMappingFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const response = await api.call("dispatch", "mapping.import_json", {
      name: file.name || "input_mappings.json",
      text,
    });
    if (response && response.ok === false) {
      throw new Error(response.error || "Could not import mapping JSON.");
    }
    const result = response?.result || {};
    stopMappingKeyCapture();
    state.mappingEditor = null;
    state.mappingImportStatus = `Imported ${file.name || "mapping JSON"} (${result.ruleCount ?? 0} rule(s)). Click Save to persist.`;
  } catch (error) {
    console.error(error);
    state.mappingImportStatus = error.message || "Could not import mapping JSON.";
  } finally {
    await refreshState();
  }
}

function mappingPageSubtitle(mappings) {
  const rules = mappings.rules || [];
  const enabledCount = rules.filter((rule) => rule.enabled).length;
  const parts = [
    mappings.activeProfile || "Default",
    `${rules.length} rule${rules.length === 1 ? "" : "s"}`,
    `${enabledCount} on`,
    mappings.enabled ? "Mapper armed" : "Mapper off",
  ];
  if (mappings.status) parts.push(formatDisplayValue(mappings.status));
  return parts.join(" · ");
}

function mappingProfileBar(mappings) {
  const bar = el("div", "mapping-profile-bar");
  bar.append(el("span", "mapping-profile-label", "Profile"));
  const tabs = el("div", "profile-tabs");
  (mappings.profiles || ["Default"]).forEach((profile) => {
    const active = profile === mappings.activeProfile;
    const tab = el("button", `profile-tab ${active ? "active" : ""}`.trim(), profile);
    tab.type = "button";
    tab.disabled = active;
    tab.addEventListener("click", () => {
      stopMappingKeyCapture();
      state.mappingEditor = null;
      dispatch("mapping.set_profile", { profile });
    });
    tabs.append(tab);
  });
  bar.append(tabs);
  return bar;
}

function mappingSignalOptions(signals, mappings) {
  const items = signals.length
    ? signals
    : (mappings.sources || []).map((source) => ({ id: source, label: source, value: "-" }));
  return items.slice(0, 120);
}

function openMappingEditorForSignal(signal) {
  openMappingEditor(
    {
      rule: {
        id: mappingRuleId(),
        name: signal.label || signal.id,
        enabled: true,
        source: signal.id,
        comparator: signal.id === "keyboard.input" ? "truthy" : "lt",
        threshold: signal.id === "keyboard.input" ? true : 100,
        action: {
          type: signal.id === "keyboard.input" ? "keyboard_text" : "keyboard_tap",
          keys: signal.id === "keyboard.input" ? [] : ["space"],
          text_source: signal.id === "keyboard.input" ? "keyboard.input" : "",
        },
      },
    },
    true,
  );
}

function mappingQuickAdd(signals, mappings) {
  const options = mappingSignalOptions(signals, mappings);
  if (!options.length) return null;

  const bar = el("div", "mapping-quick-add");
  const select = el("select", "mapping-quick-select");
  options.forEach((signal) => {
    const option = el("option", "", `${signal.label || signal.id} (${signal.id})`);
    option.value = signal.id;
    select.append(option);
  });
  const add = el("button", "btn btn-outline", "New from signal");
  add.type = "button";
  add.addEventListener("click", () => {
    const signal = options.find((item) => item.id === select.value) || options[0];
    if (signal) openMappingEditorForSignal(signal);
  });
  bar.append(select, add);
  return bar;
}

function mappingRuleRow(rule) {
  const row = el("div", `mapping-rule-row ${rule.enabled ? "" : "is-off"}`.trim());
  const info = el("div", "mapping-rule-row-info");
  info.append(
    el("span", "mapping-rule-row-name", rule.name || "Unnamed rule"),
    el(
      "span",
      "mapping-rule-row-detail",
      `${formatDisplayValue(rule.source)} · ${formatDisplayValue(rule.condition)} · ${formatDisplayValue(rule.action)}`,
    ),
  );
  row.append(info);

  const actions = el("div", "mapping-rule-row-actions");
  const toggle = el("button", `btn btn-compact ${rule.enabled ? "is-on" : ""}`.trim(), rule.enabled ? "On" : "Off");
  toggle.type = "button";
  toggle.addEventListener("click", () => dispatch("mapping.rule.toggle", { id: rule.id, enabled: !rule.enabled }));
  const edit = el("button", "btn btn-compact btn-outline", "Edit");
  edit.type = "button";
  edit.addEventListener("click", () => openMappingEditor(rule, false));
  const remove = el("button", "btn btn-compact btn-danger", "Delete");
  remove.type = "button";
  remove.addEventListener("click", () => dispatch("mapping.rule.delete", { id: rule.id }));
  actions.append(toggle, edit, remove);
  row.append(actions);
  return row;
}

function mappingRulesPanel(mappings, signals = []) {
  const section = el("section", "mapping-panel");
  const head = el("div", "mapping-panel-head");
  head.append(el("h2", "section-title", "Rules"));
  const add = el("button", "btn btn-primary", "Add rule");
  add.type = "button";
  add.addEventListener("click", () =>
    openMappingEditor(
      {
        rule: {
          id: mappingRuleId(),
          name: "New rule",
          enabled: true,
          source: "",
          comparator: "lt",
          threshold: 100,
          action: { type: "keyboard_tap", keys: ["space"], button: "left" },
        },
      },
      true,
    ),
  );
  head.append(add);
  section.append(head);

  const quickAdd = mappingQuickAdd(signals, mappings);
  if (quickAdd) section.append(quickAdd);

  const list = el("div", "mapping-rules-list");
  const rules = mappings.rules || [];
  if (!rules.length) list.append(el("div", "mapping-empty", "No rules in this profile yet."));
  else rules.forEach((rule) => list.append(mappingRuleRow(rule)));
  section.append(list);
  return section;
}

function mappingSelectField(label, id, options, value) {
  const field = el("div", "field");
  field.append(el("label", "", label));
  const select = el("select");
  select.id = id;
  options.forEach((option) => {
    const node = el("option", "", option.label ?? option);
    node.value = option.value ?? option;
    if ((option.value ?? option) === value) node.selected = true;
    select.append(node);
  });
  select.value = value;
  field.append(select);
  return field;
}

function mappingInputField(label, id, value, type = "text") {
  const field = el("div", "field");
  field.append(el("label", "", label));
  const input = el("input");
  input.id = id;
  input.type = type;
  input.value = value ?? "";
  field.append(input);
  return field;
}

function mappingKeyCaptureField(label, id, value) {
  const field = el("div", "field");
  field.append(el("label", "", label));
  const selectedModifiers = new Set();
  keysFromText(value).filter(isMappingModifierToken).forEach((token) => selectedModifiers.add(token));
  const getSelectedModifiers = () => ["cmd", "ctrl", "alt", "shift"].filter((token) => selectedModifiers.has(token));
  const row = el("div", "mapping-key-capture-row");
  const input = el("input");
  input.id = id;
  input.type = "text";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.value = value ?? "";
  const modifierBar = el("div", "mapping-modifier-toggles");
  [
    ["cmd", "Cmd"],
    ["ctrl", "Ctrl"],
    ["alt", "Alt"],
    ["shift", "Shift"],
  ].forEach(([token, text]) => {
    const modifier = el("button", "mapping-modifier-btn", text);
    modifier.type = "button";
    const active = selectedModifiers.has(token);
    modifier.classList.toggle("is-selected", active);
    modifier.setAttribute("aria-pressed", active ? "true" : "false");
    modifier.addEventListener("click", () => {
      if (selectedModifiers.has(token)) selectedModifiers.delete(token);
      else selectedModifiers.add(token);
      const selected = selectedModifiers.has(token);
      modifier.classList.toggle("is-selected", selected);
      modifier.setAttribute("aria-pressed", selected ? "true" : "false");
      const selectedTokens = getSelectedModifiers();
      if (state.mappingKeyCapture?.input === input) {
        hint.textContent = selectedTokens.length ? `${selectedTokens.join(" + ")} + ...` : "Waiting for key press...";
        input.focus();
      } else {
        hint.textContent = selectedTokens.length ? `${selectedTokens.join(" + ")} selected` : "";
      }
    });
    modifierBar.append(modifier);
  });
  const capture = el("button", "btn btn-outline mapping-capture-btn", "Capture");
  capture.type = "button";
  capture.title = "Capture from keyboard";
  const hint = el("p", "mapping-key-hint", "");
  hint.setAttribute("aria-live", "polite");
  capture.addEventListener("click", () => {
    if (state.mappingKeyCapture?.input === input) {
      stopMappingKeyCapture("Capture cancelled.");
    } else {
      startMappingKeyCapture(input, capture, hint, getSelectedModifiers);
    }
  });
  row.append(input, capture);
  field.append(row, modifierBar, hint);
  return field;
}

function mappingEditorNeedsThreshold(comparator) {
  return !["truthy", "falsey", "present"].includes(comparator);
}

function mappingEditorNeedsKeys(actionType) {
  return actionType === "keyboard_tap" || actionType === "keyboard_hold";
}

function mappingEditorNeedsText(actionType) {
  return actionType === "keyboard_text";
}

function mappingEditorNeedsMouse(actionType) {
  return actionType === "mouse_click" || actionType === "mouse_hold" || actionType === "mouse_scroll";
}

function buildMappingEditor(editorState) {
  const draft = editorState.draft;
  const mappings = state.data?.mappings || {};
  const sources = [...new Set([...(mappings.sources || []), draft.source].filter(Boolean))].sort();
  const overlay = el("div", "mapping-editor-modal");
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeMappingEditor();
  });
  const panel = el("section", "mapping-editor-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "mapping-editor-title");
  const titlebar = el("div", "mapping-editor-titlebar");
  const title = el("h3", "mapping-editor-title", editorState.isNew ? "New rule" : "Edit rule");
  title.id = "mapping-editor-title";
  const close = el("button", "mapping-editor-close", "Close");
  close.type = "button";
  close.addEventListener("click", closeMappingEditor);
  titlebar.append(title, close);
  panel.append(titlebar);

  const fields = el("div", "mapping-editor-fields");
  fields.append(
    mappingInputField("Name", "mapping-name", draft.name),
    mappingSelectField(
      "Signal",
      "mapping-source",
      [{ label: "Choose signal", value: "" }, ...sources.map((source) => ({ label: source, value: source }))],
      draft.source,
    ),
    mappingSelectField(
      "When",
      "mapping-comparator",
      MAPPING_COMPARATORS.map((value) => ({ label: value, value })),
      draft.comparator,
    ),
  );
  if (mappingEditorNeedsThreshold(draft.comparator)) {
    fields.append(mappingInputField("Threshold", "mapping-threshold", draft.threshold));
  }
  fields.append(
    mappingSelectField(
      "Do",
      "mapping-action-type",
      MAPPING_ACTION_TYPES.map((value) => ({ label: value.replace(/_/g, " "), value })),
      draft.actionType,
    ),
  );
  if (mappingEditorNeedsKeys(draft.actionType)) {
    fields.append(mappingKeyCaptureField("Keys", "mapping-keys", draft.keysText));
  }
  if (mappingEditorNeedsText(draft.actionType)) {
    fields.append(mappingInputField("Text", "mapping-text", draft.text));
    fields.append(mappingInputField("Text source", "mapping-text-source", draft.textSource));
  }
  if (mappingEditorNeedsMouse(draft.actionType)) {
    fields.append(
      mappingSelectField(
        "Mouse button",
        "mapping-button",
        MAPPING_MOUSE_BUTTONS.map((value) => ({ label: value, value })),
        draft.button,
      ),
    );
  }
  panel.append(fields);

  const actions = el("div", "mapping-editor-actions");
  const save = el("button", "btn btn-primary", "Save");
  save.type = "button";
  save.addEventListener("click", () => {
    draft.name = document.querySelector("#mapping-name")?.value || draft.name;
    draft.source = document.querySelector("#mapping-source")?.value || "";
    draft.comparator = document.querySelector("#mapping-comparator")?.value || "lt";
    draft.threshold = document.querySelector("#mapping-threshold")?.value ?? draft.threshold;
    draft.actionType = document.querySelector("#mapping-action-type")?.value || "keyboard_tap";
    draft.keysText = document.querySelector("#mapping-keys")?.value || "";
    draft.text = document.querySelector("#mapping-text")?.value || "";
    draft.textSource = document.querySelector("#mapping-text-source")?.value || "";
    draft.button = document.querySelector("#mapping-button")?.value || "left";
    saveMappingEditor(draft);
  });
  const cancel = el("button", "btn btn-muted", "Cancel");
  cancel.type = "button";
  cancel.addEventListener("click", closeMappingEditor);
  actions.append(save, cancel);
  panel.append(actions);
  overlay.append(panel);
  return overlay;
}

function updateMappingControls(mappings) {
  const armed = Boolean(mappings.enabled);
  const toggle = document.querySelector("#mapping-toggle-btn");
  if (!toggle) return;
  toggle.textContent = armed ? "Disable" : "Arm";
  toggle.title = armed ? "Mapper is armed. Click to disable." : "Mapper is disabled. Click to arm.";
  toggle.setAttribute("aria-label", toggle.title);
  toggle.setAttribute("aria-pressed", armed ? "true" : "false");
  toggle.classList.toggle("is-on", armed);
}

function updateMappingsPage(root, { rebuildEditor = false } = {}) {
  const mappings = state.data?.mappings || {};
  const signals = state.data?.signals || [];
  updateMappingControls(mappings);
  const subtitle = root.querySelector(".page-subtitle");
  if (subtitle) subtitle.textContent = mappingPageSubtitle(mappings);
  const importStatusSlot = root.querySelector("#mapping-import-status-slot");
  if (importStatusSlot) {
    importStatusSlot.replaceChildren();
    if (state.mappingImportStatus) {
      importStatusSlot.append(el("div", "mapping-import-status", state.mappingImportStatus));
    }
  }
  root.querySelector("#mapping-profiles-slot")?.replaceChildren(mappingProfileBar(mappings));
  root.querySelector("#mapping-rules-slot")?.replaceChildren(mappingRulesPanel(mappings, signals));
  const editorSlot = root.querySelector("#mapping-editor-slot");
  if (!editorSlot) return;
  if (state.mappingEditor && (rebuildEditor || !editorSlot.querySelector(".mapping-editor-modal"))) {
    editorSlot.replaceChildren(buildMappingEditor(state.mappingEditor));
  } else if (!state.mappingEditor) {
    editorSlot.replaceChildren();
  }
}

function renderMappings(root) {
  const mappings = state.data?.mappings || {};
  root.dataset.page = "Mappings";
  root.replaceChildren();
  const importInput = el("input", "mapping-import-input");
  importInput.id = "mapping-import-input";
  importInput.type = "file";
  importInput.accept = ".json,application/json";
  importInput.addEventListener("change", () => {
    const file = importInput.files && importInput.files[0];
    importMappingFile(file);
    importInput.value = "";
  });
  const importButton = el("button", "btn btn-outline", "Import JSON");
  importButton.type = "button";
  importButton.addEventListener("click", () => importInput.click());
  const toggleButton = toolbarButton(mappings.enabled ? "Disable" : "Arm", "mapping.toggle", {}, "btn btn-primary");
  toggleButton.id = "mapping-toggle-btn";
  root.append(
    pageHeader("Mappings", mappingPageSubtitle(mappings), [
      toggleButton,
      importButton,
      toolbarButton("Save", "mapping.save"),
    ]),
  );
  root.append(importInput);
  const importStatusSlot = el("div");
  importStatusSlot.id = "mapping-import-status-slot";
  const profilesSlot = el("div");
  profilesSlot.id = "mapping-profiles-slot";
  const editorSlot = el("div");
  editorSlot.id = "mapping-editor-slot";
  const rulesSlot = el("div");
  rulesSlot.id = "mapping-rules-slot";
  root.append(importStatusSlot, profilesSlot, editorSlot, rulesSlot);
  updateMappingsPage(root, { rebuildEditor: true });
}

function renderCamera(root) {
  const camera = state.data?.camera || {};
  root.append(
    pageHeader("Camera & Servo", "", [
      toolbarButton(camera.enabled ? "Camera Off" : "Camera On", "camera.toggle_power", {}, "btn btn-primary"),
      toolbarButton(camera.mirror ? "Mirror Off" : "Mirror On", "camera.toggle_mirror"),
      toolbarButton("Center Camera", "camera.center"),
      toolbarButton(camera.autoTracking ? "Tracking Off" : "Tracking On", "tracking.toggle"),
    ]),
  );
  const frame = el("div", "camera-frame");
  const placeholder = el("div", "empty", camera.enabled ? "Waiting for camera frame." : "Camera is off.");
  placeholder.id = "camera-placeholder";
  const img = el("img");
  img.id = "camera-img";
  img.alt = "Camera preview";
  frame.append(img, placeholder);
  root.append(frame);
}

function renderRaw(root) {
  root.append(
    pageHeader("Data / Logs", "", [toolbarButton("Clear Logs", "logs.clear", {}, "btn btn-danger")]),
  );
  const grid = el("div", "grid two");
  const logs = el("div", "log-list");
  (state.data?.logs || []).forEach((line) => logs.append(el("div", "", line)));
  grid.append(card("Log", logs));
  const serial = el("pre", "code", state.data?.raw?.serial || "{}");
  grid.append(card("Antenna JSON", serial));
  root.append(grid);
  const lower = el("div", "grid two");
  lower.append(card("Fused Snapshot", el("pre", "code", state.data?.raw?.snapshot || "{}")));
  lower.append(card("Servo Debug", el("pre", "code", state.data?.raw?.servo || "{}")));
  root.append(lower);
}

function settingsOverviewItem(label, value, tone = "ok") {
  const item = el("div", `settings-overview-item tone-${tone}`);
  item.append(el("span", "settings-overview-label", label), el("strong", "settings-overview-value", formatDisplayValue(value)));
  return item;
}

function settingsOverview(auth, serial, mappings) {
  const panel = el("section", "settings-overview");
  const grid = el("div", "settings-overview-grid");
  grid.append(
    settingsOverviewItem("Account", auth.user || "Guest"),
    settingsOverviewItem("Hub", serial.connected ? "Connected" : "Disconnected", serial.connected ? "ok" : "warn"),
    settingsOverviewItem("Mapper", mappings.enabled ? "Armed" : "Disabled", mappings.enabled ? "ok" : "warn"),
  );
  panel.append(grid);
  return panel;
}

function settingsRow(label, value) {
  const row = el("div", "settings-row");
  row.append(el("span", "settings-row-label", label), el("span", "settings-row-value", formatDisplayValue(value)));
  return row;
}

function settingsPanel(title, rows, actions = null) {
  const section = el("section", "settings-panel");
  section.append(el("h2", "section-title", title));
  const body = el("div", "settings-panel-body");
  rows.forEach((row) => body.append(row));
  if (actions) body.append(actions);
  section.append(body);
  return section;
}

function settingsActions(buttons) {
  const wrap = el("div", "settings-actions");
  buttons.forEach((btn) => wrap.append(btn));
  return wrap;
}

function renderSettings(root) {
  const auth = state.data?.auth || {};
  const cloud = state.data?.cloud || {};
  const camera = state.data?.camera || {};
  const serial = state.data?.serial || {};
  const mappings = state.data?.mappings || {};
  const app = state.data?.app || {};
  const isAdmin = auth.role === "admin";

  root.append(
    pageHeader("Settings", "", [
      ...(isAdmin ? [toolbarButton("Open App Data", "app.open_data_dir")] : []),
      toolbarButton("Logout", "auth.logout", {}, "btn btn-danger"),
    ]),
  );

  root.append(settingsOverview(auth, serial, mappings));

  root.append(
    settingsPanel("Account", [
      settingsRow("Signed in as", auth.user || "Guest"),
      settingsRow("Email", auth.email || "-"),
      settingsRow("Panel access", (auth.role || "guest").toUpperCase()),
    ]),
  );

  root.append(
    settingsPanel(
      "Cloud Sync",
      [
        settingsRow("Appwrite", cloud.configured ? "Configured" : "Not configured"),
        settingsRow("Status", cloud.error || cloud.syncStatus || "-"),
        settingsRow("Last sync", cloud.lastSyncedAt || "-"),
      ],
      settingsActions([button("Sync Now", "sync.now", {}, "btn btn-primary")]),
    ),
  );

  root.append(
    settingsPanel("Connection", [
      settingsRow("Antenna hub", serial.connected ? serial.port || "Connected" : "Not connected"),
      settingsRow("Input mapper", mappings.enabled ? "Armed" : "Disabled"),
      settingsRow("Mapping profile", mappings.activeProfile || "Default"),
      settingsRow("Mapper status", mappings.status || "-"),
    ]),
  );

  root.append(
    settingsPanel(
      "Camera",
      [
        settingsRow("Camera", camera.enabled ? "On" : "Off"),
        settingsRow("Mirror preview", camera.mirror ? "On" : "Off"),
        settingsRow("Auto tracking", camera.autoTracking ? "On" : "Off"),
      ],
      settingsActions([
        button(camera.enabled ? "Turn Off" : "Turn On", "camera.toggle_power", {}, "btn btn-primary"),
        button("Center", "camera.center"),
        button(camera.autoTracking ? "Disable Tracking" : "Enable Tracking", "tracking.toggle"),
      ]),
    ),
  );

  const appRows = [settingsRow("Runtime", app.runtime || "-")];
  if (isAdmin) {
    appRows.push(settingsRow("App data folder", app.userDataDir || "-"));
  }
  root.append(settingsPanel("Application", appRows));
}

function testingSubtitle(testing) {
  const entries = testing.entries || [];
  const passCount = entries.filter((entry) => entry.status === "PASS").length;
  const parts = [
    testing.active ? "Armed" : "Stopped",
    testing.mode === "all" ? "All in one" : "Selected gesture",
    `${entries.length} gesture${entries.length === 1 ? "" : "s"}`,
    `${passCount} pass`,
  ];
  if (testing.outputSuppressed !== false) parts.push("outputs suppressed");
  return parts.join(" · ");
}

function testingModeButton(label, mode, testing) {
  const active = (testing.mode || "selected") === mode;
  const node = el("button", `btn ${active ? "btn-primary" : "btn-outline"} testing-mode-button`, label);
  node.type = "button";
  node.setAttribute("aria-pressed", active ? "true" : "false");
  node.addEventListener("click", () => dispatch("testing.set_mode", { mode }));
  return node;
}

function testingControls(testing) {
  const panel = el("section", "testing-controls");
  const modeGroup = el("div", "testing-mode-group");
  modeGroup.append(
    testingModeButton("Selected gesture", "selected", testing),
    testingModeButton("All in one", "all", testing),
  );
  const suppress = el("label", "testing-check");
  const checkbox = el("input");
  checkbox.type = "checkbox";
  checkbox.checked = testing.outputSuppressed !== false;
  checkbox.addEventListener("change", () => dispatch("testing.set_suppress", { enabled: checkbox.checked }));
  suppress.append(checkbox, el("span", "", "Suppress mapped outputs"));
  const actions = el("div", "testing-actions");
  const start = el("button", "btn btn-primary", "Start");
  start.type = "button";
  start.addEventListener("click", () => dispatch("testing.start", { mode: testing.mode || "selected" }));
  const stop = el("button", "btn btn-outline", "Stop");
  stop.type = "button";
  stop.addEventListener("click", () => dispatch("testing.stop"));
  const refresh = el("button", "btn btn-outline", "Refresh List");
  refresh.type = "button";
  refresh.addEventListener("click", () => dispatch("testing.refresh"));
  actions.append(start, stop, refresh);
  panel.append(modeGroup, suppress, actions);
  return panel;
}

function testingEntryRow(entry, testing) {
  const selected = entry.id === testing.selectedId;
  const row = el("button", `testing-entry-row ${selected ? "is-selected" : ""}`.trim());
  row.type = "button";
  row.addEventListener("click", () => dispatch("testing.select", { id: entry.id }));
  const info = el("div", "testing-entry-info");
  info.append(
    el("span", "testing-entry-name", entry.name || entry.id),
    el("span", "testing-entry-trigger", entry.trigger || "-"),
  );
  const meta = el("div", "testing-entry-meta");
  meta.append(
    el("span", "testing-entry-type", entry.type || "-"),
    statusPill(entry.status || "-", entry.status === "PASS" ? "ok" : "warn"),
  );
  row.append(info, meta);
  return row;
}

function testingEntriesPanel(testing) {
  const body = el("div", "testing-entry-list");
  const entries = testing.entries || [];
  if (!entries.length) {
    body.append(el("div", "mapping-empty", "No gestures are available to test."));
  } else {
    entries.forEach((entry) => body.append(testingEntryRow(entry, testing)));
  }
  return card("Available Gestures", body, "", "testing-list-card");
}

function testingResultLine(label, value) {
  const row = el("div", "testing-result-line");
  row.append(el("span", "", label), el("strong", "", value || "-"));
  return row;
}

function testingResultsPanel(testing) {
  const body = el("div", "testing-result-body");
  body.append(
    testingResultLine("Mode", testing.status || "-"),
    testingResultLine("Selected", testing.selectedName || (testing.mode === "all" ? "all in one" : "-")),
    testingResultLine("Detected", testing.detected || "Detected: -"),
  );
  const live = el("div", "testing-live-grid");
  (testing.liveValues || []).forEach((item) => {
    const chip = el("div", "testing-live-chip");
    chip.append(el("span", "", item.label || "-"), el("strong", "", formatDisplayValue(item.value)));
    live.append(chip);
  });
  body.append(el("h4", "testing-subtitle", "Signals"), live);
  const history = el("div", "log-list testing-history");
  const lines = testing.history || [];
  if (!lines.length) history.append(el("span", "muted", "No recognition history yet."));
  else lines.forEach((line) => history.append(el("span", "", line)));
  body.append(el("h4", "testing-subtitle", "History"), history);
  return card("Recognition Result", body, "", "testing-result-card");
}

function updateTestingPage(root) {
  const testing = state.data?.testing || {};
  const subtitle = root.querySelector(".page-subtitle");
  if (subtitle) subtitle.textContent = testingSubtitle(testing);
  const slot = root.querySelector("#testing-body-slot");
  if (!slot) return;
  const layout = el("div", "testing-layout");
  layout.append(testingEntriesPanel(testing), testingResultsPanel(testing));
  slot.replaceChildren(testingControls(testing), layout);
}

function renderTesting(root) {
  const testing = state.data?.testing || {};
  const bodySlot = el("div", "testing-body-slot");
  bodySlot.id = "testing-body-slot";
  root.dataset.page = "Testing";
  root.replaceChildren(pageHeader("Testing", testingSubtitle(testing), []), bodySlot);
  updateTestingPage(root);
}

function renderGeneric(root, title) {
  const signals = (state.data?.signals || []).filter((signal) => signal.group.toLowerCase().includes(title.split(" ")[0].toLowerCase()));
  root.append(pageHeader(title, "", []));
  const rows = signals.slice(0, 80).map((signal) => [signal.label, signal.id, signal.value]);
  if (rows.length) {
    const section = el("section", "page-table");
    section.append(table(["Signal", "ID", "Value"], rows));
    root.append(section);
  } else {
    root.append(el("div", "empty", "Waiting for live data."));
  }
}

function metricCard(title, metric) {
  const body = el("div", "metric-card-body");
  body.append(el("p", "metric", formatDisplayValue(metric)));
  return card(title, body, "", "metric-card");
}

function keyboardPayload() {
  return {
    words: document.querySelector("#keyboard-words")?.value || "",
    repetitions: document.querySelector("#keyboard-reps")?.value || "3",
    seconds: document.querySelector("#keyboard-seconds")?.value || "3",
    reset_dataset: document.querySelector("#keyboard-reset")?.value === "true",
    include_commands: true,
  };
}

function renderPage() {
  ensureShell();
  const root = pageRoot();
  const page = state.activePage;
  const previousPage = root.dataset.page || "";

  if (page === "Dashboard" && previousPage === "Dashboard") {
    updateDashboard(root);
    return;
  }

  if (page === "Mappings" && previousPage === "Mappings") {
    updateMappingsPage(root);
    return;
  }

  if (page === "Testing" && previousPage === "Testing") {
    updateTestingPage(root);
    return;
  }

  if (previousPage === "Dashboard" && page !== "Dashboard") {
    destroyDashboardCharts();
  }

  if (previousPage === "Mappings" && page !== "Mappings") {
    stopMappingKeyCapture();
    state.mappingEditor = null;
  }

  root.replaceChildren();
  root.dataset.page = page;
  try {
    if (page === "Dashboard") renderDashboard(root);
    else if (page === "Signals") renderSignals(root);
    else if (page === "Keyboard") renderKeyboard(root);
    else if (page === "Mappings") renderMappings(root);
    else if (page === "Testing") renderTesting(root);
    else if (page === "Settings") renderSettings(root);
    else if (page === "Camera & Servo") renderCamera(root);
    else if (page === "Data / Logs") renderRaw(root);
    else renderGeneric(root, page);
  } catch (error) {
    renderError(root, error);
  }
}

async function dispatch(action, payload = {}) {
  try {
    const response = await api.call("dispatch", action, payload);
    if (response && response.ok === false) {
      throw new Error(response.error || "Action failed.");
    }
    if (action === "mapping.save") {
      state.mappingImportStatus = "Mappings saved.";
    }
  } catch (error) {
    console.error(error);
  } finally {
    await refreshState();
  }
}

async function refreshState() {
  try {
    const data = await api.call("get_state");
    state.data = data;
    state.activePage = data?.app?.activePage || "Dashboard";
    if (!data?.auth?.authenticated) {
      const app = document.querySelector("#app");
      const error = data?.auth?.error || "";
      if (!app.classList.contains("login-shell") || state.loginError !== error) {
        state.loginError = error;
        renderLogin();
      }
      return;
    }
    state.loginError = null;
    renderNav();
    renderSerial();
    renderTopbar();
    renderPage();
    pollCamera();
  } catch (error) {
    ensureShell();
    renderError(document.querySelector("#page .page-inner") || document.querySelector("#page"), error);
  }
}

async function pollCamera() {
  if (state.activePage !== "Camera & Servo") return;
  const stamp = Date.now();
  state.cameraStamp = stamp;
  const result = await api.call("get_camera_frame", 1120, 720);
  if (state.cameraStamp !== stamp) return;
  const img = document.querySelector("#camera-img");
  const placeholder = document.querySelector("#camera-placeholder");
  if (!img || !placeholder) return;
  if (result?.src) {
    img.src = result.src;
    img.style.display = "block";
    placeholder.style.display = "none";
  } else {
    img.removeAttribute("src");
    img.style.display = "none";
    placeholder.textContent = result?.reason || "Waiting for camera frame.";
    placeholder.style.display = "grid";
  }
}

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function escapeText(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderError(root, error) {
  if (!root) return;
  const message = error && error.message ? error.message : String(error || "Unknown error");
  root.replaceChildren();
  const panel = el("div", "render-error");
  panel.append(el("h2", "", "Interface Render Error"));
  panel.append(el("p", "", "The app is still running, but this panel could not render."));
  panel.append(el("pre", "", message));
  root.append(panel);
}

document.addEventListener("click", (event) => {
  const node = event.target.closest("[data-action]");
  if (!node) return;
  const action = node.dataset.action;
  if (action) dispatch(action);
});

document.addEventListener("keydown", (event) => {
  if (applyCapturedMappingKey(event)) return;
  if (event.key === "Escape" && state.mappingEditor) {
    closeMappingEditor();
  }
});

window.addEventListener("beforeunload", () => {
  if (window.pywebview?.api?.close) window.pywebview.api.close();
});

applyTheme(getStoredTheme());
refreshState();
setInterval(refreshState, 800);
setInterval(pollCamera, 220);
