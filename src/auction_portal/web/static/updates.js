/* Offers a refresh when the collector finds something new.
 *
 * Deliberately never reloads on its own. Someone reading a listing, or
 * halfway through filling in a price filter, should not have the page
 * pulled out from under them. We ask instead.
 *
 * If the browser tab is hidden we stop polling, so a forgotten tab does
 * not sit hitting the server all day.
 */
(function () {
  "use strict";

  var POLL_MS = 60000;      // once a minute is plenty; data moves hourly
  var BACKOFF_MAX = 15;     // give up after this many consecutive failures

  var root = document.getElementById("update-notice");
  if (!root) return;

  var baseline = {
    count: parseInt(root.dataset.count, 10),
    newest: root.dataset.newest || null,
    changed: root.dataset.changed || null,
  };

  var failures = 0;
  var dismissed = false;
  var timer = null;

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  function describe(version) {
    var added = version.count - baseline.count;
    if (added > 0) {
      return plural(added, "new listing") + " since you opened this page.";
    }
    if (added < 0) {
      // Listings are withdrawn, or expire 90 days after their auction.
      return plural(-added, "listing") + " no longer listed.";
    }
    return "Some listings have been updated.";
  }

  function show(version) {
    if (dismissed) return;
    root.querySelector(".update-text").textContent = describe(version);
    root.hidden = false;
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

    fetch("/api/version", { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(function (version) {
        failures = 0;
        if (changed(version)) show(version);
      })
      .catch(function () {
        // The portal may simply be restarting. Stop after a while rather
        // than logging errors forever.
        failures += 1;
        if (failures >= BACKOFF_MAX && timer) {
          clearInterval(timer);
          timer = null;
        }
      });
  }

  root.querySelector(".update-refresh").addEventListener("click", function () {
    // Reloads with the current query string, so filters survive.
    window.location.reload();
  });

  root.querySelector(".update-dismiss").addEventListener("click", function () {
    dismissed = true;
    root.hidden = true;
  });

  // Check as soon as the tab is looked at again, not just on the timer.
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) poll();
  });

  timer = setInterval(poll, POLL_MS);
})();
