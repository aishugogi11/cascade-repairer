# IOS_DEPLOY.md — App Store submission guide for Talk to My Trip

Everything needed to archive, upload, and submit the app. Facts below are pulled
from the project as of 2026-07-11 (Phase 17 complete); update the version table
per release.

---

## 1. App identity

| Field | Value |
|---|---|
| Display name | Talk to My Trip |
| Bundle ID | `com.zensoftware.talktomytrip` |
| SKU (App Store Connect) | `com.zensoftware.talktomytrip` |
| Apple ID (App Store Connect record) | `6789972026` |
| Team | Zen Software (`M59U69URHH`) |
| Marketing version | `1.0` (`MARKETING_VERSION`) |
| Build | `1` (`CURRENT_PROJECT_VERSION` — bump for every upload) |
| Minimum iOS | 17.0, iPhone-only, portrait-only |
| Dependencies | None (SwiftUI + WebKit + AVFoundation only) |
| Backend | `https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app` (hardcoded in `APIConfig.swift`; service must stay up while the app is live) |

## 2. URLs for App Store Connect

| Field | URL |
|---|---|
| Privacy Policy URL | `https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app/v1/legal/privacy` |
| Support URL | `https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app/v1/legal/support` |
| Marketing URL (optional) | leave blank or reuse the support URL |

Both are served by this repo's backend (`/v1/legal/*`), are on the access-gate
public allowlist (never gated), and must stay reachable for the life of the app.

## 3. App Review Information — critical

The app is gated by a shared demo access code. **No account exists** — the
reviewer enters the code once on the first screen.

- **Sign-in required:** No (there is no username/password; if the form insists,
  put the access code in the password field and anything in username).
- **Access code:** `cascade2026` — must match the `DEMO_ACCESS_CODE` env var on
  the Cloud Run service **exactly**. ⚠️ **Do not rotate the env var while a
  build is in review.**
- **Suggested review notes:**

  > This is a live travel-demo app built for the DeepLearning.AI Voice AI
  > Hackathon (July 18, 2026). No account is needed: on first launch, enter
  > access code **cascade2026** on the welcome screen.
  >
  > To try it: tap the microphone orb. A consent screen first explains that
  > voice conversations are processed by Vocal Bridge (speech), OpenAI (AI
  > replies), and Google Cloud (storage) — tap Continue, then say "book me
  > a trip to San Francisco, July 17 to 19." The assistant speaks 2–3
  > flight options; say "option one" to book, then agree when it offers to
  > arrange the rest — hotel, ride, dinner, and an activity cards appear on
  > the timeline. Tap any card to see why the AI chose it.
  >
  > The microphone activates only after consent and only for the voice
  > conversation; consent can be withdrawn anytime in the About screen.
  > Bookings are simulated demo data — no real travel is purchased and no
  > payment exists anywhere in the app.

## 4. Privacy questionnaire (App Store Connect → App Privacy)

Answers must match `PrivacyInfo.xcprivacy` (already in the app bundle):

| Question | Answer |
|---|---|
| Does the app collect data? | Yes |
| Audio Data (User Content) | Collected — App Functionality only, **not** linked to identity, **not** used for tracking |
| **Other User-Generated Content** (User Content — voice transcripts + trip data) | Collected — App Functionality only, **not** linked to identity, **not** used for tracking |
| Tracking | **No** (no tracking, no tracking domains) |
| Data linked to the user | None (no accounts; nothing is tied to an identity) |

⚠️ **Two data types must be declared, not one** — the app's
`PrivacyInfo.xcprivacy` manifest declares both Audio Data and Other User
Content; if the App Store Connect questionnaire lists only "Audio Data",
add **Other User-Generated Content** so the two can't be flagged as
inconsistent.

**Privacy Policy URL:** `…/v1/legal/privacy` · **User Privacy Choices URL**
(optional): also `…/v1/legal/privacy` — the policy's "Withdrawing consent"
and "Data deletion" sections are the privacy-choices content (the support
page is not).

Consistency notes: mic audio → Vocal Bridge (voice provider); conversation
text → OpenAI (AI processing); transcripts and trip data → BigQuery. The app
shows a first-use consent screen naming all three before the mic activates,
and consent is withdrawable in About. No ads, no analytics SDKs, no sale of
data — this matches the privacy policy page content.

## 5. Encryption / export compliance

`ITSAppUsesNonExemptEncryption = NO` is already in `Info.plist` (HTTPS only,
exempt). App Store Connect will not prompt; if it does, answer "None of the
algorithms mentioned."

## 6. Version page fields (Distribution → iOS App Version 1.0)

Copy-paste values for every field on the "iOS App Version" form, in the order
App Store Connect shows them:

**App Previews / Screenshots** — no app preview video needed (0 of 3 is fine).
Screenshots: 6.9" display set (iPhone 16/17 Pro Max class), taken straight off
the simulator, no device frames. Recommended set of 4: gate screen, orb +
booked timeline, cards mid-repair (broken → repairing), RecommendationSheet.

**Promotional Text** (170 chars max — editable anytime without re-review):

> Book a whole trip with your voice — and watch it heal itself when travel
> breaks. Your AI concierge talks, books, and repairs in real time.

**Description** (4,000 chars max):

> Talk to My Trip is a voice-first travel companion. Tap the orb, say where
> you want to go, and your AI concierge searches flights, reads you the
> options, and books the one you pick — then builds out the rest of the
> trip: hotel, ride, dinner, and something fun, appearing on a live
> timeline as they land.
>
> When travel breaks, the trip heals itself: a cancelled flight sets off
> background repairs across every affected booking while you keep talking
> to the assistant, and the timeline flips from broken to fixed in under a
> minute. Tap any card to see why the AI chose it and what it means for
> the rest of your trip.
>
> Built for the DeepLearning.AI Voice AI Hackathon. Access requires a demo
> invitation code.

**Keywords** (100 chars max, comma-separated, no spaces):

```
travel,voice,assistant,ai,trip,itinerary,concierge,flight,booking,planner
```

**Support URL:**

```
https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app/v1/legal/support
```

**Marketing URL** (optional): leave blank.

**Version:** `1.0` — must match the uploaded build's `MARKETING_VERSION`.

**Copyright:**

```
2026 Zen Software
```

(Adjust to the exact legal entity name on your Apple developer account.)

Elsewhere in App Store Connect (not on this page):

- **Subtitle** (App Information, 30 chars max): `Your trip, one conversation`
- **Category** (App Information): Travel; secondary: none
- **Age rating** (App Information, 7-step questionnaire): all "None"/"No"
  through steps 1–6 → calculated **4+**; step 7: Age Categories and Override =
  "Not Applicable", Age Suitability URL = blank → Save
- **Content Rights** (App Information): "No, this app does not contain, show,
  or access third-party content." ✅ (correct — all trip data is our own demo
  content; Vocal Bridge/OpenAI are service providers, not displayed
  third-party content)
- **License Agreement** (App Information): leave as Apple's standard EULA —
  do not upload a custom one
- **Pricing and Availability:** Free, all territories (or US-only — either fine)

## 7. Archive & upload

1. In Xcode: select the **TalkToMyTrip** scheme → destination **Any iOS Device
   (arm64)**.
2. Bump `CURRENT_PROJECT_VERSION` (every upload needs a unique build number;
   bump `MARKETING_VERSION` for user-visible releases).
3. Product → Archive → Distribute App → App Store Connect → Upload (automatic
   signing, Zen Software team).
4. In App Store Connect, attach the processed build to the version, fill the
   sections above, and Submit for Review.

Headless alternative:

```bash
cd ios/TalkToMyTrip
xcodebuild -project TalkToMyTrip.xcodeproj -scheme TalkToMyTrip \
  -destination 'generic/platform=iOS' archive \
  -archivePath build/TalkToMyTrip.xcarchive
xcodebuild -exportArchive -archivePath build/TalkToMyTrip.xcarchive \
  -exportOptionsPlist ExportOptions.plist -exportPath build/export
# then upload build/export/TalkToMyTrip.ipa via Xcode Organizer, Transporter,
# or `xcrun altool --upload-app`
```

## 8. Pre-submission checklist

- [ ] Backend deployed and green: `GET /v1/hello/gcp_check` on the Cloud Run URL
- [ ] `DEMO_ACCESS_CODE=cascade2026` set on the service (verify:
      `curl -X POST …/v1/auth/validate -H 'Content-Type: application/json' -d '{"code":"cascade2026"}'` → 200)
- [ ] Cloud Run `min-instances=1` / `max-instances=1` (in-process session state)
- [ ] Legal pages load publicly (no code): `/v1/legal/privacy`, `/v1/legal/support`
- [ ] The **updated** privacy policy (OpenAI + retention + withdrawal sections)
      is deployed — the live page must match what App Review reads
- [ ] One voice run on a **physical iPhone** (webview voice can't be exercised in
      the simulator): gate → book by voice → cards materialize
- [ ] Review notes contain the access code **exactly** as deployed
- [ ] Build number bumped since the last upload

## 9. After approval

- Rotating the access code (`--update-env-vars DEMO_ACCESS_CODE=…`) is safe any
  time **outside** an active review — live apps return to the gate on their
  next API call and accept the new code.
- The store build points at the dev Cloud Run URL; renaming/deleting that
  service breaks the shipped app silently (roadmap flags a custom domain as
  post-hackathon work).
- Demo quota reality: each full three-act demo run places 2 real outbound
  calls (Vocal Bridge: 10 calls/day, resets 00:00 UTC).
