const { contextBridge, ipcRenderer } = require("electron");

const apiAuth = ipcRenderer.sendSync("api-auth") || {};

contextBridge.exposeInMainWorld("maidViewer", {
  galleryChanged: () => ipcRenderer.send("gallery-changed"),
  apiToken: apiAuth.token || "",
});
