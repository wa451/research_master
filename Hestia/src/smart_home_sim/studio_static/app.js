const DAYS = [
  ["monday", "月"],
  ["tuesday", "火"],
  ["wednesday", "水"],
  ["thursday", "木"],
  ["friday", "金"],
  ["saturday", "土"],
  ["sunday", "日"],
];

const DEVICE_TYPES = [
  "MotionSensor",
  "ContactSensor",
  "DoorSensor",
  "Light",
  "AirConditioner",
  "Television",
  "SmartPlug",
  "CoffeeMachine",
];

const DEVICE_ICONS = {
  MotionSensor: "◉",
  ContactSensor: "⌑",
  DoorSensor: "↔",
  Light: "☀",
  AirConditioner: "≋",
  Television: "▣",
  SmartPlug: "⌁",
  CoffeeMachine: "☕",
};

const EVALUATION_HOUSES = ["compact", "corridor", "branched"];
const FLOORPLAN_EXPORT_WIDTH = 1600;
const FLOORPLAN_EXPORT_HEIGHT = 1000;

let uiRoot = document;
let componentBridge = null;
let componentBootstrap = null;
let componentInitialized = false;
let componentResponseId = null;
let componentRequestSequence = 0;
let componentSyncTimer = null;
let boundEventDocument = null;
const componentRequests = new Map();
const dom = {};

function bindDom(root) {
  const selectors = {
    workspace: "#workspace",
    visualEditor: "#visual-editor",
    codePane: "#code-pane",
    guiModeButton: "#gui-mode-button",
    codeModeButton: "#code-mode-button",
    codeFormatYaml: "#code-format-yaml",
    codeFormatJson: "#code-format-json",
    codeFormatButton: "#code-format-button",
    codeValidateButton: "#code-validate-button",
    codeApplyButton: "#code-apply-button",
    codeEditor: "#code-editor",
    codeFormatLabel: "#code-format-label",
    sourceFileName: "#source-file-name",
    exportFileName: "#export-file-name",
    exportYamlButton: "#export-yaml-button",
    codeStatus: "#code-status",
    codeValidation: "#code-validation",
    saveFileName: "#save-file-name",
    saveYamlButton: "#save-yaml-button",
    saveStatus: "#save-status",
    refreshScenariosButton: "#refresh-scenarios-button",
    runScenarioSelect: "#run-scenario-select",
    runDays: "#run-days",
    runSeed: "#run-seed",
    runOutputName: "#run-output-name",
    runOutputPreview: "#run-output-preview",
    runSimulationButton: "#run-simulation-button",
    runStatus: "#run-status",
    runResult: "#run-result",
    scenarioName: "#scenario-name",
    validationButton: "#validation-button",
    validationStatus: "#validation-status",
    roomList: "#room-list",
    residentList: "#resident-list",
    activityList: "#activity-list",
    homeSummary: "#home-summary",
    connectButton: "#connect-button",
    connectionHint: "#connection-hint",
    roomLayer: "#room-layer",
    connectionLayer: "#connection-layer",
    floorplan: "#floorplan",
    floorplanEmpty: "#floorplan-empty",
    evaluationHouseSwitcher: "#evaluation-house-switcher",
    exportFloorplanSvgButton: "#export-floorplan-svg-button",
    exportFloorplanPngButton: "#export-floorplan-png-button",
    personGrid: "#person-grid",
    activityGrid: "#activity-grid",
    inspectorTitle: "#inspector-title",
    inspectorContent: "#inspector-content",
    validationReport: "#validation-report",
    toast: "#toast",
    importInput: "#import-input",
  };
  Object.entries(selectors).forEach(function (entry) {
    dom[entry[0]] = root.querySelector(entry[1]);
  });
}

const state = {
  activeTab: "layout",
  connectingFrom: null,
  editorMode: "gui",
  drag: null,
  routineDays: {},
  scenario: null,
  selected: { type: "home", id: null },
  sourceFileName: null,
  evaluationHouse: null,
  evaluationHouseSessions: {},
  project: {
    dirty: true,
    error: false,
    files: [],
    fileName: "",
    loading: false,
    message: "",
    saving: false,
    selectedPath: "",
  },
  run: {
    days: 7,
    error: false,
    message: "",
    outputName: "",
    outputNameAutomatic: true,
    result: null,
    running: false,
    seed: 42,
  },
  validation: { kind: "neutral", errors: [] },
  code: {
    appliedText: "",
    dirty: false,
    format: "yaml",
    loading: false,
    stale: true,
    text: "",
  },
};

let toastTimer;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, function (character) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[character];
  });
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function componentWorkspaceSnapshot() {
  saveCurrentEvaluationHouseSession();
  return deepClone({
    activeTab: state.activeTab,
    connectingFrom: state.connectingFrom,
    editorMode: state.editorMode,
    routineDays: state.routineDays,
    scenario: state.scenario,
    selected: state.selected,
    sourceFileName: state.sourceFileName,
    evaluationHouse: state.evaluationHouse,
    evaluationHouseSessions: state.evaluationHouseSessions,
    project: Object.assign({}, state.project, { loading: false, saving: false }),
    run: Object.assign({}, state.run, { running: false }),
    validation: state.validation,
    code: Object.assign({}, state.code, { loading: false }),
  });
}

function syncComponentWorkspace() {
  if (!componentBridge || !state.scenario) {
    return;
  }
  componentBridge.setStateValue("workspace", componentWorkspaceSnapshot());
}

function scheduleComponentWorkspaceSync() {
  if (!componentBridge) {
    return;
  }
  window.clearTimeout(componentSyncTimer);
  componentSyncTimer = window.setTimeout(syncComponentWorkspace, 800);
}

function restoreComponentWorkspace(workspace, bootstrap) {
  const restored = deepClone(workspace);
  [
    "activeTab",
    "connectingFrom",
    "editorMode",
    "routineDays",
    "scenario",
    "selected",
    "sourceFileName",
    "evaluationHouse",
    "evaluationHouseSessions",
    "project",
    "run",
    "validation",
    "code",
  ].forEach(function (key) {
    if (restored[key] !== undefined) {
      state[key] = restored[key];
    }
  });
  state.drag = null;
  state.project.loading = false;
  state.project.saving = false;
  state.run.running = false;
  state.code.loading = false;
  if (bootstrap && Array.isArray(bootstrap.files)) {
    state.project.files = deepClone(bootstrap.files);
  }
  ensureLayout();
}

function asNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function deviceIcon(type) {
  return DEVICE_ICONS[type] || "◌";
}

function deviceLabel(type) {
  const labels = {
    MotionSensor: "人感センサー",
    ContactSensor: "開閉センサー",
    DoorSensor: "ドアセンサー",
    Light: "照明",
    AirConditioner: "エアコン",
    Television: "テレビ",
    SmartPlug: "スマートプラグ",
    CoffeeMachine: "コーヒーメーカー",
  };
  return labels[type] || type;
}

function defaultRoomPosition(index) {
  const column = index % 3;
  const row = Math.floor(index / 3);
  return {
    x: 7 + column * 28,
    y: 10 + row * 31,
    width: 23,
    height: 24,
  };
}

function defaultDevicePosition(index) {
  return {
    x: 18 + (index % 3) * 30,
    y: 61 + Math.floor(index / 3) * 18,
  };
}

function ensureLayout() {
  if (!state.scenario) {
    return;
  }
  if (!state.scenario.editor_layout) {
    state.scenario.editor_layout = {};
  }
  const layout = state.scenario.editor_layout;
  if (!layout.room_positions) {
    layout.room_positions = {};
  }
  if (!layout.device_positions) {
    layout.device_positions = {};
  }
  const roomIds = new Set(state.scenario.rooms.map(function (room) {
    return room.id;
  }));
  Object.keys(layout.room_positions).forEach(function (roomId) {
    if (!roomIds.has(roomId)) {
      delete layout.room_positions[roomId];
    }
  });
  const deviceIds = new Set();
  state.scenario.rooms.forEach(function (room, roomIndex) {
    if (!layout.room_positions[room.id]) {
      layout.room_positions[room.id] = defaultRoomPosition(roomIndex);
    }
    const position = layout.room_positions[room.id];
    position.width = clamp(asNumber(position.width, 23), 10, 95);
    position.height = clamp(asNumber(position.height, 24), 10, 95);
    position.x = clamp(asNumber(position.x, 7), 0, 100 - position.width);
    position.y = clamp(asNumber(position.y, 10), 0, 100 - position.height);
    room.devices.forEach(function (device, deviceIndex) {
      deviceIds.add(device.id);
      if (!layout.device_positions[device.id]) {
        layout.device_positions[device.id] = defaultDevicePosition(deviceIndex);
      }
      const devicePosition = layout.device_positions[device.id];
      devicePosition.x = clamp(asNumber(devicePosition.x, 50), 5, 95);
      devicePosition.y = clamp(asNumber(devicePosition.y, 50), 16, 94);
    });
  });
  Object.keys(layout.device_positions).forEach(function (deviceId) {
    if (!deviceIds.has(deviceId)) {
      delete layout.device_positions[deviceId];
    }
  });
}

function currentRoom() {
  if (state.selected.type !== "room") {
    return null;
  }
  return state.scenario.rooms.find(function (room) {
    return room.id === state.selected.id;
  }) || null;
}

function currentDevice() {
  if (state.selected.type !== "device") {
    return null;
  }
  for (const room of state.scenario.rooms) {
    const device = room.devices.find(function (candidate) {
      return candidate.id === state.selected.id;
    });
    if (device) {
      return { device: device, room: room };
    }
  }
  return null;
}

function currentResident() {
  if (state.selected.type !== "resident") {
    return null;
  }
  return state.scenario.residents.find(function (resident) {
    return resident.id === state.selected.id;
  }) || null;
}

function currentActivity() {
  if (state.selected.type !== "activity") {
    return null;
  }
  return state.scenario.activities.find(function (activity) {
    return activity.id === state.selected.id;
  }) || null;
}

function currentConnection() {
  if (state.selected.type !== "connection") {
    return null;
  }
  const index = Number(state.selected.id);
  const connection = state.scenario.connections[index];
  return connection ? { connection: connection, index: index } : null;
}

function roomForDevice(deviceId) {
  return state.scenario.rooms.find(function (room) {
    return room.devices.some(function (device) {
      return device.id === deviceId;
    });
  }) || null;
}

function allDevices() {
  return state.scenario.rooms.flatMap(function (room) {
    return room.devices.map(function (device) {
      return { device: device, room: room };
    });
  });
}

function actuatorDevices(roomId) {
  return allDevices().filter(function (entry) {
    return entry.room.id === roomId
      && !["MotionSensor", "ContactSensor", "DoorSensor"].includes(entry.device.type);
  });
}

function doorDevices() {
  return allDevices().filter(function (entry) {
    return entry.device.type === "DoorSensor";
  });
}

function zonesForRoom(roomId) {
  const room = state.scenario.rooms.find(function (candidate) {
    return candidate.id === roomId;
  });
  return room && Array.isArray(room.zones) ? room.zones : [];
}

function routineEntry(item) {
  return typeof item === "string" ? { activity_id: item } : item;
}

function ensureRoutineEntry(resident, day, index) {
  const item = resident.weekly_routine[day][index];
  if (typeof item === "string") {
    resident.weekly_routine[day][index] = { activity_id: item };
  }
  return resident.weekly_routine[day][index];
}

function routineCount(resident) {
  return DAYS.reduce(function (total, day) {
    return total + (resident.weekly_routine[day[0]] || []).length;
  }, 0);
}

function formatMinutes(minutes) {
  if (minutes === undefined || minutes === null || minutes === "") {
    return "";
  }
  const value = Math.round(asNumber(minutes, 0));
  const hours = Math.floor(value / 60) % 24;
  const remainder = value % 60;
  return String(hours).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
}

function minutesFromTime(time) {
  if (!time || time.length !== 5) {
    return null;
  }
  const parts = time.split(":");
  return Number(parts[0]) * 60 + Number(parts[1]);
}

function markProjectDirty() {
  state.project.dirty = true;
  state.project.error = false;
  state.project.message = "現在の編集はまだプロジェクトへ保存されていません。";
  state.run.result = null;
  state.run.error = false;
  state.run.message = "";
}

function markDirty() {
  state.validation = { kind: "neutral", errors: [] };
  if (state.editorMode === "gui") {
    state.code.stale = true;
  }
  markProjectDirty();
  renderStatus();
  renderValidationReport();
  renderRunPane();
  scheduleComponentWorkspaceSync();
}

function resetCodeDraft() {
  state.code.appliedText = "";
  state.code.dirty = false;
  state.code.stale = true;
  state.code.text = "";
}

function displaySourceFileName() {
  return state.sourceFileName || "未保存のシナリオ";
}

function exportFileName(format) {
  const fallback = state.scenario && state.scenario.id ? state.scenario.id : "scenario";
  const source = state.sourceFileName || fallback;
  const stem = source.replace(/\.(?:json|ya?ml)$/i, "");
  return stem + "." + (format === "json" ? "json" : "yaml");
}

function selectedScenarioFile() {
  return state.project.files.find(function (file) {
    return file.path === state.project.selectedPath;
  }) || null;
}

function defaultRunOutputName() {
  const selected = selectedScenarioFile();
  const source = selected ? selected.name : state.project.fileName || exportFileName("yaml");
  const stem = source.replace(/\.(?:ya?ml)$/i, "") || "scenario";
  return stem + "-d" + state.run.days + "-s" + state.run.seed;
}

function refreshAutomaticOutputName() {
  if (state.run.outputNameAutomatic) {
    state.run.outputName = defaultRunOutputName();
  }
}

function resetProjectScenario(sourcePath, dirty) {
  state.project.selectedPath = sourcePath || "";
  state.project.fileName = exportFileName("yaml");
  state.project.dirty = dirty;
  state.project.error = false;
  state.project.message = dirty ? "現在の編集はまだプロジェクトへ保存されていません。" : "";
  state.run.result = null;
  state.run.error = false;
  state.run.message = "";
  state.run.outputNameAutomatic = true;
  refreshAutomaticOutputName();
}

function createEvaluationHouseSession(body) {
  return {
    scenario: deepClone(body.scenario),
    sourceFileName: body.source_filename || null,
    sourcePath: body.source_path || "",
    projectFileName: body.source_filename || "",
    projectDirty: !body.source_path || !body.scenario.editor_layout,
    projectMessage: "",
    projectSelectedPath: body.source_path || "",
    run: null,
    code: null,
  };
}

function saveCurrentEvaluationHouseSession() {
  if (!state.evaluationHouse || !state.scenario) {
    return;
  }
  state.evaluationHouseSessions[state.evaluationHouse] = {
    scenario: deepClone(state.scenario),
    sourceFileName: state.sourceFileName,
    sourcePath: "",
    projectFileName: state.project.fileName,
    projectDirty: state.project.dirty,
    projectMessage: state.project.message,
    projectSelectedPath: state.project.selectedPath,
    run: deepClone(state.run),
    code: deepClone(state.code),
  };
}

function activateEvaluationHouseSession(house) {
  const session = state.evaluationHouseSessions[house];
  if (!session) {
    return false;
  }
  state.evaluationHouse = house;
  state.scenario = deepClone(session.scenario);
  state.sourceFileName = session.sourceFileName;
  state.selected = { type: "home", id: null };
  state.activeTab = "layout";
  state.connectingFrom = null;
  state.validation = { kind: "neutral", errors: [] };
  resetProjectScenario(session.projectSelectedPath || session.sourcePath, session.projectDirty);
  state.project.fileName = session.projectFileName || exportFileName("yaml");
  state.project.message = session.projectMessage || (session.projectDirty
    ? "現在の編集はまだプロジェクトへ保存されていません。"
    : "");
  if (session.run) {
    state.run = deepClone(session.run);
    state.run.running = false;
  }
  if (session.code) {
    state.code = deepClone(session.code);
    state.code.loading = false;
  } else {
    resetCodeDraft();
  }
  ensureLayout();
  return true;
}

function renderEvaluationHouseSwitcher() {
  const enabled = Boolean(state.evaluationHouse);
  dom.evaluationHouseSwitcher.hidden = !enabled;
  uiRoot.querySelectorAll("[data-evaluation-house]").forEach(function (button) {
    const active = button.dataset.evaluationHouse === state.evaluationHouse;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.disabled = state.project.saving || state.project.loading || state.run.running
      || state.code.loading;
  });
}

async function switchEvaluationHouse(house) {
  if (!EVALUATION_HOUSES.includes(house) || house === state.evaluationHouse) {
    return;
  }
  if (state.project.saving || state.project.loading || state.run.running || state.code.loading) {
    showToast("処理が完了してから住宅を切り替えてください。", true);
    return;
  }
  saveCurrentEvaluationHouseSession();
  if (!activateEvaluationHouseSession(house)) {
    showToast("住宅設定を読み込めませんでした。", true);
    return;
  }
  if (!componentBridge) {
    const url = new URL(window.location.href);
    url.searchParams.set("evaluation_house", house);
    window.history.replaceState({}, "", url);
  }
  render();
  await loadProjectScenarios(state.project.selectedPath);
  scheduleComponentWorkspaceSync();
  showToast(house + " に切り替えました。未保存編集は住宅ごとに保持されます。");
}

function showToast(message, isError) {
  window.clearTimeout(toastTimer);
  dom.toast.textContent = message;
  dom.toast.classList.toggle("error", Boolean(isError));
  dom.toast.classList.add("show");
  toastTimer = window.setTimeout(function () {
    dom.toast.classList.remove("show");
  }, 3400);
}

function request(path, options) {
  if (componentBridge) {
    const requestId = "studio-" + Date.now() + "-" + (++componentRequestSequence);
    let body = null;
    if (options && options.body) {
      try {
        body = JSON.parse(options.body);
      } catch (error) {
        body = options.body;
      }
    }
    syncComponentWorkspace();
    return new Promise(function (resolve, reject) {
      componentRequests.set(requestId, { resolve: resolve, reject: reject });
      componentBridge.setTriggerValue("request", {
        id: requestId,
        path: path,
        method: options && options.method ? options.method : "GET",
        body: body,
      });
    });
  }
  return fetch(path, options).then(async function (response) {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    return { response: response, body: body };
  });
}

function handleComponentResponse(response) {
  if (!response || !response.id || response.id === componentResponseId) {
    return;
  }
  componentResponseId = response.id;
  const pending = componentRequests.get(response.id);
  if (!pending) {
    return;
  }
  componentRequests.delete(response.id);
  pending.resolve({
    response: {
      ok: Boolean(response.ok),
      status: Number(response.status || 500),
    },
    body: response.body,
  });
}

function errorsFromResponse(body, fallback) {
  if (body && Array.isArray(body.errors)) {
    return body.errors;
  }
  return [{ path: "scenario", message: fallback || "シナリオを処理できませんでした。" }];
}

function saveErrorFallback(response) {
  if (response && response.status === 404) {
    return "保存処理が見つかりません。アプリを再読み込みしてください。";
  }
  return "YAMLを保存できませんでした。";
}

async function importScenarioText(text, format) {
  return request("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text, format: format }),
  });
}

async function exportScenarioText(scenario, format) {
  const result = await request("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: scenario, format: format }),
  });
  if (result.response.ok) {
    return { ok: true, text: result.body };
  }
  return { ok: false, errors: errorsFromResponse(result.body) };
}

function selectItem(type, id, tab) {
  state.selected = { type: type, id: id };
  if (tab) {
    state.activeTab = tab;
  }
  render();
}

function focusDuringDrag(type, id) {
  state.selected = { type: type, id: id };
  renderSidebar();
  renderPeople();
  renderActivities();
  renderInspector();
  renderTabState();
  updateSelectionClasses();
  renderConnections();
}

function updateSelectionClasses() {
  uiRoot.querySelectorAll(".room").forEach(function (element) {
    element.classList.toggle(
      "selected",
      state.selected.type === "room" && element.dataset.roomId === state.selected.id,
    );
  });
  uiRoot.querySelectorAll(".device").forEach(function (element) {
    element.classList.toggle(
      "selected",
      state.selected.type === "device" && element.dataset.deviceId === state.selected.id,
    );
  });
}

function renderStatus() {
  const kind = state.validation.kind;
  dom.validationButton.className = "validation-status " + kind;
  dom.validationStatus.textContent = {
    neutral: "未検証",
    valid: "検証済み",
    invalid: "要修正",
  }[kind] || "未検証";
}

function renderCodeValidation() {
  const errors = state.validation.errors || [];
  if (state.editorMode !== "code" || !errors.length) {
    dom.codeValidation.hidden = true;
    dom.codeValidation.innerHTML = "";
    return;
  }
  dom.codeValidation.hidden = false;
  dom.codeValidation.innerHTML = "<strong>適用前に修正が必要な項目</strong><ul>" + errors.slice(0, 10).map(function (error) {
    return "<li><code>" + escapeHtml(error.path) + "</code><br>" + escapeHtml(error.message) + "</li>";
  }).join("") + (errors.length > 10 ? "<li>ほか " + (errors.length - 10) + " 件</li>" : "") + "</ul>";
}

function renderEditorMode() {
  const codeMode = state.editorMode === "code";
  dom.workspace.classList.toggle("code-mode", codeMode);
  dom.visualEditor.hidden = codeMode;
  dom.codePane.hidden = !codeMode;
  dom.guiModeButton.classList.toggle("active", !codeMode);
  dom.codeModeButton.classList.toggle("active", codeMode);
  dom.guiModeButton.setAttribute("aria-pressed", String(!codeMode));
  dom.codeModeButton.setAttribute("aria-pressed", String(codeMode));
  if (!codeMode) {
    return;
  }
  if (dom.codeEditor.value !== state.code.text) {
    dom.codeEditor.value = state.code.text;
  }
  dom.codeFormatYaml.classList.toggle("active", state.code.format === "yaml");
  dom.codeFormatJson.classList.toggle("active", state.code.format === "json");
  dom.codeFormatLabel.textContent = state.code.format.toUpperCase();
  dom.sourceFileName.textContent = displaySourceFileName();
  dom.exportFileName.textContent = exportFileName("yaml");
  const message = state.code.loading
    ? "同期中…"
    : state.validation.errors.length
      ? state.validation.errors.length + " 件の修正項目があります"
      : state.code.dirty
        ? "未適用の編集があります"
        : state.code.stale
          ? "GUIの内容を更新できます"
          : "GUIと同期済み";
  dom.codeStatus.textContent = message;
  dom.codeEditor.readOnly = state.code.loading;
  dom.codeFormatYaml.disabled = state.code.loading;
  dom.codeFormatJson.disabled = state.code.loading;
  dom.codeFormatButton.disabled = state.code.loading;
  dom.codeValidateButton.disabled = state.code.loading;
  dom.codeApplyButton.disabled = state.code.loading;
  dom.guiModeButton.disabled = state.code.loading;
  renderCodeValidation();
}

function renderTabState() {
  uiRoot.querySelectorAll(".tab").forEach(function (tab) {
    tab.classList.toggle("active", tab.dataset.tab === state.activeTab);
  });
  uiRoot.querySelectorAll(".tab-pane").forEach(function (pane) {
    pane.classList.toggle("active", pane.id === state.activeTab + "-pane");
  });
}

function sidebarItem(type, id, icon, name, detail, iconClass) {
  const selected = state.selected.type === type && state.selected.id === id ? " selected" : "";
  return '<button class="sidebar-item selectable' + selected + '" data-select-type="' + type
    + '" data-select-id="' + escapeHtml(id) + '" type="button">'
    + '<span class="sidebar-icon ' + (iconClass || "") + '">' + icon + "</span>"
    + '<span class="sidebar-item-copy"><strong>' + escapeHtml(name) + "</strong><small>"
    + escapeHtml(detail) + "</small></span></button>";
}

function renderSidebar() {
  if (!state.scenario) {
    return;
  }
  dom.scenarioName.textContent = state.scenario.name || state.scenario.id;
  dom.homeSummary.textContent = state.scenario.id;
  uiRoot.querySelector(".home-card").classList.toggle("selected", state.selected.type === "home");
  dom.roomList.innerHTML = state.scenario.rooms.map(function (room) {
    const suffix = room.is_outside ? "屋外" : "定員 " + room.capacity;
    return sidebarItem("room", room.id, "⌂", room.name, suffix);
  }).join("");
  dom.residentList.innerHTML = state.scenario.residents.map(function (resident) {
    const initialRoom = state.scenario.rooms.find(function (room) {
      return room.id === resident.initial_room_id;
    });
    return sidebarItem(
      "resident",
      resident.id,
      "●",
      resident.name,
      initialRoom ? initialRoom.name : resident.initial_room_id,
      "person",
    );
  }).join("");
  dom.activityList.innerHTML = state.scenario.activities.map(function (activity) {
    const room = state.scenario.rooms.find(function (candidate) {
      return candidate.id === activity.room_id;
    });
    return sidebarItem(
      "activity",
      activity.id,
      "◆",
      activity.name,
      room ? room.name : activity.room_id,
      "activity",
    );
  }).join("");
  uiRoot.querySelectorAll("[data-select-type]").forEach(function (button) {
    button.addEventListener("click", function () {
      const type = button.dataset.selectType;
      if (type === "home") {
        selectItem("home", null, "layout");
        return;
      }
      const tab = type === "resident" ? "people" : type === "activity" ? "activities" : "layout";
      selectItem(type, button.dataset.selectId, tab);
    });
  });
  const connecting = state.connectingFrom !== null;
  dom.connectButton.classList.toggle("connecting", connecting);
  dom.connectButton.textContent = connecting ? "× 接続モードを終了" : "⌁ 部屋をつなぐ";
  if (state.connectingFrom === "") {
    dom.connectionHint.textContent = "最初の部屋を選択してください。";
  } else if (state.connectingFrom) {
    const room = state.scenario.rooms.find(function (candidate) {
      return candidate.id === state.connectingFrom;
    });
    dom.connectionHint.textContent = (room ? room.name : "この部屋") + " とつなぐ部屋を選択してください。";
  } else {
    dom.connectionHint.textContent = "部屋間の移動経路を設定できます。";
  }
}

function roomCenter(roomId) {
  const position = state.scenario.editor_layout.room_positions[roomId];
  if (!position) {
    return null;
  }
  return {
    x: position.x + position.width / 2,
    y: position.y + position.height / 2,
  };
}

function renderConnections() {
  if (!state.scenario) {
    return;
  }
  const fragments = [];
  state.scenario.connections.forEach(function (connection, index) {
    const source = roomCenter(connection.source);
    const target = roomCenter(connection.target);
    if (!source || !target) {
      return;
    }
    const middleX = (source.x + target.x) / 2;
    const middleY = (source.y + target.y) / 2;
    const selected = state.selected.type === "connection" && Number(state.selected.id) === index;
    const label = Math.round(asNumber(connection.travel_seconds, 0) * 10) / 10 + " 秒";
    fragments.push(
      '<g class="connection-group' + (selected ? " selected" : "") + '" data-connection-index="' + index + '">'
      + '<line class="connection-hit" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x
      + '" y2="' + target.y + '"></line>'
      + '<line class="connection-line" x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x
      + '" y2="' + target.y + '"></line>'
      + '<rect class="connection-label-bg" x="' + (middleX - 5.1) + '" y="' + (middleY - 2.65)
      + '" width="10.2" height="4.7" rx="1.2"></rect>'
      + '<text class="connection-label" x="' + middleX + '" y="' + (middleY + 1.05) + '">'
      + label + "</text></g>",
    );
  });
  dom.connectionLayer.innerHTML = fragments.join("");
  dom.connectionLayer.querySelectorAll(".connection-group").forEach(function (group) {
    group.addEventListener("click", function (event) {
      event.stopPropagation();
      selectItem("connection", Number(group.dataset.connectionIndex), "layout");
    });
  });
}

function renderLayout() {
  if (!state.scenario) {
    return;
  }
  ensureLayout();
  dom.floorplanEmpty.hidden = state.scenario.rooms.length > 0;
  const fragments = state.scenario.rooms.map(function (room) {
    const position = state.scenario.editor_layout.room_positions[room.id];
    const selected = state.selected.type === "room" && state.selected.id === room.id;
    const isSource = state.connectingFrom === room.id;
    const deviceMarkup = room.devices.map(function (device) {
      const devicePosition = state.scenario.editor_layout.device_positions[device.id];
      const deviceSelected = state.selected.type === "device" && state.selected.id === device.id;
      return '<button class="device' + (deviceSelected ? " selected" : "") + '" data-device-id="'
        + escapeHtml(device.id) + '" data-device-type="' + escapeHtml(device.type) + '" type="button"'
        + ' style="left:' + devicePosition.x + "%;top:" + devicePosition.y + '%;transform:translate(-50%,-50%);">'
        + deviceIcon(device.type) + '<span class="device-tooltip">' + escapeHtml(device.name)
        + " · " + escapeHtml(device.id) + "</span></button>";
    }).join("");
    return '<article class="room' + (room.is_outside ? " outside" : "") + (selected ? " selected" : "")
      + (isSource ? " connection-source" : "") + '" data-room-id="' + escapeHtml(room.id) + '"'
      + ' style="left:' + position.x + "%;top:" + position.y + "%;width:" + position.width
      + "%;height:" + position.height + '%;">'
      + '<div class="room-heading"><div><strong>' + escapeHtml(room.name) + "</strong><small>"
      + escapeHtml(room.id) + '</small></div><span class="room-capacity">'
      + (room.is_outside ? "屋外" : "定員 " + room.capacity) + "</span></div>"
      + deviceMarkup + '<span class="resize-handle" title="部屋の大きさを変更"></span></article>';
  });
  dom.roomLayer.innerHTML = fragments.join("");
  dom.roomLayer.querySelectorAll(".room").forEach(function (roomElement) {
    roomElement.addEventListener("pointerdown", function (event) {
      if (event.target.closest(".device") || event.target.closest(".resize-handle")) {
        return;
      }
      onRoomPointerDown(event, roomElement.dataset.roomId, roomElement);
    });
    roomElement.querySelector(".resize-handle").addEventListener("pointerdown", function (event) {
      event.stopPropagation();
      onResizePointerDown(event, roomElement.dataset.roomId, roomElement);
    });
    roomElement.querySelectorAll(".device").forEach(function (deviceElement) {
      deviceElement.addEventListener("pointerdown", function (event) {
        event.stopPropagation();
        onDevicePointerDown(
          event,
          deviceElement.dataset.deviceId,
          roomElement.dataset.roomId,
          deviceElement,
          roomElement,
        );
      });
      deviceElement.addEventListener("click", function (event) {
        event.stopPropagation();
        if (!state.drag) {
          selectItem("device", deviceElement.dataset.deviceId, "layout");
        }
      });
    });
  });
  renderConnections();
}

function renderPeople() {
  if (!state.scenario) {
    return;
  }
  if (!state.scenario.residents.length) {
    dom.personGrid.innerHTML = '<div class="empty-state">まだ人物がいません。<br>「人物を追加」から住人を作成できます。</div>';
    return;
  }
  dom.personGrid.innerHTML = state.scenario.residents.map(function (resident) {
    const room = state.scenario.rooms.find(function (candidate) {
      return candidate.id === resident.initial_room_id;
    });
    const selected = state.selected.type === "resident" && state.selected.id === resident.id;
    return '<article class="person-card' + (selected ? " selected" : "") + '" data-resident-card="'
      + escapeHtml(resident.id) + '"><div class="card-topline"><div class="card-ident"><span class="card-icon">●</span>'
      + "<div><strong>" + escapeHtml(resident.name) + "</strong><small>" + escapeHtml(resident.id)
      + '</small></div></div><span class="card-badge">優先度 ' + resident.priority + "</span></div>"
      + '<div class="card-metrics"><div class="metric"><strong>' + escapeHtml(room ? room.name : resident.initial_room_id)
      + '</strong><span>初期位置</span></div><div class="metric"><strong>' + routineCount(resident)
      + '</strong><span>週間の行動数</span></div></div><div class="card-footer"><span>速度 '
      + resident.duration_multiplier + ' ×</span><button class="link-button" type="button">詳細を編集</button></div></article>';
  }).join("");
  dom.personGrid.querySelectorAll("[data-resident-card]").forEach(function (card) {
    card.addEventListener("click", function () {
      selectItem("resident", card.dataset.residentCard, "people");
    });
  });
}

function renderActivities() {
  if (!state.scenario) {
    return;
  }
  if (!state.scenario.activities.length) {
    dom.activityGrid.innerHTML = '<div class="empty-state">行動がありません。<br>ルーティンに追加する前に、行動を作成してください。</div>';
    return;
  }
  dom.activityGrid.innerHTML = state.scenario.activities.map(function (activity) {
    const room = state.scenario.rooms.find(function (candidate) {
      return candidate.id === activity.room_id;
    });
    const selected = state.selected.type === "activity" && state.selected.id === activity.id;
    return '<article class="activity-card' + (selected ? " selected" : "") + '" data-activity-card="'
      + escapeHtml(activity.id) + '"><div class="card-topline"><div class="card-ident"><span class="card-icon">◆</span>'
      + "<div><strong>" + escapeHtml(activity.name) + "</strong><small>" + escapeHtml(activity.adl_label)
      + '</small></div></div><span class="card-badge">' + activity.base_duration_minutes + " 分</span></div>"
      + '<div class="card-metrics"><div class="metric"><strong>' + escapeHtml(room ? room.name : activity.room_id)
      + '</strong><span>場所</span></div><div class="metric"><strong>' + activity.device_actions.length
      + '</strong><span>デバイス操作</span></div></div><div class="card-footer"><span>ばらつき '
      + Math.round(activity.variation_fraction * 100) + '%</span><button class="link-button" type="button">詳細を編集</button></div></article>';
  }).join("");
  dom.activityGrid.querySelectorAll("[data-activity-card]").forEach(function (card) {
    card.addEventListener("click", function () {
      selectItem("activity", card.dataset.activityCard, "activities");
    });
  });
}

function inputField(label, dataAttribute, value, options) {
  const settings = options || {};
  const type = settings.type || "text";
  const span = settings.span ? " span-two" : "";
  const extra = settings.extra ? " " + settings.extra : "";
  return '<div class="field' + span + '"><label>' + escapeHtml(label) + '</label><input '
    + dataAttribute + ' type="' + type + '" value="' + escapeHtml(value) + '"' + extra + "></div>";
}

function selectOptions(options, selected, includeEmpty) {
  let markup = includeEmpty ? '<option value="">未設定</option>' : "";
  markup += options.map(function (option) {
    const value = typeof option === "string" ? option : option.value;
    const label = typeof option === "string" ? option : option.label;
    const isSelected = String(value) === String(selected) ? " selected" : "";
    return '<option value="' + escapeHtml(value) + '"' + isSelected + ">" + escapeHtml(label) + "</option>";
  }).join("");
  return markup;
}

function selectField(label, dataAttribute, options, selected, includeEmpty, span) {
  return '<div class="field' + (span ? " span-two" : "") + '"><label>' + escapeHtml(label)
    + '</label><select ' + dataAttribute + ">" + selectOptions(options, selected, includeEmpty)
    + "</select></div>";
}

function textareaField(label, dataAttribute, value, description) {
  return '<div class="field"><label>' + escapeHtml(label) + '</label><textarea ' + dataAttribute + ">"
    + escapeHtml(value) + "</textarea>" + (description ? '<p class="helper-text">' + escapeHtml(description)
    + "</p>" : "") + "</div>";
}

function section(title, body, description) {
  return '<section class="form-section"><h3 class="form-section-title">' + title + "</h3>"
    + (description ? '<p class="form-section-description">' + description + "</p>" : "") + body + "</section>";
}

function fieldError(path) {
  return state.validation.errors.some(function (error) {
    return error.path.indexOf(path) >= 0;
  }) ? " invalid" : "";
}

function renderHomeInspector() {
  dom.inspectorTitle.textContent = "ホーム設定";
  const scenario = state.scenario;
  const stats = [
    ["部屋", scenario.rooms.length],
    ["デバイス", allDevices().length],
    ["人物", scenario.residents.length],
    ["行動", scenario.activities.length],
  ].map(function (item) {
    return '<div class="metric"><strong>' + item[1] + "</strong><span>" + item[0] + "</span></div>";
  }).join("");
  dom.inspectorContent.innerHTML = section(
    "基本情報",
    '<div class="field-grid">' + inputField("シナリオID", 'data-home-field="id"', scenario.id)
    + inputField("表示名", 'data-home-field="name"', scenario.name)
    + inputField("開始日時（UTCオフセット必須）", 'data-home-field="start_datetime"', scenario.start_datetime, { span: true })
    + "</div>",
    "この情報は書き出すシナリオに保存されます。",
  ) + section(
    "構成",
    '<div class="card-metrics">' + stats + "</div>",
    "間取りの座標とデバイス位置は editor_layout としてシナリオに保存されます。",
  ) + section(
    "確認",
    '<button class="button primary full-width" id="inspector-validate-button" type="button">シナリオを検証</button>',
    "保存前に既存の Hestia スキーマで検証します。",
  );
  dom.inspectorContent.querySelectorAll("[data-home-field]").forEach(function (input) {
    input.addEventListener("input", function () {
      scenario[input.dataset.homeField] = input.value;
      markDirty();
    });
    input.addEventListener("change", renderSidebar);
  });
  dom.inspectorContent.querySelector("#inspector-validate-button").addEventListener("click", validateScenario);
}

function renderRoomInspector(room) {
  dom.inspectorTitle.textContent = room.name;
  const connections = state.scenario.connections
    .map(function (connection, index) {
      return { connection: connection, index: index };
    })
    .filter(function (entry) {
      return entry.connection.source === room.id || entry.connection.target === room.id;
    });
  const devices = room.devices.length ? '<div class="device-list">' + room.devices.map(function (device) {
    return '<button class="device-row" data-select-device="' + escapeHtml(device.id) + '" type="button"><span class="device-row-copy">'
      + '<strong><span class="row-type-icon">' + deviceIcon(device.type) + "</span>" + escapeHtml(device.name)
      + "</strong><small>" + escapeHtml(device.id) + " · " + escapeHtml(deviceLabel(device.type))
      + "</small></span><span>›</span></button>";
  }).join("") + "</div>" : '<div class="empty-state">デバイスはありません。</div>';
  const paths = connections.length ? '<div class="connection-list">' + connections.map(function (entry) {
    const other = entry.connection.source === room.id ? entry.connection.target : entry.connection.source;
    const target = state.scenario.rooms.find(function (candidate) {
      return candidate.id === other;
    });
    return '<button class="connection-row" data-select-connection="' + entry.index + '" type="button"><span class="connection-row-copy"><strong>'
      + escapeHtml(target ? target.name : other) + "</strong><small>" + entry.connection.travel_seconds
      + " 秒" + (entry.connection.door_sensor_id ? " · ドアあり" : "") + "</small></span><span>›</span></button>";
  }).join("") + "</div>" : '<div class="empty-state">接続がありません。<br>「部屋をつなぐ」で追加できます。</div>';
  dom.inspectorContent.innerHTML = section(
    "部屋の情報",
    '<div class="field-grid">' + inputField("部屋ID", 'data-room-field="id"', room.id)
    + inputField("表示名", 'data-room-field="name"', room.name)
    + inputField("定員", 'data-room-field="capacity"', room.capacity, { type: "number", extra: 'min="1" step="1"' })
    + '<div class="field"><label>屋外</label><label class="checkbox-field"><input data-room-field="is_outside" type="checkbox"'
    + (room.is_outside ? " checked" : "") + ">この部屋を屋外にする</label></div></div>",
    "屋外の部屋は必ず1つ必要です。",
  ) + section(
    "デバイス",
    devices + '<div class="inline-actions"><button class="button outline small" id="add-device-inspector-button" type="button">＋ デバイスを追加</button></div>',
    "デバイスは部屋の中でドラッグして位置を変えられます。",
  ) + section(
    "移動経路",
    paths,
    "線を選択すると移動時間とドアセンサーを編集できます。",
  ) + section(
    "削除",
    '<button class="button danger full-width" id="delete-room-button" type="button">この部屋を削除</button>',
    "関連する行動・接続・配置情報も整理されます。",
  );
  dom.inspectorContent.querySelectorAll("[data-room-field]").forEach(function (input) {
    const field = input.dataset.roomField;
    if (field === "id") {
      input.addEventListener("change", function () {
        renameRoom(room.id, input.value);
      });
      return;
    }
    if (field === "is_outside") {
      input.addEventListener("change", function () {
        setOutsideRoom(room.id, input.checked);
      });
      return;
    }
    input.addEventListener("input", function () {
      room[field] = field === "capacity" ? Math.max(1, Math.round(asNumber(input.value, 1))) : input.value;
      markDirty();
    });
    input.addEventListener("change", render);
  });
  dom.inspectorContent.querySelectorAll("[data-select-device]").forEach(function (button) {
    button.addEventListener("click", function () {
      selectItem("device", button.dataset.selectDevice, "layout");
    });
  });
  dom.inspectorContent.querySelectorAll("[data-select-connection]").forEach(function (button) {
    button.addEventListener("click", function () {
      selectItem("connection", Number(button.dataset.selectConnection), "layout");
    });
  });
  dom.inspectorContent.querySelector("#add-device-inspector-button").addEventListener("click", function () {
    addDevice(room.id);
  });
  dom.inspectorContent.querySelector("#delete-room-button").addEventListener("click", function () {
    deleteRoom(room.id);
  });
}

function renderDeviceInspector(entry) {
  const device = entry.device;
  const room = entry.room;
  dom.inspectorTitle.textContent = device.name;
  const roomOptions = state.scenario.rooms.map(function (candidate) {
    return { value: candidate.id, label: candidate.name + " (" + candidate.id + ")" };
  });
  const initialStateOptions = ["", "ON", "OFF"];
  if (["DoorSensor", "ContactSensor"].includes(device.type)) {
    initialStateOptions.splice(1, 2, "OPEN", "CLOSE");
  }
  const zoneOptions = zonesForRoom(room.id).map(function (zone) {
    return { value: zone.id, label: zone.name + " (" + zone.id + ")" };
  });
  dom.inspectorContent.innerHTML = section(
    "デバイスの情報",
    '<div class="field-grid">' + inputField("デバイスID", 'data-device-field="id"', device.id)
    + inputField("表示名", 'data-device-field="name"', device.name)
    + selectField("種類", 'data-device-field="type"', DEVICE_TYPES, device.type, false)
    + selectField("初期状態", 'data-device-field="initial_state"', initialStateOptions, device.initial_state || "", true)
    + selectField("ゾーン", 'data-device-field="zone_id"', zoneOptions, device.zone_id || "", true, true)
    + "</div>",
    "IDは住宅全体で一意です。種類により設定できる初期状態が変わります。",
  ) + section(
    "初期属性",
    textareaField(
      "JSON",
      'data-device-json="initial_attributes"',
      JSON.stringify(device.initial_attributes || {}, null, 2),
      '例: {"brightness": 60, "color_temperature": 3000}',
    ),
    "照明の明るさやテレビの音量など、初期の追加属性を指定できます。",
  ) + section(
    "配置",
    selectField("所属部屋", 'id="device-room-select"', roomOptions, room.id, false)
    + '<p class="form-section-description">所属部屋を変更するか、間取りタブでアイコンをドラッグして部屋内の表示位置を調整できます。</p>'
    + '<button class="button outline full-width" id="focus-device-room-button" type="button">間取りで表示</button>',
    "所属部屋を変えた場合は、行動や接続からの参照も検証してください。",
  ) + section(
    "削除",
    '<button class="button danger full-width" id="delete-device-button" type="button">このデバイスを削除</button>',
    "行動、好み、ドア接続からの参照も整理されます。",
  );
  dom.inspectorContent.querySelectorAll("[data-device-field]").forEach(function (input) {
    const field = input.dataset.deviceField;
    if (field === "id") {
      input.addEventListener("change", function () {
        renameDevice(device.id, input.value);
      });
      return;
    }
    input.addEventListener("change", function () {
      if (field === "initial_state") {
        if (input.value) {
          device.initial_state = input.value;
        } else {
          delete device.initial_state;
        }
      } else if (field === "zone_id") {
        if (input.value) {
          device.zone_id = input.value;
        } else {
          delete device.zone_id;
        }
      } else {
        device[field] = input.value;
        if (field === "type" && device.initial_state) {
          const allowed = ["DoorSensor", "ContactSensor"].includes(input.value)
            ? ["OPEN", "CLOSE"] : ["ON", "OFF"];
          if (!allowed.includes(device.initial_state)) {
            delete device.initial_state;
          }
        }
      }
      markDirty();
      render();
    });
  });
  const jsonInput = dom.inspectorContent.querySelector("[data-device-json]");
  jsonInput.addEventListener("change", function () {
    try {
      const attributes = JSON.parse(jsonInput.value || "{}");
      if (!attributes || Array.isArray(attributes) || typeof attributes !== "object") {
        throw new Error("属性はJSONオブジェクトで指定してください。");
      }
      device.initial_attributes = attributes;
      jsonInput.classList.remove("invalid");
      markDirty();
    } catch (error) {
      jsonInput.classList.add("invalid");
      showToast(error.message || "JSONの形式を確認してください。", true);
    }
  });
  dom.inspectorContent.querySelector("#device-room-select").addEventListener("change", function (event) {
    moveDeviceToRoom(device.id, event.target.value);
  });
  dom.inspectorContent.querySelector("#focus-device-room-button").addEventListener("click", function () {
    selectItem("room", room.id, "layout");
  });
  dom.inspectorContent.querySelector("#delete-device-button").addEventListener("click", function () {
    deleteDevice(device.id);
  });
}

function renderConnectionInspector(entry) {
  const connection = entry.connection;
  dom.inspectorTitle.textContent = "移動経路";
  const rooms = state.scenario.rooms.map(function (room) {
    return { value: room.id, label: room.name + " (" + room.id + ")" };
  });
  const doors = doorDevices().map(function (entry) {
    return { value: entry.device.id, label: entry.device.name + " (" + entry.device.id + ")" };
  });
  dom.inspectorContent.innerHTML = section(
    "接続",
    '<div class="field-grid">' + selectField("出発部屋", 'data-connection-field="source"', rooms, connection.source, false)
    + selectField("到着部屋", 'data-connection-field="target"', rooms, connection.target, false)
    + inputField("移動時間（秒）", 'data-connection-field="travel_seconds"', connection.travel_seconds, { type: "number", extra: 'min="0" step="0.1"' })
    + selectField("ドアセンサー", 'data-connection-field="door_sensor_id"', doors, connection.door_sensor_id || "", true)
    + "</div>",
    "線をクリックしても選択できます。移動時間は部屋の見た目の距離とは独立です。",
  ) + section(
    "削除",
    '<button class="button danger full-width" id="delete-connection-button" type="button">この接続を削除</button>',
    "全ての部屋が接続された状態を保つ必要があります。",
  );
  dom.inspectorContent.querySelectorAll("[data-connection-field]").forEach(function (input) {
    input.addEventListener("change", function () {
      const field = input.dataset.connectionField;
      if (field === "travel_seconds") {
        connection[field] = Math.max(0, asNumber(input.value, 0));
      } else if (field === "door_sensor_id") {
        if (input.value) {
          connection[field] = input.value;
        } else {
          delete connection[field];
        }
      } else {
        connection[field] = input.value;
      }
      markDirty();
      render();
    });
  });
  dom.inspectorContent.querySelector("#delete-connection-button").addEventListener("click", function () {
    deleteConnection(entry.index);
  });
}

function routineMarkup(resident) {
  const day = state.routineDays[resident.id] || "monday";
  const routine = resident.weekly_routine[day] || [];
  const activityOptions = state.scenario.activities.map(function (activity) {
    return { value: activity.id, label: activity.name + " (" + activity.id + ")" };
  });
  const tabs = DAYS.map(function (item) {
    return '<button class="day-tab' + (item[0] === day ? " active" : "") + '" data-routine-day="' + item[0]
      + '" type="button">' + item[1] + "</button>";
  }).join("");
  const entries = routine.length ? routine.map(function (item, index) {
    const entry = routineEntry(item);
    const schedule = formatMinutes(entry.scheduled_start_minute);
    const probability = entry.inclusion_probability === undefined ? 1 : entry.inclusion_probability;
    return '<div class="routine-entry" data-routine-index="' + index + '"><div class="routine-entry-grid">'
      + '<div class="field compact-field"><label>行動</label><select data-routine-field="activity_id" data-routine-index="'
      + index + '">' + selectOptions(activityOptions, entry.activity_id, false) + "</select></div>"
      + '<div class="field compact-field"><label>開始時刻</label><input data-routine-field="scheduled_start_minute" data-routine-index="'
      + index + '" type="time" value="' + schedule + '"></div></div><div class="routine-entry-meta">'
      + '<div class="field compact-field"><label>実行確率</label><input data-routine-field="inclusion_probability" data-routine-index="'
      + index + '" type="number" min="0" max="1" step="0.05" value="' + probability + '"></div>'
      + '<div class="field compact-field"><label>開始前の間隔</label><input disabled type="text" value="高度な設定"></div>'
      + '</div><div class="routine-entry-actions"><button class="icon-button" data-routine-action="up" data-routine-index="'
      + index + '" type="button" title="上へ">↑</button><button class="icon-button" data-routine-action="down" data-routine-index="'
      + index + '" type="button" title="下へ">↓</button><button class="icon-button" data-routine-action="delete" data-routine-index="'
      + index + '" type="button" title="削除">×</button></div></div>';
  }).join("") : '<div class="empty-state">この曜日に行動はありません。</div>';
  return '<div class="routine-day-tabs">' + tabs + '</div><div class="routine-list">' + entries
    + '</div><div class="inline-actions" style="margin-top:9px"><button class="button outline small" id="add-routine-entry-button" type="button">＋ 行動を追加</button></div>';
}

function renderResidentInspector(resident) {
  dom.inspectorTitle.textContent = resident.name;
  const rooms = state.scenario.rooms.map(function (room) {
    return { value: room.id, label: room.name + " (" + room.id + ")" };
  });
  const zoneOptions = zonesForRoom(resident.initial_room_id).map(function (zone) {
    return { value: zone.id, label: zone.name + " (" + zone.id + ")" };
  });
  dom.inspectorContent.innerHTML = section(
    "人物の情報",
    '<div class="field-grid">' + inputField("人物ID", 'data-resident-field="id"', resident.id)
    + inputField("表示名", 'data-resident-field="name"', resident.name)
    + selectField("初期位置", 'data-resident-field="initial_room_id"', rooms, resident.initial_room_id, false)
    + selectField("初期ゾーン", 'data-resident-field="initial_zone_id"', zoneOptions, resident.initial_zone_id || "", true)
    + inputField("優先度", 'data-resident-field="priority"', resident.priority, { type: "number", extra: 'step="1"' })
    + inputField("行動時間倍率", 'data-resident-field="duration_multiplier"', resident.duration_multiplier, { type: "number", extra: 'min="0.01" step="0.01"' })
    + inputField("副次行動係数", 'data-resident-field="secondary_activity_factor"', resident.secondary_activity_factor, { type: "number", extra: 'min="0" max="1" step="0.05"', span: true })
    + "</div>",
    "優先度が高い人物の好みが、共有デバイス使用時に優先されます。",
  ) + section(
    "デバイスの好み",
    textareaField(
      "JSON",
      'data-resident-json="preferences"',
      JSON.stringify(resident.preferences || {}, null, 2),
      '例: {"L_LIVING": {"brightness": 45}}',
    ),
  ) + section(
    "週間ルーティン",
    routineMarkup(resident),
    "曜日を切り替えて、行動の順番・予定時刻・実行確率を編集できます。",
  ) + section(
    "削除",
    '<button class="button danger full-width" id="delete-resident-button" type="button">この人物を削除</button>',
  );
  dom.inspectorContent.querySelectorAll("[data-resident-field]").forEach(function (input) {
    const field = input.dataset.residentField;
    if (field === "id") {
      input.addEventListener("change", function () {
        renameResident(resident.id, input.value);
      });
      return;
    }
    input.addEventListener("change", function () {
      if (field === "initial_room_id") {
        resident.initial_room_id = input.value;
        const zones = zonesForRoom(input.value);
        if (!zones.some(function (zone) { return zone.id === resident.initial_zone_id; })) {
          delete resident.initial_zone_id;
        }
      } else if (field === "initial_zone_id") {
        if (input.value) {
          resident.initial_zone_id = input.value;
        } else {
          delete resident.initial_zone_id;
        }
      } else if (field === "priority") {
        resident.priority = Math.round(asNumber(input.value, 0));
      } else {
        resident[field] = asNumber(input.value, field === "duration_multiplier" ? 1 : 0);
      }
      markDirty();
      render();
    });
  });
  const jsonInput = dom.inspectorContent.querySelector("[data-resident-json]");
  jsonInput.addEventListener("change", function () {
    try {
      const preferences = JSON.parse(jsonInput.value || "{}");
      if (!preferences || Array.isArray(preferences) || typeof preferences !== "object") {
        throw new Error("好みはJSONオブジェクトで指定してください。");
      }
      resident.preferences = preferences;
      jsonInput.classList.remove("invalid");
      markDirty();
    } catch (error) {
      jsonInput.classList.add("invalid");
      showToast(error.message || "JSONの形式を確認してください。", true);
    }
  });
  dom.inspectorContent.querySelectorAll("[data-routine-day]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.routineDays[resident.id] = button.dataset.routineDay;
      renderInspector();
    });
  });
  dom.inspectorContent.querySelectorAll("[data-routine-field]").forEach(function (input) {
    input.addEventListener("change", function () {
      const day = state.routineDays[resident.id] || "monday";
      const index = Number(input.dataset.routineIndex);
      const entry = ensureRoutineEntry(resident, day, index);
      if (input.dataset.routineField === "scheduled_start_minute") {
        const value = minutesFromTime(input.value);
        if (value === null) {
          delete entry.scheduled_start_minute;
        } else {
          entry.scheduled_start_minute = value;
        }
      } else if (input.dataset.routineField === "inclusion_probability") {
        entry.inclusion_probability = clamp(asNumber(input.value, 1), 0, 1);
      } else {
        entry.activity_id = input.value;
      }
      markDirty();
    });
  });
  dom.inspectorContent.querySelectorAll("[data-routine-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      const day = state.routineDays[resident.id] || "monday";
      const index = Number(button.dataset.routineIndex);
      const routine = resident.weekly_routine[day];
      if (button.dataset.routineAction === "delete") {
        routine.splice(index, 1);
      } else if (button.dataset.routineAction === "up" && index > 0) {
        const item = routine.splice(index, 1)[0];
        routine.splice(index - 1, 0, item);
      } else if (button.dataset.routineAction === "down" && index < routine.length - 1) {
        const item = routine.splice(index, 1)[0];
        routine.splice(index + 1, 0, item);
      }
      markDirty();
      renderInspector();
      renderPeople();
    });
  });
  dom.inspectorContent.querySelector("#add-routine-entry-button").addEventListener("click", function () {
    if (!state.scenario.activities.length) {
      showToast("先に行動を1つ以上追加してください。", true);
      return;
    }
    const day = state.routineDays[resident.id] || "monday";
    resident.weekly_routine[day].push({ activity_id: state.scenario.activities[0].id });
    markDirty();
    renderInspector();
    renderPeople();
  });
  dom.inspectorContent.querySelector("#delete-resident-button").addEventListener("click", function () {
    deleteResident(resident.id);
  });
}

function renderActivityInspector(activity) {
  dom.inspectorTitle.textContent = activity.name;
  const rooms = state.scenario.rooms.map(function (room) {
    return { value: room.id, label: room.name + " (" + room.id + ")" };
  });
  const actions = activity.device_actions.length ? '<div class="action-list">' + activity.device_actions.map(function (action, index) {
    const devices = actuatorDevices(activity.room_id).map(function (entry) {
      return { value: entry.device.id, label: entry.device.name + " (" + entry.device.id + ")" };
    });
    return '<div class="action-row"><div class="action-row-copy"><strong>操作 ' + (index + 1)
      + '</strong><small>行動中に保持するデバイス状態</small></div><button class="icon-button" data-delete-action="'
      + index + '" type="button" title="削除">×</button><div class="field compact-field"><label>デバイス</label><select data-action-field="device_id" data-action-index="'
      + index + '">' + selectOptions(devices, action.device_id, false) + '</select></div><div class="field compact-field"><label>状態</label><select data-action-field="state" data-action-index="'
      + index + '">' + selectOptions(["ON", "OFF"], action.state, false) + "</select></div></div>";
  }).join("") + "</div>" : '<div class="empty-state">この行動にはデバイス操作がありません。</div>';
  dom.inspectorContent.innerHTML = section(
    "行動の情報",
    '<div class="field-grid">' + inputField("行動ID", 'data-activity-field="id"', activity.id)
    + inputField("表示名", 'data-activity-field="name"', activity.name)
    + selectField("場所", 'data-activity-field="room_id"', rooms, activity.room_id, false)
    + inputField("基本時間（分）", 'data-activity-field="base_duration_minutes"', activity.base_duration_minutes, { type: "number", extra: 'min="0.1" step="1"' })
    + inputField("時間のばらつき", 'data-activity-field="variation_fraction"', activity.variation_fraction, { type: "number", extra: 'min="0" max="1" step="0.05"' })
    + inputField("ADLラベル", 'data-activity-field="adl_label"', activity.adl_label)
    + "</div>",
    "この行動を人物の週間ルーティンに登録できます。",
  ) + section(
    "デバイス操作",
    actions + '<div class="inline-actions" style="margin-top:9px"><button class="button outline small" id="add-device-action-button" type="button">＋ デバイス操作を追加</button></div>',
    "人感・接触・ドアセンサーは直接操作できません。",
  ) + section(
    "削除",
    '<button class="button danger full-width" id="delete-activity-button" type="button">この行動を削除</button>',
    "全住人の週間ルーティンと副次活動からも取り除かれます。",
  );
  dom.inspectorContent.querySelectorAll("[data-activity-field]").forEach(function (input) {
    const field = input.dataset.activityField;
    if (field === "id") {
      input.addEventListener("change", function () {
        renameActivity(activity.id, input.value);
      });
      return;
    }
    input.addEventListener("change", function () {
      if (field === "base_duration_minutes") {
        activity[field] = Math.max(0.1, asNumber(input.value, 30));
      } else if (field === "variation_fraction") {
        activity[field] = clamp(asNumber(input.value, 0), 0, 1);
      } else {
        activity[field] = input.value;
        if (field === "room_id") {
          activity.device_actions = activity.device_actions.filter(function (action) {
            return actuatorDevices(input.value).some(function (entry) {
              return entry.device.id === action.device_id;
            });
          });
        }
      }
      markDirty();
      render();
    });
  });
  dom.inspectorContent.querySelectorAll("[data-action-field]").forEach(function (input) {
    input.addEventListener("change", function () {
      const action = activity.device_actions[Number(input.dataset.actionIndex)];
      action[input.dataset.actionField] = input.value;
      markDirty();
    });
  });
  dom.inspectorContent.querySelectorAll("[data-delete-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      activity.device_actions.splice(Number(button.dataset.deleteAction), 1);
      markDirty();
      renderInspector();
      renderActivities();
    });
  });
  dom.inspectorContent.querySelector("#add-device-action-button").addEventListener("click", function () {
    const available = actuatorDevices(activity.room_id);
    if (!available.length) {
      showToast("この部屋に操作可能なデバイスがありません。", true);
      return;
    }
    const existingIds = new Set(activity.device_actions.map(function (action) {
      return action.device_id;
    }));
    const selected = available.find(function (entry) {
      return !existingIds.has(entry.device.id);
    });
    if (!selected) {
      showToast("この部屋の操作可能なデバイスはすべて追加済みです。", true);
      return;
    }
    activity.device_actions.push({ device_id: selected.device.id, state: "ON" });
    markDirty();
    renderInspector();
    renderActivities();
  });
  dom.inspectorContent.querySelector("#delete-activity-button").addEventListener("click", function () {
    deleteActivity(activity.id);
  });
}

function renderInspector() {
  if (!state.scenario) {
    return;
  }
  const room = currentRoom();
  const device = currentDevice();
  const resident = currentResident();
  const activity = currentActivity();
  const connection = currentConnection();
  if (room) {
    renderRoomInspector(room);
  } else if (device) {
    renderDeviceInspector(device);
  } else if (resident) {
    renderResidentInspector(resident);
  } else if (activity) {
    renderActivityInspector(activity);
  } else if (connection) {
    renderConnectionInspector(connection);
  } else {
    renderHomeInspector();
  }
  renderValidationReport();
}

function renderValidationReport() {
  const errors = state.validation.errors || [];
  if (!errors.length) {
    dom.validationReport.hidden = true;
    dom.validationReport.innerHTML = "";
    return;
  }
  dom.validationReport.hidden = false;
  dom.validationReport.innerHTML = "<strong>修正が必要な項目</strong><ul>" + errors.slice(0, 8).map(function (error) {
    return "<li><code>" + escapeHtml(error.path) + "</code><br>" + escapeHtml(error.message) + "</li>";
  }).join("") + (errors.length > 8 ? "<li>ほか " + (errors.length - 8) + " 件</li>" : "") + "</ul>";
}

function setInputValue(input, value) {
  if (document.activeElement !== input && input.value !== String(value)) {
    input.value = String(value);
  }
}

function renderRunPane() {
  if (!state.scenario) {
    return;
  }
  const saveName = state.project.fileName || exportFileName("yaml");
  setInputValue(dom.saveFileName, saveName);
  const files = state.project.files;
  if (files.length) {
    dom.runScenarioSelect.innerHTML = files.map(function (file) {
      const label = (file.group === "scenarios" ? "保存済み" : "例") + " · " + file.path;
      return '<option value="' + escapeHtml(file.path) + '">' + escapeHtml(label) + "</option>";
    }).join("");
    if (!files.some(function (file) { return file.path === state.project.selectedPath; })) {
      state.project.selectedPath = files[0].path;
      refreshAutomaticOutputName();
    }
    dom.runScenarioSelect.value = state.project.selectedPath;
  } else {
    dom.runScenarioSelect.innerHTML = '<option value="">先にYAMLを保存してください</option>';
    state.project.selectedPath = "";
  }
  const selected = selectedScenarioFile();
  setInputValue(dom.runDays, state.run.days);
  setInputValue(dom.runSeed, state.run.seed);
  setInputValue(dom.runOutputName, state.run.outputName);
  dom.runOutputPreview.textContent = "outputs/studio/" + (state.run.outputName || "実行名");
  const saveDisabled = !state.scenario || state.project.saving || state.run.running;
  dom.exportYamlButton.disabled = saveDisabled;
  dom.saveYamlButton.disabled = saveDisabled;
  dom.refreshScenariosButton.disabled = state.project.loading || state.run.running;
  dom.runScenarioSelect.disabled = state.project.loading || state.run.running || !files.length;
  dom.runDays.disabled = state.run.running;
  dom.runSeed.disabled = state.run.running;
  dom.runOutputName.disabled = state.run.running;
  dom.runSimulationButton.disabled = state.run.running || state.project.loading || !selected;
  const saveMessage = state.project.saving
    ? "YAMLを保存中です…"
    : state.project.message || (state.project.dirty
      ? "現在の編集はまだプロジェクトへ保存されていません。"
      : "現在の設定はプロジェクトへ保存されています。");
  dom.saveStatus.textContent = saveMessage;
  dom.saveStatus.classList.toggle("error", state.project.error);
  const runMessage = state.run.running
    ? "シミュレーションを実行中です…"
    : state.run.message || (selected
      ? (state.project.dirty
        ? "選択したYAMLを実行します。現在の未保存編集は反映されません。"
        : "実行するYAMLとオプションを確認してください。")
      : "実行するには、YAMLを保存するか一覧から選択してください。");
  dom.runStatus.textContent = runMessage;
  dom.runStatus.classList.toggle("error", state.run.error);
  if (!state.run.result) {
    dom.runResult.hidden = true;
    dom.runResult.innerHTML = "";
    return;
  }
  const result = state.run.result;
  dom.runResult.hidden = false;
  dom.runResult.innerHTML = '<div><span class="eyebrow">生成完了</span><h2>ログを生成しました</h2><p><code>'
    + escapeHtml(result.scenario_path) + "</code> → <code>" + escapeHtml(result.output_dir)
    + '</code></p></div><div class="run-result-metrics"><div><strong>' + escapeHtml(result.event_count)
    + '</strong><span>イベント</span></div><div><strong>' + escapeHtml(result.state_count)
    + '</strong><span>状態ベクトル</span></div><div><strong>' + escapeHtml(result.aruba_count)
    + '</strong><span>Arubaログ</span></div></div><p class="run-hash"><span>SHA-256</span><code>'
    + escapeHtml(result.content_hash) + "</code></p>";
}

async function loadProjectScenarios(preferredPath) {
  if (state.project.loading) {
    return;
  }
  state.project.loading = true;
  state.project.error = false;
  renderRunPane();
  try {
    const result = await request("/api/project-scenarios");
    if (!result.response.ok || !Array.isArray(result.body.files)) {
      throw new Error("scenario list failed");
    }
    state.project.files = result.body.files;
    const preferred = preferredPath || state.project.selectedPath;
    const matchingPath = state.project.files.some(function (file) {
      return file.path === preferred;
    }) ? preferred : null;
    const matchingSource = state.project.files.find(function (file) {
      return file.name === state.sourceFileName;
    });
    state.project.selectedPath = matchingPath
      || (matchingSource ? matchingSource.path : state.project.files[0] ? state.project.files[0].path : "");
    refreshAutomaticOutputName();
  } catch (error) {
    state.project.error = true;
    state.project.message = "YAML一覧を取得できませんでした。";
  } finally {
    state.project.loading = false;
    renderRunPane();
    scheduleComponentWorkspaceSync();
  }
}

async function requestProjectSave(filename, overwrite) {
  return request("/api/project-scenarios/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: state.scenario, filename: filename, overwrite: overwrite }),
  });
}

async function saveCurrentYaml() {
  if (!state.scenario) {
    showToast("Studioの初期化が完了してから保存してください。", true);
    return false;
  }
  if (state.project.saving || state.run.running) {
    return false;
  }
  if (state.editorMode === "code" && state.code.dirty) {
    const applied = await applyCode(false);
    if (!applied) {
      return false;
    }
  }
  const filename = (state.project.fileName || exportFileName("yaml")).trim();
  state.project.saving = true;
  state.project.error = false;
  state.project.message = "";
  renderRunPane();
  try {
    let result = await requestProjectSave(filename, false);
    if (result.response.status === 409) {
      const shouldOverwrite = window.confirm("「" + filename + "」はすでに存在します。上書きしますか？");
      if (!shouldOverwrite) {
        state.project.message = "保存を取り消しました。";
        return false;
      }
      result = await requestProjectSave(filename, true);
    }
    if (!result.response.ok || !result.body.valid) {
      const errors = errorsFromResponse(result.body, saveErrorFallback(result.response));
      state.project.error = true;
      state.project.message = errors[0].message;
      state.validation = { kind: "invalid", errors: errors };
      renderStatus();
      renderValidationReport();
      return false;
    }
    state.scenario = result.body.scenario;
    state.sourceFileName = result.body.filename;
    state.project.fileName = result.body.filename;
    state.project.selectedPath = result.body.scenario_path;
    state.project.dirty = false;
    state.project.message = "scenarios/" + result.body.filename + " に保存しました。";
    state.run.result = null;
    state.run.error = false;
    state.run.message = "";
    state.code.stale = true;
    state.validation = { kind: "valid", errors: [] };
    ensureLayout();
    await loadProjectScenarios(result.body.scenario_path);
    showToast("YAMLをプロジェクトへ保存しました。");
    return true;
  } catch (error) {
    state.project.error = true;
    state.project.message = "YAMLを保存できませんでした。";
    showToast("YAMLを保存できませんでした。", true);
    return false;
  } finally {
    state.project.saving = false;
    render();
    scheduleComponentWorkspaceSync();
  }
}

async function runSimulation() {
  if (state.run.running || !state.project.selectedPath) {
    return;
  }
  state.run.running = true;
  state.run.error = false;
  state.run.message = "";
  state.run.result = null;
  renderRunPane();
  try {
    const result = await request("/api/simulations/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_path: state.project.selectedPath,
        days: state.run.days,
        seed: state.run.seed,
        output_name: state.run.outputName,
      }),
    });
    if (!result.response.ok || !result.body.valid) {
      const errors = errorsFromResponse(result.body, "ログを生成できませんでした。");
      state.run.error = true;
      state.run.message = errors[0].message;
      showToast("ログを生成できませんでした。", true);
      return;
    }
    state.run.result = result.body;
    state.run.message = "ログを生成しました。";
    showToast("ログを生成しました。");
  } catch (error) {
    state.run.error = true;
    state.run.message = "ログを生成できませんでした。";
    showToast("ログを生成できませんでした。", true);
  } finally {
    state.run.running = false;
    renderRunPane();
    scheduleComponentWorkspaceSync();
  }
}

function render() {
  ensureLayout();
  renderStatus();
  renderEvaluationHouseSwitcher();
  renderEditorMode();
  renderSidebar();
  renderTabState();
  renderLayout();
  renderPeople();
  renderActivities();
  renderRunPane();
  renderInspector();
}

function nextId(prefix, ids) {
  let number = 1;
  while (ids.has(prefix + "_" + number)) {
    number += 1;
  }
  return prefix + "_" + number;
}

function addRoom() {
  const ids = new Set(state.scenario.rooms.map(function (room) { return room.id; }));
  const id = nextId("room", ids);
  const room = { id: id, name: "New room", capacity: 2, devices: [] };
  const previous = state.scenario.rooms[0];
  state.scenario.rooms.push(room);
  state.scenario.editor_layout.room_positions[id] = defaultRoomPosition(state.scenario.rooms.length - 1);
  if (previous) {
    state.scenario.connections.push({ source: previous.id, target: id, travel_seconds: 3 });
  }
  markDirty();
  selectItem("room", id, "layout");
}

function addDevice(roomId) {
  const room = state.scenario.rooms.find(function (candidate) { return candidate.id === roomId; });
  if (!room) {
    return;
  }
  const ids = new Set(allDevices().map(function (entry) { return entry.device.id; }));
  const id = nextId("device", ids);
  const device = { id: id, type: "Light", name: "New light" };
  room.devices.push(device);
  state.scenario.editor_layout.device_positions[id] = defaultDevicePosition(room.devices.length - 1);
  markDirty();
  selectItem("device", id, "layout");
}

function moveDeviceToRoom(deviceId, targetRoomId) {
  const entry = allDevices().find(function (candidate) {
    return candidate.device.id === deviceId;
  });
  const target = state.scenario.rooms.find(function (candidate) {
    return candidate.id === targetRoomId;
  });
  if (!entry || !target || entry.room.id === target.id) {
    render();
    return;
  }
  entry.room.devices = entry.room.devices.filter(function (candidate) {
    return candidate.id !== deviceId;
  });
  target.devices.push(entry.device);
  const targetZoneIds = new Set((target.zones || []).map(function (zone) { return zone.id; }));
  if (entry.device.zone_id && !targetZoneIds.has(entry.device.zone_id)) {
    delete entry.device.zone_id;
  }
  state.scenario.editor_layout.device_positions[deviceId] = defaultDevicePosition(
    target.devices.length - 1,
  );
  markDirty();
  selectItem("device", deviceId, "layout");
}

function addResident() {
  const ids = new Set(state.scenario.residents.map(function (resident) { return resident.id; }));
  const id = nextId("resident", ids);
  const initial = state.scenario.rooms.find(function (room) { return !room.is_outside; }) || state.scenario.rooms[0];
  if (!initial) {
    showToast("先に部屋を追加してください。", true);
    return;
  }
  const weeklyRoutine = {};
  DAYS.forEach(function (day) {
    weeklyRoutine[day[0]] = [];
  });
  state.scenario.residents.push({
    id: id,
    name: "New resident",
    initial_room_id: initial.id,
    priority: 0,
    duration_multiplier: 1,
    secondary_activity_factor: 1,
    preferences: {},
    weekly_routine: weeklyRoutine,
  });
  markDirty();
  selectItem("resident", id, "people");
}

function addActivity() {
  const room = state.scenario.rooms.find(function (candidate) { return !candidate.is_outside; }) || state.scenario.rooms[0];
  if (!room) {
    showToast("先に部屋を追加してください。", true);
    return;
  }
  const ids = new Set(state.scenario.activities.map(function (activity) { return activity.id; }));
  const id = nextId("activity", ids);
  state.scenario.activities.push({
    id: id,
    name: "New activity",
    room_id: room.id,
    base_duration_minutes: 30,
    variation_fraction: 0,
    device_actions: [],
    adl_label: "Activity",
  });
  markDirty();
  selectItem("activity", id, "activities");
}

function addConnection(source, target) {
  if (source === target) {
    showToast("異なる2つの部屋を選択してください。", true);
    return false;
  }
  const duplicate = state.scenario.connections.some(function (connection) {
    return (connection.source === source && connection.target === target)
      || (connection.source === target && connection.target === source);
  });
  if (duplicate) {
    showToast("この2部屋はすでに接続されています。", true);
    return false;
  }
  state.scenario.connections.push({ source: source, target: target, travel_seconds: 3 });
  markDirty();
  showToast("移動経路を追加しました。線をクリックして詳細を設定できます。");
  return true;
}

function renameRoom(oldId, newId) {
  const id = newId.trim();
  if (!id || id === oldId) {
    render();
    return;
  }
  if (state.scenario.rooms.some(function (room) { return room.id === id; })) {
    showToast("部屋ID '" + id + "' はすでに使われています。", true);
    render();
    return;
  }
  const room = state.scenario.rooms.find(function (candidate) { return candidate.id === oldId; });
  room.id = id;
  state.scenario.connections.forEach(function (connection) {
    if (connection.source === oldId) connection.source = id;
    if (connection.target === oldId) connection.target = id;
  });
  state.scenario.activities.forEach(function (activity) {
    if (activity.room_id === oldId) activity.room_id = id;
    (activity.micro_action_templates || []).forEach(function (template) {
      (template.steps || []).forEach(function (step) {
        if (step.room_id === oldId) step.room_id = id;
      });
    });
  });
  state.scenario.residents.forEach(function (resident) {
    if (resident.initial_room_id === oldId) resident.initial_room_id = id;
  });
  const positions = state.scenario.editor_layout.room_positions;
  positions[id] = positions[oldId];
  delete positions[oldId];
  if (state.connectingFrom === oldId) state.connectingFrom = id;
  state.selected = { type: "room", id: id };
  markDirty();
  render();
}

function renameDevice(oldId, newId) {
  const id = newId.trim();
  if (!id || id === oldId) {
    render();
    return;
  }
  if (allDevices().some(function (entry) { return entry.device.id === id; })) {
    showToast("デバイスID '" + id + "' はすでに使われています。", true);
    render();
    return;
  }
  const entry = currentDevice() || allDevices().find(function (candidate) {
    return candidate.device.id === oldId;
  });
  entry.device.id = id;
  state.scenario.connections.forEach(function (connection) {
    if (connection.door_sensor_id === oldId) connection.door_sensor_id = id;
  });
  state.scenario.activities.forEach(function (activity) {
    activity.device_actions.forEach(function (action) {
      if (action.device_id === oldId) action.device_id = id;
    });
    (activity.micro_action_templates || []).forEach(function (template) {
      (template.steps || []).forEach(function (step) {
        (step.device_actions || []).forEach(function (action) {
          if (action.device_id === oldId) action.device_id = id;
        });
      });
    });
  });
  state.scenario.residents.forEach(function (resident) {
    if (resident.preferences && Object.prototype.hasOwnProperty.call(resident.preferences, oldId)) {
      resident.preferences[id] = resident.preferences[oldId];
      delete resident.preferences[oldId];
    }
  });
  const profiles = state.scenario.sensor_imperfections && state.scenario.sensor_imperfections.profiles;
  if (profiles && Object.prototype.hasOwnProperty.call(profiles, oldId)) {
    profiles[id] = profiles[oldId];
    delete profiles[oldId];
  }
  const positions = state.scenario.editor_layout.device_positions;
  positions[id] = positions[oldId];
  delete positions[oldId];
  state.selected = { type: "device", id: id };
  markDirty();
  render();
}

function renameResident(oldId, newId) {
  const id = newId.trim();
  if (!id || id === oldId) {
    render();
    return;
  }
  if (state.scenario.residents.some(function (resident) { return resident.id === id; })) {
    showToast("人物ID '" + id + "' はすでに使われています。", true);
    render();
    return;
  }
  const resident = state.scenario.residents.find(function (candidate) { return candidate.id === oldId; });
  resident.id = id;
  state.routineDays[id] = state.routineDays[oldId];
  delete state.routineDays[oldId];
  state.selected = { type: "resident", id: id };
  markDirty();
  render();
}

function renameActivity(oldId, newId) {
  const id = newId.trim();
  if (!id || id === oldId) {
    render();
    return;
  }
  if (state.scenario.activities.some(function (activity) { return activity.id === id; })) {
    showToast("行動ID '" + id + "' はすでに使われています。", true);
    render();
    return;
  }
  const activity = state.scenario.activities.find(function (candidate) { return candidate.id === oldId; });
  activity.id = id;
  state.scenario.activities.forEach(function (candidate) {
    (candidate.secondary_activities || []).forEach(function (rule) {
      if (rule.activity_id === oldId) rule.activity_id = id;
    });
  });
  state.scenario.residents.forEach(function (resident) {
    DAYS.forEach(function (day) {
      resident.weekly_routine[day[0]] = resident.weekly_routine[day[0]].map(function (item) {
        if (typeof item === "string") {
          return item === oldId ? id : item;
        }
        if (item.activity_id === oldId) item.activity_id = id;
        return item;
      });
    });
  });
  state.selected = { type: "activity", id: id };
  markDirty();
  render();
}

function setOutsideRoom(roomId, enabled) {
  const room = state.scenario.rooms.find(function (candidate) { return candidate.id === roomId; });
  if (enabled) {
    state.scenario.rooms.forEach(function (candidate) {
      candidate.is_outside = candidate.id === roomId;
    });
  } else {
    const otherOutside = state.scenario.rooms.some(function (candidate) {
      return candidate.id !== roomId && candidate.is_outside;
    });
    if (!otherOutside) {
      showToast("屋外の部屋を少なくとも1つ指定してください。", true);
      renderInspector();
      return;
    }
    room.is_outside = false;
  }
  markDirty();
  render();
}

function deleteRoom(roomId) {
  if (state.scenario.rooms.length <= 1) {
    showToast("最後の部屋は削除できません。", true);
    return;
  }
  const room = state.scenario.rooms.find(function (candidate) { return candidate.id === roomId; });
  if (!window.confirm("「" + room.name + "」を削除しますか？ 関連する行動と接続も整理されます。")) {
    return;
  }
  const removedDeviceIds = new Set(room.devices.map(function (device) { return device.id; }));
  const removedActivityIds = new Set(state.scenario.activities.filter(function (activity) {
    return activity.room_id === roomId;
  }).map(function (activity) { return activity.id; }));
  state.scenario.rooms = state.scenario.rooms.filter(function (candidate) { return candidate.id !== roomId; });
  if (room.is_outside && !state.scenario.rooms.some(function (candidate) { return candidate.is_outside; })) {
    state.scenario.rooms[0].is_outside = true;
  }
  state.scenario.connections = state.scenario.connections.filter(function (connection) {
    return connection.source !== roomId && connection.target !== roomId;
  });
  state.scenario.activities = state.scenario.activities.filter(function (activity) {
    return activity.room_id !== roomId;
  });
  state.scenario.activities.forEach(function (activity) {
    activity.device_actions = activity.device_actions.filter(function (action) {
      return !removedDeviceIds.has(action.device_id);
    });
    (activity.micro_action_templates || []).forEach(function (template) {
      template.steps = (template.steps || []).filter(function (step) {
        return step.room_id !== roomId;
      });
    });
  });
  const replacement = state.scenario.rooms.find(function (candidate) {
    return !candidate.is_outside;
  }) || state.scenario.rooms[0];
  state.scenario.residents.forEach(function (resident) {
    if (resident.initial_room_id === roomId) {
      resident.initial_room_id = replacement.id;
      delete resident.initial_zone_id;
    }
    DAYS.forEach(function (day) {
      resident.weekly_routine[day[0]] = resident.weekly_routine[day[0]].filter(function (item) {
        return !removedActivityIds.has(routineEntry(item).activity_id);
      });
    });
    removedDeviceIds.forEach(function (deviceId) {
      if (resident.preferences) delete resident.preferences[deviceId];
    });
  });
  state.scenario.activities.forEach(function (activity) {
    activity.secondary_activities = (activity.secondary_activities || []).filter(function (rule) {
      return !removedActivityIds.has(rule.activity_id);
    });
  });
  delete state.scenario.editor_layout.room_positions[roomId];
  removedDeviceIds.forEach(function (deviceId) {
    delete state.scenario.editor_layout.device_positions[deviceId];
  });
  state.selected = { type: "home", id: null };
  markDirty();
  render();
}

function deleteDevice(deviceId) {
  const entry = roomForDevice(deviceId);
  if (!entry) return;
  const device = entry.devices.find(function (candidate) { return candidate.id === deviceId; });
  if (!window.confirm("「" + device.name + "」を削除しますか？")) {
    return;
  }
  entry.devices = entry.devices.filter(function (candidate) { return candidate.id !== deviceId; });
  state.scenario.connections.forEach(function (connection) {
    if (connection.door_sensor_id === deviceId) delete connection.door_sensor_id;
  });
  state.scenario.activities.forEach(function (activity) {
    activity.device_actions = activity.device_actions.filter(function (action) {
      return action.device_id !== deviceId;
    });
    (activity.micro_action_templates || []).forEach(function (template) {
      (template.steps || []).forEach(function (step) {
        step.device_actions = (step.device_actions || []).filter(function (action) {
          return action.device_id !== deviceId;
        });
      });
    });
  });
  state.scenario.residents.forEach(function (resident) {
    if (resident.preferences) delete resident.preferences[deviceId];
  });
  if (state.scenario.sensor_imperfections && state.scenario.sensor_imperfections.profiles) {
    delete state.scenario.sensor_imperfections.profiles[deviceId];
  }
  delete state.scenario.editor_layout.device_positions[deviceId];
  state.selected = { type: "room", id: entry.id };
  markDirty();
  render();
}

function deleteResident(residentId) {
  const resident = state.scenario.residents.find(function (candidate) { return candidate.id === residentId; });
  if (!window.confirm("「" + resident.name + "」を削除しますか？")) {
    return;
  }
  state.scenario.residents = state.scenario.residents.filter(function (candidate) {
    return candidate.id !== residentId;
  });
  delete state.routineDays[residentId];
  state.selected = { type: "home", id: null };
  markDirty();
  render();
}

function deleteActivity(activityId) {
  const activity = state.scenario.activities.find(function (candidate) { return candidate.id === activityId; });
  if (!window.confirm("「" + activity.name + "」を削除しますか？")) {
    return;
  }
  state.scenario.activities = state.scenario.activities.filter(function (candidate) {
    return candidate.id !== activityId;
  });
  state.scenario.activities.forEach(function (candidate) {
    candidate.secondary_activities = (candidate.secondary_activities || []).filter(function (rule) {
      return rule.activity_id !== activityId;
    });
  });
  state.scenario.residents.forEach(function (resident) {
    DAYS.forEach(function (day) {
      resident.weekly_routine[day[0]] = resident.weekly_routine[day[0]].filter(function (item) {
        return routineEntry(item).activity_id !== activityId;
      });
    });
  });
  state.selected = { type: "home", id: null };
  markDirty();
  render();
}

function deleteConnection(index) {
  const connection = state.scenario.connections[index];
  if (!connection) return;
  if (!window.confirm("この移動経路を削除しますか？")) {
    return;
  }
  state.scenario.connections.splice(index, 1);
  state.selected = { type: "home", id: null };
  markDirty();
  render();
}

function beginDrag(event, drag) {
  if (event.button !== 0) {
    return;
  }
  event.preventDefault();
  state.drag = Object.assign({
    changed: false,
    startClientX: event.clientX,
    startClientY: event.clientY,
  }, drag);
}

function onRoomPointerDown(event, roomId, element) {
  if (state.connectingFrom !== null) {
    if (state.connectingFrom === "") {
      state.connectingFrom = roomId;
      renderSidebar();
      renderLayout();
      return;
    }
    if (state.connectingFrom === roomId) {
      showToast("もう1つの部屋を選択してください。", true);
      return;
    }
    addConnection(state.connectingFrom, roomId);
    state.connectingFrom = null;
    render();
    return;
  }
  focusDuringDrag("room", roomId);
  const position = deepClone(state.scenario.editor_layout.room_positions[roomId]);
  beginDrag(event, { kind: "room", roomId: roomId, element: element, position: position });
}

function onResizePointerDown(event, roomId, element) {
  focusDuringDrag("room", roomId);
  const position = deepClone(state.scenario.editor_layout.room_positions[roomId]);
  beginDrag(event, { kind: "resize", roomId: roomId, element: element, position: position });
}

function onDevicePointerDown(event, deviceId, roomId, element, roomElement) {
  focusDuringDrag("device", deviceId);
  const position = deepClone(state.scenario.editor_layout.device_positions[deviceId]);
  beginDrag(event, {
    kind: "device",
    roomId: roomId,
    deviceId: deviceId,
    element: element,
    roomElement: roomElement,
    position: position,
  });
}

function onPointerMove(event) {
  const drag = state.drag;
  if (!drag) {
    return;
  }
  if (drag.kind === "device") {
    const bounds = drag.roomElement.getBoundingClientRect();
    const position = state.scenario.editor_layout.device_positions[drag.deviceId];
    position.x = clamp((event.clientX - bounds.left) / bounds.width * 100, 5, 95);
    position.y = clamp((event.clientY - bounds.top) / bounds.height * 100, 16, 94);
    drag.element.style.left = position.x + "%";
    drag.element.style.top = position.y + "%";
    drag.changed = true;
    return;
  }
  const bounds = dom.floorplan.getBoundingClientRect();
  const xDelta = (event.clientX - drag.startClientX) / bounds.width * 100;
  const yDelta = (event.clientY - drag.startClientY) / bounds.height * 100;
  const position = state.scenario.editor_layout.room_positions[drag.roomId];
  if (drag.kind === "room") {
    position.x = clamp(drag.position.x + xDelta, 0, 100 - position.width);
    position.y = clamp(drag.position.y + yDelta, 0, 100 - position.height);
  } else {
    position.width = clamp(drag.position.width + xDelta, 10, 100 - position.x);
    position.height = clamp(drag.position.height + yDelta, 10, 100 - position.y);
  }
  drag.element.style.left = position.x + "%";
  drag.element.style.top = position.y + "%";
  drag.element.style.width = position.width + "%";
  drag.element.style.height = position.height + "%";
  drag.changed = true;
  renderConnections();
}

function onPointerUp() {
  if (!state.drag) {
    return;
  }
  if (state.drag.changed) {
    markDirty();
  }
  state.drag = null;
}

function arrangeRooms() {
  state.scenario.rooms.forEach(function (room, index) {
    state.scenario.editor_layout.room_positions[room.id] = defaultRoomPosition(index);
    room.devices.forEach(function (device, deviceIndex) {
      state.scenario.editor_layout.device_positions[device.id] = defaultDevicePosition(deviceIndex);
    });
  });
  markDirty();
  renderLayout();
}

function fallbackCodeSource() {
  return JSON.stringify(state.scenario, null, 2) + "\n";
}

async function populateCodeFromScenario(format) {
  state.code.loading = true;
  renderEditorMode();
  try {
    const source = await exportScenarioText(state.scenario, format);
    if (source.ok) {
      state.code.format = format;
      state.code.text = source.text;
      state.code.appliedText = source.text;
      state.code.dirty = false;
      state.code.stale = false;
      state.validation = { kind: "valid", errors: [] };
      return true;
    }
    state.code.format = "json";
    state.code.text = fallbackCodeSource();
    state.code.appliedText = "";
    state.code.dirty = true;
    state.code.stale = false;
    state.validation = { kind: "invalid", errors: source.errors };
    showToast("GUIの未検証の内容をJSONとして表示しました。コードで修正して適用できます。", true);
    return false;
  } catch (error) {
    state.code.format = "json";
    state.code.text = fallbackCodeSource();
    state.code.appliedText = "";
    state.code.dirty = true;
    state.code.stale = false;
    state.validation = {
      kind: "invalid",
      errors: [{ path: "scenario", message: "コード用のシナリオを取得できませんでした。" }],
    };
    showToast("コード編集用のシナリオを取得できませんでした。", true);
    return false;
  } finally {
    state.code.loading = false;
    renderStatus();
    renderEditorMode();
    renderValidationReport();
    scheduleComponentWorkspaceSync();
  }
}

async function enterCodeMode() {
  if (state.editorMode === "code" || !state.scenario) {
    return;
  }
  state.editorMode = "code";
  state.connectingFrom = null;
  render();
  if (state.code.dirty || (!state.code.stale && state.code.text)) {
    return;
  }
  await populateCodeFromScenario(state.code.format);
}

async function enterGuiMode() {
  if (state.editorMode !== "code" || state.code.loading) {
    return;
  }
  if (state.code.dirty) {
    await applyCode(true);
    return;
  }
  state.editorMode = "gui";
  render();
}

async function validateCode() {
  if (state.code.loading) {
    return false;
  }
  state.code.loading = true;
  renderEditorMode();
  try {
    const result = await importScenarioText(state.code.text, state.code.format);
    if (result.response.ok && result.body.valid) {
      state.validation = { kind: "valid", errors: [] };
      showToast("コードは有効です。GUIに適用できます。");
      return true;
    }
    state.validation = {
      kind: "invalid",
      errors: errorsFromResponse(result.body),
    };
    showToast("コードで " + state.validation.errors.length + " 件の修正項目が見つかりました。", true);
    return false;
  } catch (error) {
    state.validation = {
      kind: "invalid",
      errors: [{ path: "scenario", message: "コードを検証できませんでした。" }],
    };
    showToast("コードを検証できませんでした。", true);
    return false;
  } finally {
    state.code.loading = false;
    renderStatus();
    renderEditorMode();
    renderValidationReport();
    scheduleComponentWorkspaceSync();
  }
}

async function applyCode(returnToGui) {
  if (state.code.loading) {
    return false;
  }
  state.code.loading = true;
  renderEditorMode();
  try {
    const result = await importScenarioText(state.code.text, state.code.format);
    if (!result.response.ok || !result.body.valid) {
      state.validation = {
        kind: "invalid",
        errors: errorsFromResponse(result.body),
      };
      showToast("コードを適用できません。修正項目を確認してください。", true);
      return false;
    }
    state.scenario = result.body.scenario;
    state.selected = { type: "home", id: null };
    state.activeTab = "layout";
    state.connectingFrom = null;
    state.validation = { kind: "valid", errors: [] };
    state.code.appliedText = state.code.text;
    state.code.dirty = false;
    state.code.stale = true;
    markProjectDirty();
    if (returnToGui) {
      state.editorMode = "gui";
    }
    ensureLayout();
    showToast(returnToGui ? "コードの変更をGUIに適用しました。" : "コードの変更を適用しました。");
    return true;
  } catch (error) {
    state.validation = {
      kind: "invalid",
      errors: [{ path: "scenario", message: "コードを適用できませんでした。" }],
    };
    showToast("コードを適用できませんでした。", true);
    return false;
  } finally {
    state.code.loading = false;
    render();
    scheduleComponentWorkspaceSync();
  }
}

async function formatCode(targetFormat) {
  if (state.code.loading) {
    return;
  }
  const hadUnappliedChanges = state.code.dirty;
  state.code.loading = true;
  renderEditorMode();
  try {
    const parsed = await importScenarioText(state.code.text, state.code.format);
    if (!parsed.response.ok || !parsed.body.valid) {
      state.validation = {
        kind: "invalid",
        errors: errorsFromResponse(parsed.body),
      };
      showToast("整形する前にコードを修正してください。", true);
      return;
    }
    const source = await exportScenarioText(parsed.body.scenario, targetFormat);
    if (!source.ok) {
      state.validation = { kind: "invalid", errors: source.errors };
      showToast("コードを整形できませんでした。", true);
      return;
    }
    state.code.format = targetFormat;
    state.code.text = source.text;
    state.code.appliedText = hadUnappliedChanges ? "" : source.text;
    state.code.dirty = hadUnappliedChanges;
    state.code.stale = false;
    state.validation = { kind: "valid", errors: [] };
    showToast(targetFormat.toUpperCase() + " 形式に整形しました。");
  } catch (error) {
    state.validation = {
      kind: "invalid",
      errors: [{ path: "scenario", message: "コードを整形できませんでした。" }],
    };
    showToast("コードを整形できませんでした。", true);
  } finally {
    state.code.loading = false;
    renderStatus();
    renderEditorMode();
    renderValidationReport();
    scheduleComponentWorkspaceSync();
  }
}

async function validateScenario() {
  try {
    const result = await request("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: state.scenario }),
    });
    if (result.response.ok && result.body.valid) {
      state.scenario = result.body.scenario;
      ensureLayout();
      state.validation = { kind: "valid", errors: [] };
      state.code.stale = true;
      showToast("シナリオは有効です。");
    } else {
      state.validation = { kind: "invalid", errors: result.body.errors || [] };
      showToast("検証で " + state.validation.errors.length + " 件の修正項目が見つかりました。", true);
    }
    render();
    scheduleComponentWorkspaceSync();
  } catch (error) {
    showToast("検証処理を完了できませんでした。", true);
  }
}

function floorplanExportFileName(extension) {
  const fallback = state.scenario && state.scenario.id ? state.scenario.id : "scenario";
  const stem = String(fallback).replace(/[^A-Za-z0-9_.-]+/g, "_") || "scenario";
  return stem + "_floorplan." + extension;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function svgEscape(value) {
  return escapeHtml(value).replaceAll("&#039;", "&apos;");
}

function buildFloorplanSvg() {
  if (!state.scenario) {
    return "";
  }
  ensureLayout();
  const plot = { x: 80, y: 120, width: 1440, height: 750 };
  const roomPositions = state.scenario.editor_layout.room_positions;
  const devicePositions = state.scenario.editor_layout.device_positions;
  const connectionLabels = [];
  const roomBox = function (roomId) {
    const position = roomPositions[roomId];
    if (!position) {
      return null;
    }
    return {
      x: plot.x + plot.width * position.x / 100,
      y: plot.y + plot.height * position.y / 100,
      width: plot.width * position.width / 100,
      height: plot.height * position.height / 100,
    };
  };
  const parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + FLOORPLAN_EXPORT_WIDTH
      + '" height="' + FLOORPLAN_EXPORT_HEIGHT + '" viewBox="0 0 '
      + FLOORPLAN_EXPORT_WIDTH + " " + FLOORPLAN_EXPORT_HEIGHT + '">',
    "<title>" + svgEscape(state.scenario.name || state.scenario.id) + " floorplan</title>",
    "<desc>Room connectivity and sensor/device placement exported from Hestia Studio.</desc>",
    '<rect width="1600" height="1000" fill="#ffffff"/>',
    '<text x="80" y="58" fill="#172326" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="700">'
      + svgEscape(state.scenario.name || state.scenario.id) + "</text>",
    '<text x="80" y="88" fill="#526168" font-family="Arial, Helvetica, sans-serif" font-size="16">'
      + "Room connectivity and sensor/device placement · " + svgEscape(state.scenario.id) + "</text>",
  ];

  state.scenario.connections.forEach(function (connection) {
    const source = roomBox(connection.source);
    const target = roomBox(connection.target);
    if (!source || !target) {
      return;
    }
    const x1 = source.x + source.width / 2;
    const y1 = source.y + source.height / 2;
    const x2 = target.x + target.width / 2;
    const y2 = target.y + target.height / 2;
    const middleX = (x1 + x2) / 2;
    const middleY = (y1 + y2) / 2;
    const label = asNumber(connection.travel_seconds, 0) + " s"
      + (connection.door_sensor_id ? " · " + connection.door_sensor_id : "");
    const labelWidth = Math.max(64, label.length * 7.1 + 18);
    parts.push(
      '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2
        + '" stroke="#65737a" stroke-width="5" stroke-linecap="round"/>',
    );
    connectionLabels.push(
      '<rect x="' + (middleX - labelWidth / 2) + '" y="' + (middleY - 13)
        + '" width="' + labelWidth + '" height="26" rx="6" fill="#ffffff" stroke="#cbd3d4"/>',
      '<text x="' + middleX + '" y="' + (middleY + 5)
        + '" text-anchor="middle" fill="#33434a" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="600">'
        + svgEscape(label) + "</text>",
    );
  });

  state.scenario.rooms.forEach(function (room) {
    const box = roomBox(room.id);
    if (!box) {
      return;
    }
    const dash = room.is_outside ? ' stroke-dasharray="10 7"' : "";
    const fill = room.is_outside ? "#f8faf9" : "#ffffff";
    parts.push(
      '<rect x="' + box.x + '" y="' + box.y + '" width="' + box.width
        + '" height="' + box.height + '" rx="12" fill="' + fill
        + '" stroke="#35464a" stroke-width="2.5"' + dash + "/>",
      '<text x="' + (box.x + 15) + '" y="' + (box.y + 27)
        + '" fill="#172326" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700">'
        + svgEscape(room.name) + "</text>",
      '<text x="' + (box.x + 15) + '" y="' + (box.y + 48)
        + '" fill="#607077" font-family="Arial, Helvetica, sans-serif" font-size="12">'
        + svgEscape(room.id) + (room.is_outside ? " · outside" : "") + "</text>",
    );
    room.devices.forEach(function (device) {
      const position = devicePositions[device.id] || { x: 50, y: 60 };
      const x = box.x + box.width * position.x / 100;
      const y = box.y + box.height * position.y / 100;
      const isSensor = ["MotionSensor", "ContactSensor", "DoorSensor"].includes(device.type);
      const color = isSensor ? "#147d78" : "#d06a24";
      parts.push(
        '<circle cx="' + x + '" cy="' + y + '" r="7" fill="' + color
          + '" stroke="#ffffff" stroke-width="2"/>',
        '<text x="' + (x + 12) + '" y="' + (y + 4)
          + '" fill="#27373d" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="600">'
          + svgEscape(device.id) + "</text>",
      );
    });
  });

  parts.push(...connectionLabels);
  parts.push(
    '<line x1="80" y1="914" x2="111" y2="914" stroke="#65737a" stroke-width="5" stroke-linecap="round"/>',
    '<text x="122" y="919" fill="#405158" font-family="Arial, Helvetica, sans-serif" font-size="14">connection (travel time · door sensor)</text>',
    '<circle cx="552" cy="914" r="7" fill="#147d78"/>',
    '<text x="568" y="919" fill="#405158" font-family="Arial, Helvetica, sans-serif" font-size="14">sensor</text>',
    '<circle cx="670" cy="914" r="7" fill="#d06a24"/>',
    '<text x="686" y="919" fill="#405158" font-family="Arial, Helvetica, sans-serif" font-size="14">device / actuator</text>',
    '<rect x="873" y="903" width="30" height="22" rx="4" fill="#f8faf9" stroke="#35464a" stroke-width="2" stroke-dasharray="6 4"/>',
    '<text x="914" y="919" fill="#405158" font-family="Arial, Helvetica, sans-serif" font-size="14">outside</text>',
    '<text x="1520" y="968" text-anchor="end" fill="#7a878c" font-family="Arial, Helvetica, sans-serif" font-size="12">Exported from Hestia Studio</text>',
    "</svg>",
  );
  return parts.join("");
}

function exportFloorplanSvg() {
  const svg = buildFloorplanSvg();
  if (!svg) {
    showToast("間取りを読み込んでから書き出してください。", true);
    return;
  }
  downloadBlob(
    new Blob([svg], { type: "image/svg+xml;charset=utf-8" }),
    floorplanExportFileName("svg"),
  );
  showToast("論文用SVGを書き出しました。");
}

function exportFloorplanPng() {
  const svg = buildFloorplanSvg();
  if (!svg) {
    showToast("間取りを読み込んでから書き出してください。", true);
    return;
  }
  const image = new Image();
  const sourceUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  image.onload = function () {
    const canvas = document.createElement("canvas");
    canvas.width = FLOORPLAN_EXPORT_WIDTH * 2;
    canvas.height = FLOORPLAN_EXPORT_HEIGHT * 2;
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(sourceUrl);
    canvas.toBlob(function (blob) {
      if (!blob) {
        showToast("PNGを書き出せませんでした。", true);
        return;
      }
      downloadBlob(blob, floorplanExportFileName("png"));
      showToast("論文用PNG（3200 × 2000 px）を書き出しました。");
    }, "image/png");
  };
  image.onerror = function () {
    URL.revokeObjectURL(sourceUrl);
    showToast("PNGを書き出せませんでした。", true);
  };
  image.src = sourceUrl;
}

async function exportScenario(format) {
  if (state.editorMode === "code" && state.code.dirty) {
    const applied = await applyCode(false);
    if (!applied) {
      return;
    }
  }
  try {
    const result = await request("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: state.scenario, format: format }),
    });
    if (!result.response.ok) {
      state.validation = { kind: "invalid", errors: result.body.errors || [] };
      renderStatus();
      renderValidationReport();
      showToast("書き出す前に修正が必要です。", true);
      return;
    }
    const content = result.body;
    const blob = new Blob([content], {
      type: format === "yaml" ? "application/yaml" : "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = exportFileName(format);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    state.validation = { kind: "valid", errors: [] };
    renderStatus();
    renderValidationReport();
    showToast(format.toUpperCase() + " を書き出しました。");
  } catch (error) {
    showToast("書き出しに失敗しました。", true);
  }
}

async function importFile(file) {
  const text = await file.text();
  const name = file.name.toLowerCase();
  const format = name.endsWith(".json") ? "json" : "yaml";
  try {
    const result = await request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, format: format, source_filename: file.name }),
    });
    if (!result.response.ok || !result.body.valid) {
      state.validation = { kind: "invalid", errors: result.body.errors || [] };
      renderStatus();
      renderValidationReport();
      showToast("読み込めませんでした。検証結果を確認してください。", true);
      return;
    }
    state.scenario = result.body.scenario;
    state.selected = { type: "home", id: null };
    state.activeTab = "layout";
    state.connectingFrom = null;
    state.sourceFileName = result.body.source_filename || null;
    state.validation = { kind: "valid", errors: [] };
    resetCodeDraft();
    resetProjectScenario(result.body.source_path || null, true);
    ensureLayout();
    render();
    scheduleComponentWorkspaceSync();
    showToast("「" + state.scenario.name + "」を読み込みました。");
  } catch (error) {
    showToast("読み込みに失敗しました。", true);
  }
}

async function newScenario() {
  if (!window.confirm("現在の編集内容を破棄して、新しいシナリオを作成しますか？")) {
    return;
  }
  try {
    const result = await request("/api/template");
    state.scenario = result.body.scenario;
    state.selected = { type: "home", id: null };
    state.activeTab = "layout";
    state.connectingFrom = null;
    state.sourceFileName = result.body.source_filename || null;
    state.validation = { kind: "neutral", errors: [] };
    resetCodeDraft();
    resetProjectScenario(result.body.source_path || null, true);
    ensureLayout();
    render();
    scheduleComponentWorkspaceSync();
    showToast("新しいシナリオを作成しました。");
  } catch (error) {
    showToast("新規シナリオの作成に失敗しました。", true);
  }
}

function bindEvents() {
  uiRoot.querySelector("#new-button").addEventListener("click", newScenario);
  uiRoot.querySelector("#export-json-button").addEventListener("click", function () {
    exportScenario("json");
  });
  uiRoot.querySelector("#export-yaml-button").addEventListener("click", function () {
    saveCurrentYaml();
  });
  dom.saveYamlButton.addEventListener("click", saveCurrentYaml);
  dom.refreshScenariosButton.addEventListener("click", function () {
    loadProjectScenarios(state.project.selectedPath);
  });
  dom.saveFileName.addEventListener("input", function () {
    state.project.fileName = dom.saveFileName.value;
    state.project.error = false;
  });
  dom.runScenarioSelect.addEventListener("change", function () {
    state.project.selectedPath = dom.runScenarioSelect.value;
    state.run.outputNameAutomatic = true;
    refreshAutomaticOutputName();
    state.run.result = null;
    state.run.error = false;
    state.run.message = "";
    renderRunPane();
  });
  dom.runDays.addEventListener("input", function () {
    state.run.days = Math.max(1, Math.floor(asNumber(dom.runDays.value, 7)));
    refreshAutomaticOutputName();
    renderRunPane();
  });
  dom.runSeed.addEventListener("input", function () {
    state.run.seed = Math.trunc(asNumber(dom.runSeed.value, 42));
    refreshAutomaticOutputName();
    renderRunPane();
  });
  dom.runOutputName.addEventListener("input", function () {
    state.run.outputName = dom.runOutputName.value;
    state.run.outputNameAutomatic = false;
    renderRunPane();
  });
  dom.runSimulationButton.addEventListener("click", runSimulation);
  dom.validationButton.addEventListener("click", function () {
    if (state.editorMode === "code") {
      validateCode();
      return;
    }
    validateScenario();
  });
  dom.guiModeButton.addEventListener("click", enterGuiMode);
  dom.codeModeButton.addEventListener("click", enterCodeMode);
  dom.codeEditor.addEventListener("input", function () {
    state.code.text = dom.codeEditor.value;
    state.code.dirty = state.code.text !== state.code.appliedText;
    state.validation = { kind: "neutral", errors: [] };
    renderStatus();
    renderCodeValidation();
    renderEditorMode();
  });
  dom.codeFormatYaml.addEventListener("click", function () {
    formatCode("yaml");
  });
  dom.codeFormatJson.addEventListener("click", function () {
    formatCode("json");
  });
  dom.codeFormatButton.addEventListener("click", function () {
    formatCode(state.code.format);
  });
  dom.codeValidateButton.addEventListener("click", validateCode);
  dom.codeApplyButton.addEventListener("click", function () {
    applyCode(true);
  });
  dom.importInput.addEventListener("change", function () {
    const file = dom.importInput.files && dom.importInput.files[0];
    if (file) {
      importFile(file);
    }
    dom.importInput.value = "";
  });
  uiRoot.querySelector("#add-room-button").addEventListener("click", addRoom);
  uiRoot.querySelector("#add-room-canvas-button").addEventListener("click", addRoom);
  uiRoot.querySelector("#add-resident-button").addEventListener("click", addResident);
  uiRoot.querySelector("#add-resident-pane-button").addEventListener("click", addResident);
  uiRoot.querySelector("#add-activity-button").addEventListener("click", addActivity);
  uiRoot.querySelector("#add-activity-pane-button").addEventListener("click", addActivity);
  uiRoot.querySelector("#fit-layout-button").addEventListener("click", arrangeRooms);
  dom.exportFloorplanSvgButton.addEventListener("click", exportFloorplanSvg);
  dom.exportFloorplanPngButton.addEventListener("click", exportFloorplanPng);
  uiRoot.querySelectorAll("[data-evaluation-house]").forEach(function (button) {
    button.addEventListener("click", function () {
      switchEvaluationHouse(button.dataset.evaluationHouse);
    });
  });
  uiRoot.querySelector("#connect-button").addEventListener("click", function () {
    state.connectingFrom = state.connectingFrom === null ? "" : null;
    renderSidebar();
    renderLayout();
  });
  uiRoot.querySelector("#close-selection-button").addEventListener("click", function () {
    selectItem("home", null, state.activeTab);
  });
  uiRoot.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      state.activeTab = tab.dataset.tab;
      renderTabState();
      if (state.activeTab === "run") {
        renderRunPane();
      }
    });
  });
  if (boundEventDocument) {
    boundEventDocument.removeEventListener("pointermove", onPointerMove);
    boundEventDocument.removeEventListener("pointerup", onPointerUp);
  }
  boundEventDocument = uiRoot.ownerDocument || uiRoot;
  boundEventDocument.addEventListener("pointermove", onPointerMove);
  boundEventDocument.addEventListener("pointerup", onPointerUp);
  window.removeEventListener("resize", renderConnections);
  window.addEventListener("resize", renderConnections);
}

function initializeFromComponent(data) {
  componentBootstrap = data.bootstrap;
  if (!componentBootstrap || !componentBootstrap.houses) {
    throw new Error("component bootstrap is missing");
  }
  if (data.workspace && data.workspace.scenario) {
    restoreComponentWorkspace(data.workspace, componentBootstrap);
  } else {
    EVALUATION_HOUSES.forEach(function (house) {
      state.evaluationHouseSessions[house] = createEvaluationHouseSession(
        componentBootstrap.houses[house],
      );
    });
    activateEvaluationHouseSession(componentBootstrap.initial_house || "compact");
    state.project.files = deepClone(componentBootstrap.files || []);
  }
  render();
}

async function initialize() {
  bindEvents();
  try {
    const parameters = new URLSearchParams(window.location.search);
    const evaluationHouse = parameters.get("evaluation_house");
    if (EVALUATION_HOUSES.includes(evaluationHouse)) {
      const results = await Promise.all(EVALUATION_HOUSES.map(function (house) {
        return request("/api/initial?evaluation_house=" + encodeURIComponent(house));
      }));
      results.forEach(function (result, index) {
        if (!result.response.ok || !result.body.scenario) {
          throw new Error("evaluation house preload failed");
        }
        state.evaluationHouseSessions[EVALUATION_HOUSES[index]] = createEvaluationHouseSession(
          result.body,
        );
      });
      activateEvaluationHouseSession(evaluationHouse);
      render();
      await loadProjectScenarios(state.project.selectedPath);
      return;
    }
    const initialEndpoint = evaluationHouse
      ? "/api/initial?evaluation_house=" + encodeURIComponent(evaluationHouse)
      : "/api/initial";
    const result = await request(initialEndpoint);
    if (!result.response.ok || !result.body.scenario) {
      throw new Error("initial scenario failed");
    }
    state.scenario = result.body.scenario;
    state.sourceFileName = result.body.source_filename || null;
    const hadEditorLayout = Boolean(state.scenario.editor_layout);
    ensureLayout();
    resetProjectScenario(result.body.source_path || null, !result.body.source_path || !hadEditorLayout);
    render();
    await loadProjectScenarios(result.body.source_path || null);
  } catch (error) {
    dom.scenarioName.textContent = "起動エラー";
    showToast("Studio を読み込めませんでした。", true);
  }
}

export default function renderHestiaStudioComponent(component) {
  componentBridge = component;
  const rootChanged = uiRoot !== component.parentElement;
  if (rootChanged || !componentInitialized) {
    uiRoot = component.parentElement;
    bindDom(uiRoot);
    bindEvents();
    initializeFromComponent(component.data || {});
    componentInitialized = true;
  } else if (component.data && component.data.bootstrap) {
    componentBootstrap = component.data.bootstrap;
  }
  handleComponentResponse(component.data && component.data.response);
}

if (document.querySelector("#workspace")) {
  bindDom(document);
  initialize();
}
