const { contextBridge, ipcRenderer, webUtils } = require("electron");

const apiAuth = ipcRenderer.sendSync("api-auth") || {};

contextBridge.exposeInMainWorld("maidlink", {
  platform: process.platform,
  version: "0.1.0",
  apiToken: apiAuth.token || "",
  mediaToken: apiAuth.media || "",

  minimize: () => ipcRenderer.send("window-minimize"),
  maximize: () => ipcRenderer.send("window-maximize"),
  close: () => ipcRenderer.send("window-close"),
  quit: () => ipcRenderer.send("app-quit"),

  reportChatActivity: (isActive) => ipcRenderer.send("chat-activity", !!isActive),

  getAppState: () => ipcRenderer.invoke("get-app-state"),

  onAppStateChange: (callback) => {
    const handler = (_event, state) => callback(state);
    ipcRenderer.on("app-state-changed", handler);
    return () => ipcRenderer.removeListener("app-state-changed", handler);
  },

  showNotification: (title, body, opts) =>
    ipcRenderer.send("show-notification", {
      title, body, kind: opts?.kind, icon: opts?.icon,
    }),

  getBounds: () => ipcRenderer.sendSync("win-get-bounds"),
  resize: (bounds) => ipcRenderer.send("win-resize", bounds),

  captureScreenshot: () => ipcRenderer.invoke("capture-screenshot"),

  readThemeConfig: (id) => ipcRenderer.invoke("read-theme-config", id),

  openImageViewer: (payload) => ipcRenderer.invoke("open-image-viewer", payload),
  onGalleryChanged: (callback) => {
    const handler = () => callback();
    ipcRenderer.on("gallery-changed", handler);
    return () => ipcRenderer.removeListener("gallery-changed", handler);
  },

  getPathForFile: (file) => webUtils.getPathForFile(file),
});
