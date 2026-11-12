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
