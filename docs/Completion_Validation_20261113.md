# Validation of the 1.1 completion work

These are isolated development checks, not company-server or physical-device acceptance. No real customer messages were sent.

- Backend offline subset: no failures/errors; exact discovered/skipped counts are printed by `scripts/run_offline_review_tests.py`. Live API suites and opt-in SQL groups are explicitly excluded/skipped here.
- All 28 original SQL groups passed against disposable PostgreSQL. Added a 29th specialist SQL group, also passed. Focused reruns passed 21 outbound +11 training tests, including unknown-send reconciliation, no resend, paid/stale/ambiguous receivables, changed-balance cancellation and enrollment of previously unenrolled staff only. Specialist SQL checks verify real person/product/date filtering, private inflation sources, one actual obligation task and target-period sales evidence.
- Actual running API: teacher created/published source-cited training to visitor and finance accounts; their private assessments submitted real task results for manager review. Anonymous, other-role and cross-user GPS access were denied. Missing course was not exposed.
- Chromium: training, automation, outbound, specialists and live tracking at390/1280 widths without horizontal overflow or page exceptions; teacher could inspect answer keys, learner saw submitted results and no teacher key.
- Web: lint passed with two pre-existing CMS image warnings; generated Next route types and TypeScript passed. Production build generates54 pages/routes. New UI paths are inside the existing permissions shell.
- Native: TypeScript and six policy tests passed; Hermes bundles exported for Android/iOS; Expo prebuild generated both native projects. Verified camera/audio/location permissions and app version1.1.0/build2. Physical background-location continuity, camera/audio and file-sharing acceptance remain company/device checks.
- Persian handbook rendered successfully as35 A4 pages, with local Persian fonts. Updated source builds PDF/standalone HTML in CI.
- All44 PowerShell files parsed, including staged migration and selective enable switches. CI repeats backup/restore, kit guards, Android Release APK and iOS Release Simulator compilation. Final downloadable artifact SHA, CI conclusion and source commit are recorded by the actual workflow, not inferred from these local checks.

The first unrestricted default-discovery attempt also picked up live-API tests without their configured endpoint/JWT environment; it is not the offline runner. Those environmental errors are not counted as passing checks. The separately scoped API, offline and SQL results above are the evidence used for release readiness.

## Traccar extension validation

- Local offline subset:872 discovered,271 skipped, zero failures/errors. All30 disposable PostgreSQL groups passed341 tests; a later26-test focused rerun adds retryable burst-throttling and mock-location coverage. The bridge has dedicated JSON/header authentication tests through the actual application middleware.
- Actual JWT API and Chromium: manager device binding, own consented start/stop, trusted sample/live/history, duplicate suppression, outside-shift and revoked-device rejection; worker/manager visibility and390/1280 layouts passed. These samples are synthetic, not phone GPS.
- Web lint/types/production build passed (two existing CMS image warnings); updated Persian handbook rendered37 A4 pages. PowerShell parses45 files.
- CI now also runs the complete Linux-image build for PRs, before merge. Its smoke script sends real OsmAnd protocol requests through the official pinned Traccar container, verifies forwarding to the existing live dashboard, pre/post-shift exclusion, duplicate handling and forwarding-auth denial. Exact success is recorded in `validation/traccar-smoke.json` of the corresponding final offline artifact.
- Company HTTPS/reverse proxy, App Store availability, phone Always/Precise/background settings and actual locked-screen/offline/battery behavior still require company/device acceptance.

Additional authorization hardening: the bridge reads current map-write grants in the same database transaction, ends affected shifts when map permission is revoked, and binds each shift to the account security version. Role/profile/password revocation cannot silently reuse an old shift. The follow-up31 focused tests and all30 isolated SQL groups(348 tests) passed; offline subset877 discovered/276 skipped, no failures/errors. The first local rerun encountered a full disposable PostgreSQL disk; only owned build cache was removed, the synthetic fixture was restarted and the successful checks above were rerun.
