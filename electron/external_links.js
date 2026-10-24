"use strict";

const EXTERNAL_RX = /^https?:\/\//i;

function isSameApp(currentUrl, nextUrl) {
  try {
    const cur = new URL(currentUrl);
    const next = new URL(nextUrl);
    return cur.origin !== "null" && next.origin === cur.origin;
  } catch {
    return false;
  }
}

function attachExternalLinkHandlers(win, shell) {
  const openExternally = (url) => {
    if (!EXTERNAL_RX.test(url)) return;
    try {
      Promise.resolve(shell.openExternal(url)).catch(() => {});
    } catch {
    }
  };
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternally(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!isSameApp(win.webContents.getURL(), url) && EXTERNAL_RX.test(url)) {
      event.preventDefault();
      openExternally(url);
    }
  });
}

module.exports = { attachExternalLinkHandlers, isSameApp, EXTERNAL_RX };
