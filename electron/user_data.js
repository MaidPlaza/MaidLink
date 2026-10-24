const fs = require("fs");
const path = require("path");

const PROFILE_DIR = "MaidLink";
const LEGACY_PROFILE_DIR = "maidai";

function useMaidLinkProfile(app, log = console) {
  const appData = app.getPath("appData");
  const target = path.join(appData, PROFILE_DIR);
  const legacy = path.join(appData, LEGACY_PROFILE_DIR);
  try {
    if (!fs.existsSync(target) && fs.existsSync(legacy)) {
      fs.renameSync(legacy, target);
      log.log(`[electron] профиль перенесён: ${legacy} -> ${target}`);
    }
  } catch (e) {
    log.warn(`[electron] профиль ${legacy} не перенесён: ${e.message}`);
  }
  app.setPath("userData", target);
  return target;
}

module.exports = { useMaidLinkProfile, PROFILE_DIR, LEGACY_PROFILE_DIR };
