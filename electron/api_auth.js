"use strict";

const crypto = require("crypto");
const path = require("path");
const { fileURLToPath } = require("url");

const TOKEN_HEADER = "X-MaidLink-Token";
const MEDIA_LABEL = "maidlink-media-v1";
const DEV_UI_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"];

function newToken() {
  return crypto.randomBytes(32).toString("base64url");
}

function mediaTokenFor(token) {
  return crypto.createHmac("sha256", token).update(MEDIA_LABEL).digest("base64url");
}

function normPath(p) {
  const r = path.resolve(p);
  return process.platform === "win32" ? r.toLowerCase() : r;
}

function makePageCheck(pages, devOrigins = []) {
  const files = new Set(pages.map(normPath));
  const origins = new Set(devOrigins);
  return (rawUrl) => {
    try {
      const u = new URL(rawUrl);
      if (u.protocol === "file:") return files.has(normPath(fileURLToPath(u)));
      return origins.has(u.origin);
    } catch {
      return false;
    }
  };
}

function attachApiAuth(ipcMain, { token, media, isAppPage, log = console.log }) {
  ipcMain.on("api-auth", (event) => {
    const url = (event.senderFrame && event.senderFrame.url) || event.sender.getURL();
    const ok = isAppPage(url);
    event.returnValue = ok ? { token, media } : null;
    if (!ok && url && url !== "about:blank") log(`[auth] токен не выдан странице ${url}`);
  });
}

module.exports = {
  TOKEN_HEADER, MEDIA_LABEL, DEV_UI_ORIGINS,
  newToken, mediaTokenFor, makePageCheck, attachApiAuth,
};
