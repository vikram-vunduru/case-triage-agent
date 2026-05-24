# KB-602: Dashboard Pages Load Slowly or Hang

**Category:** Performance & Browser
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-05-15
**Owner:** Web Platform Team

## Symptoms

- Dashboard pages take more than 10 seconds to render after the URL bar settles.
- A spinner or skeleton state stays visible indefinitely.
- The browser shows "Waiting for app.example.com" in the status bar but never finishes.
- Often only on specific machines or browsers; other devices work fine.

## Root cause

In 80% of reports the slowness is client-side, not server-side. The three common causes:

1. **Stale browser cache** holding an old `app.js` bundle that fights with the current API contracts.
2. **Browser extension interference**, especially ad blockers and privacy extensions that strip telemetry beacons our app waits on.
3. **Too many filters / widgets** on a single dashboard — the page renders 200+ chart widgets which exceeds the browser's main-thread budget.

## Resolution steps

1. Open the dashboard in an **incognito / private window** (this disables most extensions and uses an empty cache). If it loads quickly, you've confirmed it's a client-side issue.
2. In your normal window, **hard-refresh** with `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows / Linux) to bypass the cache.
3. If still slow, **disable browser extensions** one at a time — common culprits: uBlock Origin, Privacy Badger, Ghostery.
4. Reduce the number of widgets on the dashboard: edit the dashboard, remove unused charts, and split very large dashboards into multiple pages.
5. Check your network throughput at <https://fast.com> — anything below 5 Mbps will visibly slow our app.

## When to escalate

Escalate to Web Platform if:

- All four steps above completed with no change.
- Multiple users in the same org are affected (suggests a regional CDN issue).
- The browser DevTools Network tab shows API calls returning in >2s (backend issue, not client).

## Related articles

- KB-412 (Session cookie issues on Safari)
