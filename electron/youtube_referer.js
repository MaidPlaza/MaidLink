"use strict";

const YT_URLS = [
  "https://www.youtube-nocookie.com/*",
  "https://www.youtube.com/*",
  "https://*.youtube.com/*",
  "https://*.ytimg.com/*",
  "https://*.googlevideo.com/*",
];
const APP_REFERER = "http://localhost:8001/";

function attachYoutubeReferer(ses, referer = APP_REFERER) {
  ses.webRequest.onBeforeSendHeaders({ urls: YT_URLS }, (details, callback) => {
    const headers = details.requestHeaders || {};
    const has = Object.keys(headers).some((k) => k.toLowerCase() === "referer");
    if (!has) headers.Referer = referer;
    callback({ requestHeaders: headers });
  });
}

module.exports = { attachYoutubeReferer, APP_REFERER };
