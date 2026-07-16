# IOS_DEPLOY.md — App Store submission guide for Talk to My Trip

Everything needed to archive, upload, and submit the app. Facts below are pulled
from the project as of 2026-07-16. The immediate path is the **same-build
Unlisted App Distribution recovery** below; do not archive or upload a replacement
binary while Apple reviews v1.0 (3).

---

## 0. Immediate recovery — Unlisted App Distribution

Apple rejected iOS 1.0 (3) on 2026-07-16 under Guideline 3.2 because the app's
limited hackathon-event audience did not match public, searchable App Store
distribution. Unlisted distribution is the correct option: Apple explicitly
supports limited audiences and special events, the app installs from the App
Store through a direct link, and the existing access-code gate remains the
unauthorized-use mechanism. Unlisted is hidden, not private; anyone with the link
can reach the product page, but only a valid code unlocks the app.

Official references:

- [Unlisted App Distribution](https://developer.apple.com/support/unlisted-app-distribution/)
- [Set distribution methods](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/set-distribution-methods)
- [Unlisted request form](https://developer.apple.com/contact/request/unlisted-app/)
- [Expedited App Review request](https://developer.apple.com/contact/app-store/?topic=expedite)

### Do this now, in this order

1. In **Pricing and Availability → App Distribution Methods**, leave the app set
   to **Public**. This is counterintuitive but required: Apple's request flow
   starts from Public and Apple changes it to Unlisted upon approval. Do not
   select Private/Custom App.
2. Edit **iOS App 1.0 → App Review Information → Notes** and replace the opening
   with the unlisted review notes in §3 below. Keep the access code and full test
   script.
3. On the unresolved submission, click **Edit**, save the metadata, **Add for
   Review**, then **Resubmit to App Review** using the existing v1.0 (3) build.
   Do not upload build 4.
4. Immediately submit the authenticated [Unlisted App Distribution
   request](https://developer.apple.com/contact/request/unlisted-app/) for Apple
   ID `6789972026`, using the request text below.
5. Immediately submit an [expedited App Review
   request](https://developer.apple.com/contact/app-store/?topic=expedite) using
   the event text below. This is the documented event-related expedite case.
6. Reply to the Guideline 3.2 message with the response below. Monitor App Review
   and the developer-account email closely; answer any follow-up immediately.
7. On approval, verify **Pricing and Availability** says **Unlisted App**, open
   the generated direct link on a device that is not signed into App Store
   Connect, install, enter the code, and record the URL in §9.

### Reply to App Review — paste after resubmitting and filing the request

> Hello App Review,
>
> Thank you for the guidance. We agree that Unlisted App Distribution is the
> correct method for Talk to My Trip. This is a final limited-audience app for
> participants, judges, and invited attendees of the DeepLearning.AI Voice AI
> Hackathon, a special event. Users install it on personal, unmanaged devices;
> they are not employees or clients of one organization managed through Apple
> Business Manager, so Custom App distribution is not a fit.
>
> We have kept the app record set to Public as Apple's unlisted-request process
> requires, updated the Review Notes, resubmitted the existing final iOS 1.0 (3)
> build without uploading a replacement binary, and submitted the Unlisted App
> Distribution request and an event-related expedited-review request for Apple
> ID 6789972026. The app is not a beta or a substitute for TestFlight. Its
> access-code screen prevents unauthorized use, and the non-expiring reviewer
> code and complete test instructions remain in
> App Review Information.
>
> Original submission ID: 6945d2a4-5010-40d6-b283-e58e52ae75c6.
>
> Please continue review for unlisted distribution. We are available immediately
> if you need any additional information.

### Unlisted request — purpose/audience text

> We request Unlisted App Distribution for Talk to My Trip, Apple ID
> 6789972026, iOS version 1.0 (3). This is a final release for the limited
> audience of participants, judges, and invited attendees of the
> DeepLearning.AI Voice AI Hackathon, a special event. The audience uses personal,
> unmanaged iPhones and is not contained within one Apple Business
> Manager or Apple School Manager organization. We will distribute the app only
> through its direct App Store link. The app includes a server-validated access
> code to prevent unauthorized use. It is not a beta, prerelease build, or an
> alternative to TestFlight.

### Expedited App Review request — event text

> Talk to My Trip (Apple ID 6789972026, iOS 1.0 (3), original submission ID
> 6945d2a4-5010-40d6-b283-e58e52ae75c6) is directly associated with the
> DeepLearning.AI Voice AI Hackathon, "The Complete Trip," taking place in
> Mountain View, California on July 18, 2026. We are a participating team and
> built this app as the native iPhone surface for our required live demonstration.
> Apple reviewed the original July 11 submission on July 16 and advised us to use
> another distribution method under Guideline 3.2. We immediately adopted that
> guidance: the unchanged final build has been resubmitted for review, and we
> filed the separate Unlisted App Distribution request because event participants
> and judges use personal unmanaged devices. We respectfully request expedited
> review so the direct App Store link can be available for the July 18 event. The
> reviewer access code and complete test instructions are in App Review
> Information, and our team is available immediately for questions.

The same-build path is deliberate. Apple allows rejected metadata/distribution
issues to be corrected and resubmitted without a replacement binary. Approval
timing remains Apple's; keep the TestFlight/Xcode install and web demo ready for
the July 18 event.

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
| Build | `3` (`CURRENT_PROJECT_VERSION`; do not bump during the unlisted recovery) |
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
- **Review notes for the unlisted resubmission:**

  > Talk to My Trip 1.0 (3) is the final special-event app for participants,
  > judges, and invited attendees of the DeepLearning.AI Voice AI Hackathon. It
  > is intended for **Unlisted App Distribution**, not public discovery, and is
  > not a beta or a TestFlight substitute. No account is needed: on first launch,
  > enter the non-expiring reviewer access code **cascade2026** on the welcome
  > screen. This unlocks all app functionality.
  >
  > To try it: tap the microphone orb. A consent screen first explains that
  > voice conversations are processed by Vocal Bridge (speech), OpenAI (AI
  > replies), and Google Cloud (storage) — tap Continue, then say "book me
  > a flight from JFK to Los Angeles on July 21, 2026." The assistant speaks 2–3
  > flight options; say "option one" to book, then agree when it offers to
  > arrange the rest — cards for the hotel, ride, dinner, and an activity
  > appear on the timeline. Tap any card to see why the AI chose it.
  >
  > The microphone activates only after consent and only for the voice
  > conversation; consent can be withdrawn anytime in the About screen.
  > Bookings are simulated demo data — no real travel is purchased and no
  > payment exists anywhere in the app.

  The JFK → LAX July 21 path returned three options through the deployed app
  backend on 2026-07-16. InstaFlights content can drift; if re-review is delayed,
  re-run the README's live-pair probe and update only this spoken route/date if
  needed.

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
- **Binary category follow-up:** build 3 was compiled with
  `LSApplicationCategoryType=public.app-category.business` even though App Store
  Connect correctly says Travel. Do not replace build 3 during the unlisted
  recovery; before the next archive, change both Xcode configurations to
  `public.app-category.travel`.
- **Age rating** (App Information, 7-step questionnaire): all "None"/"No"
  through steps 1–6 → calculated **4+**; step 7: Age Categories and Override =
  "Not Applicable", Age Suitability URL = blank → Save
- **Content Rights** (App Information): "No, this app does not contain, show,
  or access third-party content." ✅ (correct — all trip data is our own demo
  content; Vocal Bridge/OpenAI are service providers, not displayed
  third-party content)
- **License Agreement** (App Information): leave as Apple's standard EULA —
  do not upload a custom one
- **Pricing and Availability:** Free; leave the distribution method **Public**
  until Apple approves the unlisted request and changes it to **Unlisted App**.

## 7. Archive & upload

**Not used for the v1.0 (3) unlisted recovery.** This section applies only to a
later binary after Phase 36 is settled.

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
- [ ] Reviewer route/date re-probed against the deployed voice path
- [ ] Review notes contain the access code **exactly** as deployed
- [ ] Review notes explicitly say **Unlisted App Distribution** and final/not beta
- [ ] Existing v1.0 (3) selected; no replacement build uploaded
- [ ] Unlisted request submitted for Apple ID `6789972026`
- [ ] Event-related expedited App Review request submitted

## 9. After approval

- Distribution method reads **Unlisted App** and the direct link installs on a
  clean device. Record the approved URL here: `PENDING`.
- Share the direct link only with the event audience. The page is hidden from
  search/charts/categories but is not private; the access code remains required.
- Rotating the access code (`--update-env-vars DEMO_ACCESS_CODE=…`) is safe any
  time **outside** an active review — live apps return to the gate on their
  next API call and accept the new code.
- The store build points at the dev Cloud Run URL; renaming/deleting that
  service breaks the shipped app silently (roadmap flags a custom domain as
  post-hackathon work).
- Demo quota reality: each full three-act demo run places 2 real outbound
  calls (Vocal Bridge: 10 calls/day, resets 00:00 UTC).
