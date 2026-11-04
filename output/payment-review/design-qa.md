# Payment integration and preview recovery — 2026-11-04

## What was integrated

- GitHub `feature/payment-qr` and `main` both contained `bbaa84f` (order payment/receiving codes/converter) and `bd818e4` (team-provided FPS and Alipay HK artwork), directly descending from the previous collaboration snapshot `1031fb5`.
- These commits were fast-forwarded into a separate `codex/payment-integration-2026-11-04` branch. Existing sharing, Profile, Buddy/groups, lost-and-found, Messages, languages and visual design remain.
- Migration 0009 adds PaymentCode. It was applied only to the isolated synthetic review database for this pass; the original local database and online databases were not migrated.
- Static parity is deliberately a simulation: the existing on-loan borrower order #3 gains a payment-method entry, and Profile gains sample receiving settings. Original source order roles/statuses and confirmation forms are preserved.

## Corrections made during integration

1. **Preview startup: restored.** Initially neither local preview port had a listener. The static files were intact. Replaced the short-lived server workflow with `tools/preview_server.py` and `start-preview.cmd`: background server, loopback-only bind, checkout-specific response identity, readiness check and safe repeat invocation. The helper never kills an occupied port. Windows fallback can use system Python if the local venv is broken. A computer restart still requires running the helper again.
2. **Charges: clarified.** The initial payment page called full rent + deposit “Total to pay” despite existing confirmation flags. It now labels full order charges, displays existing bilateral rent/deposit confirmations, and says the platform does not calculate an outstanding balance. Extensions/partial payments cannot be inferred from these flags. Both-confirmed fees show a clear duplicate-payment caution; original confirmations remain self-reported, not bank evidence.
3. **FX failure: handled.** Validates the HKD base, positive finite rates and update timestamps inside the protected fallback path. Invalid data returns cached unavailability instead of a server error or misleading converted amount. This review used a deliberately disabled local provider; no live rates or payment details were sent out.
4. **Menus and layout: checked.** Alipay supports Escape and focus restoration. Static payment layout is constrained to a readable desktop width, with natural single-column mobile cards and native dialogs. All four channel variants retain the provided artwork.

## Verification

- Full Django suite: **143 tests passed** (29 payment tests); system check clean. `makemigrations --check --dry-run`: no changes detected.
- Existing demo-core rules: **14 passed**. JavaScript syntax checks passed for 11 maintained demo/backend payment files.
- Rebuilt static preview from the frozen sanitized baseline; new pages exist in Simplified Chinese, Traditional Chinese and English. 316 shareable HTML pages and 17,521 local references checked; zero missing targets. All six new payment routes and their initial hidden auth gates were checked.
- Browser: restored `/hans/buddy/2/` from an initially refused connection; verified its activity heading and group entry. New helper launches independently of the invoking process, recognizes its own checkout and reuses the existing listener without duplication. A temporary second-port launch smoke was stopped after verification.
- Static payment: guest route is locked → demo login → same order #3 payment route; HKD 108.00 and explicit fixed example CNY 91.80; Alipay expand/Escape/refocus, Alipay HK placeholder dialog/Escape. No payment app or real QR exists.
- Static receiving settings: add WeChat sample channel → reload retains it → remove channel. State is per-tab and belongs to Demo, separate from Jamie’s sample methods.
- Backend browser: signed-out payment route redirects to login. Normal local-file sign-in with a synthetic `.invalid` account; unrelated account denied; matching borrower sees accepted order charges, bilateral confirmations and eligible QR channels. The opened image is visibly “DEMO ONLY / NOT A PAYMENT CODE”; Escape closes the dialog. Deliberate FX failure leaves the HKD charges intact with a clear message.
- Actual browser widths: static payment at 1280 and 390, static settings at 390, backend payment at 390. No document-level horizontal overflow found in these checks. Final screenshot captures are below.

## Screenshots

- [Static desktop payment](payment-desktop.jpg)
- [Static mobile payment](payment-mobile.jpg)
- [Static mobile receiving settings](settings-mobile.jpg)
- [Static nonpayable placeholder](demo-placeholder.jpg)
- [Backend synthetic placeholder](backend-placeholder.jpg)

## Remaining boundaries

- QR recognition, channel account ownership/scannability, settlement currencies and actual payment on physical phones remain unverified. No real QR, funds, payment confirmation or transaction was used for this review.
- Backend payments are direct borrower-to-lender payments. There is no automatic verification, escrow, charge, refund processor or reliable monetary balance ledger.
- The static preview has no real accounts, uploads, exchange-rate requests or payment state mutation. Its example rate is not financial information.
- Browser viewport checks do not establish physical-device keyboard or full accessibility compatibility. Manual message refresh remains unchanged.
- The 127.0.0.1 preview works only on the computer running the helper; friends should clone the integration branch and follow COLLABORATION.md locally.
- No Render or Sites deployment, main-branch push, private QR/data upload or production mutation was performed by this integration.
