/* Keeps the reader informed about new listings, without interrupting them.
 *
 * Two levels of feedback, deliberately different in weight:
 *
 *   heartbeat  a quiet line in the header, always visible. Says when we
 *              last checked and when the collector last ran, so "nothing
 *              new" can be told apart from "nothing is running". Those
 *              look identical otherwise, and the second one is a fault.
 *
 *   notice     a prominent bar, only when something actually changed.
 *              Offers Refresh; never reloads on its own. Someone reading
 *              a listing should not have the page pulled from under them.
 *
 * Polling stops while the tab is hidden and resumes when it is looked at
 * again, so a forgotten tab is not a standing cost.
 */
(function () {
  "use strict";

  var POLL_MS = 60000;
  var TICK_MS = 15000;    // how often the "checked N ago" text is redrawn
  var BACKOFF_MAX = 15;

  var notice = document.getElementById("update-notice");
  var heartbeat = document.getElementById("update-heartbeat");
  if (!notice) return;

  var baseline = {
    count: parseInt(notice.dataset.count, 10),
    newest: notice.dataset.newest || null,
    changed: notice.dataset.changed || null,
  };

  var lastChecked = new Date();
  var lastCollected = notice.dataset.collected
    ? new Date(notice.dataset.collected)
    : null;
  var failures = 0;
  var dismissed = false;
  var timer = null;

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  function ago(date) {
    if (!date) return "never";
    var seconds = Math.round((new Date() - date) / 1000);
    if (seconds < 45) return "just now";
    if (seconds < 5400) return plural(Math.round(seconds / 60), "minute") + " ago";
    if (seconds < 172800) return plural(Math.round(seconds / 3600), "hour") + " ago";
    return plural(Math.round(seconds / 86400), "day") + " ago";
  }

  /* Keep auction countdowns current without reloading the page or data. */
  function countdown(date) {
    var delta = date - new Date();
    var future = delta > 0;
    var seconds = Math.abs(delta) / 1000;
    if (seconds < 60) return future ? "in under a minute" : "just passed";

    var amount, unit;
    if (seconds < 3600) {
      amount = future ? Math.ceil(seconds / 60) : Math.floor(seconds / 60);
      unit = "minute";
    } else if (seconds < 86400) {
      amount = future ? Math.ceil(seconds / 3600) : Math.floor(seconds / 3600);
      unit = "hour";
    } else {
      amount = future ? Math.ceil(seconds / 86400) : Math.floor(seconds / 86400);
      unit = "day";
    }
    amount = Math.max(amount, 1);
    return future ? "in " + plural(amount, unit) : plural(amount, unit) + " ago";
  }

  function drawCountdowns() {
    document.querySelectorAll("[data-countdown]").forEach(function (element) {
      var date = new Date(element.dataset.countdown);
      if (!Number.isNaN(date.getTime())) element.textContent = countdown(date);
    });
  }

  /* Recompute date-driven status badges using the same rules as the server. */
  function drawClockStatuses() {
    document.querySelectorAll("[data-clock-status]").forEach(function (element) {
      var current = element.dataset.clockStatus;
      if (["upcoming", "live", "closed"].indexOf(current) === -1) return;

      var start = new Date(element.dataset.auctionStart);
      if (Number.isNaN(start.getTime())) return;

      var now = new Date();
      var end = element.dataset.auctionEnd
        ? new Date(element.dataset.auctionEnd)
        : new Date(start.getTime() + 86400000);
      if (Number.isNaN(end.getTime())) end = new Date(start.getTime() + 86400000);
      var status = now < start ? "upcoming" : now < end ? "live" : "closed";
      element.className = "status status-" + status;
      element.textContent = status;
    });
  }

  /* --- the quiet line ---------------------------------------------- */

  function drawHeartbeat(state) {
    if (!heartbeat) return;

    var text = heartbeat.querySelector(".beat-text");
    var collected = heartbeat.querySelector(".beat-collected");
    heartbeat.classList.remove("is-checking", "is-stalled");

    if (state === "checking") {
      heartbeat.classList.add("is-checking");
      text.textContent = "Checking for new listings\u2026";
    } else if (state === "failed") {
      heartbeat.classList.add("is-stalled");
      text.textContent = "Cannot reach the server";
    } else {
      text.textContent = "Checked " + ago(lastChecked);
    }

    if (lastCollected) {
      // Over a day without the collector running is a fault worth
      // showing, not a detail to bury.
      var stale = new Date() - lastCollected > 86400000;
      collected.textContent = "\u00b7 listings last collected " + ago(lastCollected);
      collected.classList.toggle("is-stale", stale);
    } else {
      collected.textContent = "";
    }
  }

  /* --- the prominent bar -------------------------------------------- */

  function describe(version) {
    var added = version.count - baseline.count;
    if (added > 0) return plural(added, "new listing") + " since you opened this page.";
    if (added < 0) return plural(-added, "listing") + " no longer listed.";
    // The count is unchanged but a timestamp moved. Something was
    // touched; whether it affects what this reader is looking at is not
    // something we can tell from the fingerprint, so do not claim it.
    return "Some listings may be updated.";
  }

  function changed(version) {
    return (
      version.count !== baseline.count ||
      version.newest !== baseline.newest ||
      version.changed !== baseline.changed
    );
  }

  function poll() {
    if (document.hidden) return;
    drawHeartbeat("checking");

    fetch("/api/version", { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(function (version) {
        failures = 0;
        lastChecked = new Date();
        if (version.collected) lastCollected = new Date(version.collected);

        if (changed(version) && !dismissed) {
          notice.querySelector(".update-text").textContent = describe(version);
          notice.hidden = false;
        }
        drawHeartbeat("idle");
      })
      .catch(function () {
        failures += 1;
        drawHeartbeat("failed");
        if (failures >= BACKOFF_MAX && timer) {
          clearInterval(timer);
          timer = null;
        }
      });
  }

  notice.querySelector(".update-refresh").addEventListener("click", function () {
    window.location.reload();  // keeps the current query string, so filters survive
  });

  notice.querySelector(".update-dismiss").addEventListener("click", function () {
    dismissed = true;
    notice.hidden = true;
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) poll();
  });

  drawHeartbeat("idle");
  drawCountdowns();
  drawClockStatuses();
  setInterval(function () {
    drawHeartbeat("idle");
    drawCountdowns();
    drawClockStatuses();
  }, TICK_MS);
  timer = setInterval(poll, POLL_MS);
  // First check shortly after load, so the line is doing something
  // visible rather than sitting still for a whole minute.
  setTimeout(poll, 5000);
})();
