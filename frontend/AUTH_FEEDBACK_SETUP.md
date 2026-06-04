# Auth Gate + Feedback — Setup (what you need to do)

The code is done. To turn it on you need a **Firebase project** (free Spark plan
is plenty). ~10 minutes, one-time. Nothing to deploy — it's all client-side.

## What this gives you
- **Google sign-in gate** — nobody reaches any Feynman screen until they sign in
  and complete a tiny profile (name + phone; email comes from Google).
- **Exit-intent survey** — when a tester moves to leave the page, a 5-question
  survey + 3 free-text prompts (liked / disliked / future) appears.
- **Always-on feedback button** — bottom-left, opens a quick manual form anytime.
- All of it lands in **Firestore** (`users` and `feedback` collections) that you
  can read in the Firebase console or export to CSV.

---

## Step 1 — Create the Firebase project
1. Go to <https://console.firebase.google.com> → **Add project**. Name it
   (e.g. `feynman-cohort`). Google Analytics is optional — skip it for now.

## Step 2 — Register a Web app
1. In the project, click the **`</>`** (Web) icon → register an app
   (nickname e.g. `feynman-web`). **Do not** enable Firebase Hosting.
2. Firebase shows a `firebaseConfig` object. Keep that tab open — you'll copy
   these values in Step 5.

## Step 3 — Enable Google sign-in
1. Left nav → **Build → Authentication → Get started**.
2. **Sign-in method** tab → **Google** → enable → pick a support email → **Save**.

## Step 4 — Create Firestore
1. Left nav → **Build → Firestore Database → Create database**.
2. Start in **production mode** → pick a region close to your users
   (`asia-south1` (Mumbai) for India) → **Enable**.
3. Open the **Rules** tab, paste the rules below, **Publish**:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // A signed-in user can read/write only their own profile.
    match /users/{uid} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
    // Any signed-in user can submit feedback; nobody can read/edit it from
    // the client (you read it in the console).
    match /feedback/{doc} {
      allow create: if request.auth != null;
      allow read, update, delete: if false;
    }
  }
}
```

## Step 5 — Wire the config into the app
1. `cp frontend/.env.example frontend/.env.local`
2. Fill `frontend/.env.local` from the `firebaseConfig` in Step 2:
   ```
   VITE_FIREBASE_API_KEY=AIza...
   VITE_FIREBASE_AUTH_DOMAIN=feynman-cohort.firebaseapp.com
   VITE_FIREBASE_PROJECT_ID=feynman-cohort
   VITE_FIREBASE_STORAGE_BUCKET=feynman-cohort.appspot.com
   VITE_FIREBASE_MESSAGING_SENDER_ID=1234567890
   VITE_FIREBASE_APP_ID=1:1234567890:web:abc123
   VITE_AUTH_DISABLED=false
   ```
3. Restart the dev server (`pnpm dev`) — Vite only reads env at startup.

## Step 6 — Authorize your domains
**Authentication → Settings → Authorized domains.** `localhost` is there by
default. **Add the domain you deploy the cohort build to** (e.g. your Vercel/
Netlify URL), or Google sign-in will fail with `auth/unauthorized-domain`.

---

## Viewing the data
- **Firestore → Data** → `users` (one doc per tester) and `feedback` (one doc
  per submission, with `variant: exit | manual`, the MCQ `ratings` + readable
  `ratingLabels`, the free-text fields, plus `uid`, `email`, `name`, timestamp,
  and which lecture they were in).
- Export: use the Firebase console or `gcloud firestore export` if you want CSV.

## Local dev without Firebase
Set `VITE_AUTH_DISABLED=true` in `.env.local` to skip the gate entirely while
developing. Feedback writes become no-ops (logged to the console). Flip it back
to `false` for anything you hand to a tester.

## Notes
- The Firebase web config is **safe to expose** — it's not a secret. Access is
  controlled by the Firestore rules above and the authorized-domains list.
- Free Spark plan limits (50K reads / 20K writes per day) are far beyond a
  feedback cohort. Cost: **$0**.
- Phone numbers are collected as plain profile text (not phone-auth verified).
  If you later want OTP verification, that's a separate Firebase Phone Auth
  setup — out of scope for a feedback build.
