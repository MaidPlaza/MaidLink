const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, Notification, screen, session, shell } = require("electron");
const { spawn, execSync } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");
const apiAuth = require("./api_auth");

const ROOT = path.resolve(__dirname, "..");

require("./user_data").useMaidLinkProfile(app);

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
  process.exit(0);
}
app.on("second-instance", () => {
  if (mainWindow) {
    if (!mainWindow.isVisible()) mainWindow.show();
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

const BACKEND_EXE = app.isPackaged
  ? path.join(process.resourcesPath, "backend", "backend.exe")
  : (process.env.MAIDLINK_BACKEND_EXE || null);
const USE_FROZEN_BACKEND = !!BACKEND_EXE;
const UI_DIST = path.join(ROOT, "ui", "dist", "index.html");
const VIEWER_HTML = path.join(__dirname, "viewer.html");

const API_TOKEN = apiAuth.newToken();
const MEDIA_TOKEN = apiAuth.mediaTokenFor(API_TOKEN);
const API_TOKEN_HEADER = apiAuth.TOKEN_HEADER;
apiAuth.attachApiAuth(ipcMain, {
  token: API_TOKEN,
  media: MEDIA_TOKEN,
  isAppPage: apiAuth.makePageCheck([UI_DIST, VIEWER_HTML],
                                   app.isPackaged ? [] : apiAuth.DEV_UI_ORIGINS),
});

app.commandLine.appendSwitch("disable-gpu-compositing");

if (process.platform === "win32") {
  app.setAppUserModelId("com.maidlink.app");
}

let mainWindow = null;
let tray = null;
let fastapiProcess = null;
let viteProcess = null;

const IDLE_THRESHOLD_MS = 5 * 60 * 1000;

const appState = {
  windowVisible: true,
  chatActive: false,
  lastChatActivity: Date.now(),
  isQuitting: false,
};

let lastReportedState = null;

function getComputeState() {
  if (appState.chatActive) return "ACTIVE_CHAT";
  if (!appState.windowVisible) return "BACKGROUND";
  const idle = Date.now() - appState.lastChatActivity;
  if (idle > IDLE_THRESHOLD_MS) return "IDLE_FOREGROUND";
  return "FOREGROUND";
}

function notifyStateChange() {
  const state = getComputeState();
  if (state !== lastReportedState) {
    console.log(`[state] ${lastReportedState ?? "(init)"} → ${state}`);
    lastReportedState = state;
  }
  if (tray) {
    tray.setToolTip(`MaidLink · ${state}`);
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("app-state-changed", state);
  }
  postAppStateToBackend(state);
}

const BACKEND_STATE_URL = "http://127.0.0.1:8001/api/background/state";

function postAppStateToBackend(state) {
  try {
    const body = JSON.stringify({ state });
    const url = new URL(BACKEND_STATE_URL);
    const req = http.request(
      {
        method: "POST",
        host: url.hostname,
        port: url.port,
        path: url.pathname,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
          [API_TOKEN_HEADER]: API_TOKEN,
        },
        timeout: 1500,
      },
      (res) => {
        res.resume();
      }
    );
    req.on("error", () => {});
    req.on("timeout", () => req.destroy());
    req.write(body);
    req.end();
  } catch {
  }
}

const APP_STATUS_URL = "http://127.0.0.1:8001/api/status";

function fetchAppStatus() {
  return new Promise((resolve) => {
    try {
      const url = new URL(APP_STATUS_URL);
      const req = http.get(
        { host: url.hostname, port: url.port, path: url.pathname, timeout: 1500,
          headers: { [API_TOKEN_HEADER]: API_TOKEN } },
        (res) => {
          let raw = "";
          res.on("data", (d) => { raw += d; });
          res.on("end", () => {
            try { resolve(JSON.parse(raw)); } catch { resolve(null); }
          });
        }
      );
      req.on("error", () => resolve(null));
      req.on("timeout", () => { req.destroy(); resolve(null); });
    } catch {
      resolve(null);
    }
  });
}

const EXIT_CLEANUP_URL = "http://127.0.0.1:8001/api/app/exit-cleanup";

function requestExitCleanup(timeoutMs = 5000) {
  return new Promise((resolve) => {
    try {
      const url = new URL(EXIT_CLEANUP_URL);
      const req = http.request(
        { host: url.hostname, port: url.port, path: url.pathname, method: "POST", timeout: timeoutMs,
          headers: { [API_TOKEN_HEADER]: API_TOKEN } },
        (res) => {
          res.resume();
          res.on("end", resolve);
        }
      );
      req.on("error", resolve);
      req.on("timeout", () => { req.destroy(); resolve(); });
      req.end();
    } catch {
      resolve();
    }
  });
}

function formatAppStatus(st) {
  if (!st || !st.label) return "Бэкенд недоступен";
  let s = st.label;
  if (st.detail) s += `: ${st.detail}`;
  if (st.step && st.total) s += ` (${st.step}/${st.total})`;
  return s;
}

let stateTickerInterval = null;
function startStateTicker() {
  if (stateTickerInterval) return;
  stateTickerInterval = setInterval(notifyStateChange, 30000);
}
function stopStateTicker() {
  if (stateTickerInterval) {
    clearInterval(stateTickerInterval);
    stateTickerInterval = null;
  }
}

function logStream(name, stream) {
  stream?.on("data", (d) => {
    const t = d.toString().trim();
    if (t) console.log(`[${name}] ${t}`);
  });
}

function waitForPort(port, maxWait = 180000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    function check() {
      if (Date.now() - start > maxWait) {
        return reject(new Error(`Port ${port} timeout`));
      }
      const req = http.get(`http://localhost:${port}`, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => setTimeout(check, 2000));
      req.setTimeout(2000, () => {
        req.destroy();
        setTimeout(check, 2000);
      });
    }
    check();
  });
}

function killTreeByPid(pid) {
  if (!pid) return;
  try {
    execSync(`taskkill /pid ${pid} /f /t`, { shell: true, stdio: "ignore", windowsHide: true });
  } catch {
  }
}

function killByPort(port) {
  try {
    const r = execSync(
      `netstat -ano | findstr :${port} | findstr LISTENING`,
      { shell: true, encoding: "utf-8", windowsHide: true }
    );
    r.trim().split("\n").forEach((line) => {
      const pid = line.trim().split(/\s+/).pop();
      if (pid && pid !== "0") killTreeByPid(pid);
    });
  } catch {
  }
}

function killAll() {
  killTreeByPid(fastapiProcess?.pid);
  killTreeByPid(viteProcess?.pid);
  try {
    execSync("taskkill /im llama-server.exe /f", {
      shell: true,
      stdio: "ignore",
      windowsHide: true,
    });
  } catch {
  }
}

app.on("ready", async () => {
  [8000, 8001, 8002, 8188, 5173].forEach(killByPort);

  await session.defaultSession.clearCache().catch(() => {});

  if (USE_FROZEN_BACKEND) {
    console.log(`[backend] frozen exe: ${BACKEND_EXE}`);
    fastapiProcess = spawn(BACKEND_EXE, [], {
      cwd: path.dirname(BACKEND_EXE),
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: { ...process.env, MAIDLINK_PORT: "8001", MAIDLINK_HOST: "127.0.0.1",
             MAIDLINK_API_TOKEN: API_TOKEN },
    });
  } else {
    console.log("[backend] dev: rvc_env python -m uvicorn");
    fastapiProcess = spawn(
      path.join(ROOT, "rvc_env", "Scripts", "python.exe"),
      [
        "-X", "utf8",
        "-m", "uvicorn",
        "api.server:app",
        "--port", "8001",
        "--host", "127.0.0.1",
      ],
      {
        cwd: ROOT,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, PYTHONIOENCODING: "utf-8", MAIDLINK_API_TOKEN: API_TOKEN },
      }
    );
  }
  logStream("backend", fastapiProcess.stdout);
  logStream("backend", fastapiProcess.stderr);
  fastapiProcess.on("exit", (code) => console.log(`[backend] exited (${code})`));

  if (!app.isPackaged) {
    const viteBin = path.join(
      ROOT, "ui", "node_modules", "vite", "bin", "vite.js"
    );
    const viteCwd = path.join(ROOT, "ui");
    console.log(`[vite] Starting in ${viteCwd}...`);
    viteProcess = spawn(
      process.execPath,
      [viteBin, "--port", "5173", "--host", "127.0.0.1", "--strictPort"],
      {
        cwd: viteCwd,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
      }
    );
    logStream("vite", viteProcess.stdout);
    logStream("vite", viteProcess.stderr);
    viteProcess.on("exit", (code) => console.log(`[vite] exited (${code})`));
  }

  mainWindow = new BrowserWindow({
    width: 780, height: 906, minWidth: 780, minHeight: 906,
    title: "MaidLink",
    icon: path.join(__dirname, "icon-light-32x32.png"),
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
      devTools: !app.isPackaged,
    },
  });

  require("./external_links").attachExternalLinkHandlers(mainWindow, shell);

  require("./youtube_referer").attachYoutubeReferer(mainWindow.webContents.session);

  mainWindow.webContents.on("before-input-event", (event, input) => {
    if (input.type === "keyDown" && input.control && ["-", "=", "+"].includes(input.key)) {
      event.preventDefault();
    }
  });
  mainWindow.webContents.on("zoom-changed", () => mainWindow?.webContents.setZoomLevel(0));
  mainWindow.webContents.setVisualZoomLevelLimits(1, 1);
  mainWindow.webContents.on("did-finish-load", () => mainWindow?.webContents.setZoomLevel(0));

  if (app.isPackaged) {
    console.log(`[app] Loading built UI: ${UI_DIST}`);
    mainWindow.loadFile(UI_DIST).catch((e) =>
      console.log(`[app] loadFile failed: ${e}`)
    );
  } else {
    console.log("[app] Waiting for Vite on port 5173...");
    try {
      await waitForPort(5173, 120000);
      console.log("[app] Vite ready, loading UI...");
      mainWindow.loadURL("http://localhost:5173");
      mainWindow.webContents.openDevTools({ mode: "detach" });
    } catch {
      mainWindow.loadURL(
        `data:text/html;charset=utf-8,` +
        `<html><body style="display:flex;align-items:center;justify-content:center;height:100vh;background:%23d9d0c7;font-family:system-ui;margin:0;">` +
        `<div style="text-align:center"><h1 style="color:%234a3830">MaidLink</h1>` +
        `<p style="color:%238b7f6e">Vite не стартанул. Проверь логи в консоли.</p>` +
        `</div></body></html>`
      );
    }
  }

  mainWindow.on("close", (e) => {
    if (!appState.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      if (!mainWindow._trayBalloonShown) {
        try {
          tray?.displayBalloon({
            title: "MaidLink",
            content: "Свернуто в трей. Кликните по иконке чтобы открыть, или «Выход» в меню чтобы выйти полностью.",
          });
        } catch {
        }
        mainWindow._trayBalloonShown = true;
      }
    }
  });

  mainWindow.on("show", () => {
    appState.windowVisible = true;
    notifyStateChange();
  });
  mainWindow.on("hide", () => {
    appState.windowVisible = false;
    notifyStateChange();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  const trayIconPath = path.join(__dirname, "icon-light-32x32.png");
  tray = new Tray(nativeImage.createFromPath(trayIconPath));
  tray.setToolTip("MaidLink");
  const buildTrayMenu = (statusLine) => Menu.buildFromTemplate([
    { label: statusLine, enabled: false },
    { type: "separator" },
    {
      label: "Открыть",
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: "separator" },
    {
      label: "Выход",
      click: () => {
        appState.isQuitting = true;
        stopStateTicker();
        app.quit();
      },
    },
  ]);
  tray.on("right-click", async () => {
    const st = await fetchAppStatus();
    tray.popUpContextMenu(buildTrayMenu(formatAppStatus(st)));
  });
  const trayStatusTick = setInterval(async () => {
    const st = await fetchAppStatus();
    if (tray && !tray.isDestroyed()) {
      tray.setToolTip(`MaidLink — ${formatAppStatus(st)}`);
    }
  }, 5000);
  app.on("before-quit", () => clearInterval(trayStatusTick));
  tray.on("click", () => {
    if (!mainWindow) return;
    if (!mainWindow.isVisible()) mainWindow.show();
    mainWindow.focus();
  });
  tray.on("balloon-click", () => {
    if (!mainWindow) return;
    if (!mainWindow.isVisible()) mainWindow.show();
    mainWindow.focus();
  });

  ipcMain.on("window-minimize", () => mainWindow?.minimize());
  ipcMain.on("window-maximize", () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize();
    else mainWindow?.maximize();
  });
  ipcMain.on("window-close", () => {
    mainWindow?.close();
  });
  ipcMain.on("app-quit", () => {
    appState.isQuitting = true;
    stopStateTicker();
    app.quit();
  });

  ipcMain.on("chat-activity", (_event, isActive) => {
    appState.chatActive = !!isActive;
    appState.lastChatActivity = Date.now();
    notifyStateChange();
  });
  ipcMain.handle("get-app-state", () => getComputeState());

  ipcMain.on("show-notification", (_event, payload) => {
    const isMessage = payload && payload.kind === "message";
    const title = isMessage ? (payload.title || "") : ((payload && payload.title) || "MaidLink");
    const body = (payload && payload.body) || "";
    console.log(`[notification] requested: ${title} | ${body.slice(0, 60)}`);
    if (!tray) {
      console.log("[notification] tray not initialized yet, skipping");
      return;
    }
    if (isMessage && mainWindow && mainWindow.isVisible()
        && !mainWindow.isMinimized() && mainWindow.isFocused()) {
      console.log("[notification] окно в фокусе — весточка видна в чате, без уведомления");
      return;
    }
    let icon = null;
    if (payload && payload.icon) {
      try {
        const img = nativeImage.createFromPath(payload.icon);
        if (!img.isEmpty()) icon = img.resize({ width: 64, height: 64, quality: "best" });
      } catch {
        icon = null;
      }
    }
    try {
      tray.displayBalloon({
        title,
        content: body,
        ...(icon ? { icon, iconType: "custom", largeIcon: true } : { iconType: "info" }),
        ...(isMessage ? { noSound: true } : {}),
      });
    } catch (e) {
      console.log(`[notification] tray.displayBalloon failed: ${e}`);
    }
  });

  ipcMain.on("win-get-bounds", (event) => {
    event.returnValue = mainWindow ? mainWindow.getBounds() : null;
  });
  ipcMain.on("win-resize", (_event, bounds) => {
    if (mainWindow && bounds) mainWindow.setBounds(bounds);
  });
  ipcMain.handle("capture-screenshot", async () => {
    if (!mainWindow) return null;
    const image = await mainWindow.webContents.capturePage();
    return image.toDataURL();
  });
  ipcMain.handle("read-theme-config", async (_event, id) => {
    try {
      const safe = String(id || "").replace(/[^a-z0-9_-]/gi, "");
      if (!safe) return null;
      const p = path.join(ROOT, "ui", "electron", "configs", `${safe}.json`);
      return JSON.parse(fs.readFileSync(p, "utf8"));
    } catch (e) {
      console.log(`[theme] read-theme-config(${id}) failed: ${e}`);
      return null;
    }
  });

  const viewerWindows = new Map();
  ipcMain.handle("open-image-viewer", (_event, payload) => {
    const p = payload || {};
    const id = String(p.id || "");
    const existing = id ? viewerWindows.get(id) : null;
    if (existing && !existing.isDestroyed()) {
      existing.focus();
      return true;
    }
    const BAR = 36;
    const disp = screen.getDisplayMatching(
      mainWindow && !mainWindow.isDestroyed()
        ? mainWindow.getBounds() : screen.getPrimaryDisplay().bounds);
    const wa = disp.workArea;
    const iw = Number(p.width) || 1024;
    const ih = Number(p.height) || 1536;
    const maxW = Math.floor(wa.width * 0.85);
    const maxH = Math.floor(wa.height * 0.85) - BAR;
    const k = Math.min(maxW / iw, maxH / ih, 1);
    const w = Math.max(320, Math.round(iw * k));
    const h = Math.max(240, Math.round(ih * k) + BAR);
    const th = p.theme || {};
    const hex = (v) => (/^#[0-9a-fA-F]{6}$/.test(String(v || "").trim()) ? String(v).trim() : "");
    const barColor = hex(th.bar), fgColor = hex(th.fg), stageColor = hex(th.stage);
    const win = new BrowserWindow({
      width: w, height: h, minWidth: 240, minHeight: 200,
      x: Math.round(wa.x + (wa.width - w) / 2),
      y: Math.round(wa.y + (wa.height - h) / 2),
      title: "MaidLink — снимок",
      icon: path.join(__dirname, "icon-light-32x32.png"),
      frame: false, roundedCorners: true, backgroundColor: barColor || "#1c1e27",
      resizable: true,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: path.join(__dirname, "viewer-preload.js"),
        devTools: !app.isPackaged,
      },
    });
    win.setMenuBarVisibility(false);
    win.loadFile(VIEWER_HTML, {
      query: {
        url: String(p.url || ""), id,
        intent: String(p.intent || ""),
        added_at: String(p.added_at || ""),
        api: String(p.api || "http://localhost:8001"),
        bar: barColor, fg: fgColor, stage: stageColor,
      },
    }).catch((e) => console.log(`[viewer] loadFile failed: ${e}`));
    if (id) {
      viewerWindows.set(id, win);
      win.on("closed", () => {
        if (viewerWindows.get(id) === win) viewerWindows.delete(id);
      });
    }
    return true;
  });
  ipcMain.on("gallery-changed", () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("gallery-changed");
  });

  startStateTicker();
  notifyStateChange();
});

let exitCleanupDone = false;
app.on("before-quit", (event) => {
  if (exitCleanupDone) {
    killAll();
    return;
  }
  exitCleanupDone = true;
  event.preventDefault();
  requestExitCleanup().then(() => app.quit());
});
app.on("window-all-closed", () => {
});

process.on("exit", killAll);
process.on("SIGINT", () => {
  killAll();
  process.exit();
});
