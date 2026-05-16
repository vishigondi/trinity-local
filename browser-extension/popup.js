// Trinity Local — popup glue. Phase 3.
//
// Two affordances:
//  1. Type a question + click "Send to council" → fires an action
//      message via chrome.runtime.sendMessage, the service worker
//      forwards through Native Messaging to capture_host, which runs
//      `trinity-local council-launch --task <text>`.
//  2. "Open full launchpad" → chrome.tabs.create on launchpad.html
//      served from the extension's own origin (chrome-extension://...).

"use strict";

const $ = (id) => document.getElementById(id);

function setStatus(text, cls = "") {
  const el = $("status");
  el.textContent = text;
  el.className = "status " + cls;
}

$("run-btn").addEventListener("click", () => {
  const task = $("task").value.trim();
  if (!task) {
    setStatus("Type a question first.", "error");
    return;
  }
  setStatus("Sending to council…");
  $("run-btn").disabled = true;
  chrome.runtime.sendMessage(
    { type: "action", kind: "launch-council", task },
    (response) => {
      $("run-btn").disabled = false;
      if (chrome.runtime.lastError) {
        setStatus("Extension error: " + chrome.runtime.lastError.message, "error");
        return;
      }
      if (!response) {
        setStatus("No response from native host. Did you run trinity-local install-extension?", "error");
        return;
      }
      if (response.ok) {
        setStatus("Council started. Check the launchpad for live status.", "ok");
        $("task").value = "";
      } else {
        const err = response.error || response.detail || "unknown error";
        const hint = response.hint ? "\n" + response.hint : "";
        setStatus("Failed: " + err + hint, "error");
      }
    }
  );
});

$("task").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("run-btn").click();
  }
});

$("open-launchpad-btn").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("launchpad.html") });
  window.close();
});
