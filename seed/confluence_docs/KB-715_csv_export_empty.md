# KB-715: CSV Export Returns an Empty or Truncated File

**Category:** Data Export
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-04-28
**Owner:** Reporting Team

## Symptoms

- User clicks **Export to CSV** and gets a downloaded file, but the file is:
  - Empty except for the header row, or
  - Truncated to fewer rows than the user expected (e.g. 1,000 rows instead of 50,000), or
  - Contains data but the rows look wrong (different columns than the on-screen view).

## Root cause

Three causes by frequency:

1. **Date range filter** on the report is narrower than the user remembers — most often defaults to "last 30 days" after a session refresh, hiding older records.
2. **Row cap hit** — the synchronous CSV export caps at **10,000 rows** to protect browser memory. Larger exports must use the asynchronous Bulk Export feature.
3. **Saved filter mismatch** — the on-screen view uses one saved filter while the export uses a different one (typically the "default" filter).

## Resolution steps

1. **Verify the filter visually** before exporting:
   - Date range: scroll up on the report; the current range is shown at the top.
   - Status filter: confirm it isn't accidentally set to "Closed" when you want all records.
2. If the CSV is **exactly 10,000 rows or fewer than expected**, switch to **Bulk Export**: Settings → Data → Bulk Export → New Job. Bulk Export emails you a download link when ready (usually 5-15 minutes).
3. If the on-screen view shows different rows than the CSV:
   - Click **Reset filters** before exporting.
   - Re-apply only the filter you want.
4. Open the downloaded CSV in a text editor (not Excel) to verify the actual row count — Excel sometimes silently truncates at ~1M rows.

## When to escalate

Escalate to Reporting if:

- User has confirmed filter is correct, exported less than 10K rows, and still gets an empty file.
- Bulk Export jobs never email a download link after 1 hour.
- Customer needs an export larger than 5M rows (requires a different pipeline).

## Related articles

- KB-803 (API rate limit exceeded — for programmatic exports)
