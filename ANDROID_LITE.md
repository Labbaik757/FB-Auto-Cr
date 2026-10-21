# FB Auto Create → Android Setup (Facebook Lite App Only)

Added 2026-10-21 as a second setup **inside Mode 2 (FB Auto Create)**.
When you pick Mode 2 you now choose: **1 = Browser Setup** (the
original one, untouched) or **2 = Android Setup** (this one). The
Android Setup creates Facebook accounts **inside the Facebook Lite
Android app** (`com.facebook.lite`) on an emulator or a real Android
phone. It lives in its own file:
`automation/android_lite_register.py`.

## What you need

1. **An Android emulator or phone**
   - Emulator: use your Android Emulator Launcher (creates devices
     with the official Android SDK — `adb` comes with it), OR
   - Real phone: USB debugging ON (Developer options), connected by USB, OR
   - **The same phone the tool is running on (Termux)** — see below.
2. **Facebook Lite installed** on that device (Play Store), or an APK
   file — the mode asks for the APK path if Lite is missing.
3. Nothing else: the mode uses only `adb` + Android's built-in
   `uiautomator`. No new pip packages.

## Running in Termux on the phone itself

This is the mobile way: Termux runs the tool on the phone, and the
tool launches the **real Facebook Lite app on that same phone** —
exactly like the Browser Setup launches a browser on a PC. No
emulator, no second phone.

One-time setup:

1. Install the tool in Termux (`pkg install python git android-tools`,
   `git clone ...`, `pip install -r requirements-termux.txt`).
   Do NOT use the PC `requirements.txt` on Termux: it contains
   playwright, which has no Android package — pip aborts the whole
   install and nothing gets installed.
2. On the phone: Settings → Developer options → **Wireless debugging
   ON** (keep Wi-Fi on).
3. Run the tool, choose Mode 2 → Setup 2 (Android Setup). The tool
   detects Termux and guides you: open Wireless debugging → "Pair
   device with pairing code", type the PORT and 6-digit CODE it asks
   for (keep Termux side-by-side/split screen so the pairing screen
   does not close), then type the main connection PORT shown on the
   Wireless debugging screen.
4. Done — pairing is one-time. From then on the tool connects by
   itself and launches Lite on your phone for every run.

## How to run

```
python main.py
Select Mode -> 2 (FB Auto Create)
Select Setup -> 2 (Android Setup)
```

Then: password type (same as other modes) → how many accounts →
where contacts come from:

- **Saved Outlook emails** — if Mode 4 saved `outlook_accounts.txt`,
  those emails are offered automatically, one per FB account.
- **Typed email** — you type one email per account.
- **Mobile number** — you type one number per account
  (confirmation code is typed by you in the console when Lite asks).

## Flow per account

Launch Lite (app data wiped first) → Create new account → First/Last
name → Date of birth → Gender → Email/Number → Password → Sign Up →
dialogs ("Not now" / "Skip") auto-dismissed → confirmation code if
asked → success when the feed opens.

Accounts are saved to **`android_lite_accounts.txt`** in the output
folder as:

```
email_or_number|password|Full Name|DD-MM-YYYY|Gender|facebook_lite
```

Accounts that end on a confirmation/identity screen are saved too,
marked "verification pending".

## If a step fails

The mode prints the texts it can actually see on the screen
(`Screen par ye texts mile: [...]`). Send that line when reporting a
problem — the wording Facebook Lite shows lives in ONE config block
at the top of `android_lite_register.py` (`TEXTS = {...}`), so a
Lite UI wording change is a one-place fix.

Notes:

- DOB spinner pickers (in some Lite versions) ask you to set the date
  in the emulator once and press Enter — typed date fields are
  handled automatically.
- Between accounts the app data is wiped and there is a 20–40s pause.
- Test with **1 account first**.

## OTP AUTO — the PC system, now on Android too

Same logic as Mode 2's Browser Setup:

- Put your numbers in **Number_List.txt** (project folder), one per
  line: `number` or `number|sms_url` (comma also works) — exactly
  the PC format.
- In the Android Setup source menu, pick **Number_List.txt**. For
  every number that has an SMS link, the confirmation code is
  **fetched from the link and typed automatically** — resend taps
  included (up to 3 resend+fetch rounds, like the PC).
- No SMS link (or typed email/number): the code is typed by hand in
  the console, as before.
- Saved lines in `android_lite_accounts.txt` end with `|confirmed`
  when the OTP step completed and the feed opened (a fully verified
  account, like the PC's complete IDs), or `|pending` when Facebook
  held the account for its own verification.
- Note: on PC the saved line also carries the UID + cookies because
  a browser exposes them. The Lite app keeps its login data inside
  the app's private storage, which Android does not let any tool
  read without root — so on Android the saved ID is the
  number/email + password + full details, with the OTP confirmed.

## Auto setup (one time) — nothing to prepare by hand

On the first run the tool prepares itself:

- Creates the `lite_apks/` folder and a blank `Number_List.txt`
  template (with the format written inside) if they don't exist,
  and makes sure the output folder exists.
- If fewer than 2 Lite versions are in the folder, it stocks them
  once: it **pulls the phone's own installed Lite APK** (the safest
  copy — it's the official app already on the device) and tries to
  download up to 2 more versions, keeping only real APK files
  (size + signature-header check, duplicates removed).
- Once 2+ versions exist, this setup never runs again.

## Rotating Lite versions (different version per account)

A phone can only have ONE Lite version installed at a time, so the
mode rotates versions for you:

1. Create a folder named **`lite_apks`** next to `main.py` (or in
   your home folder, or `/sdcard/lite_apks` in Termux).
2. Put 2–4 **official Facebook Lite APKs of different versions**
   in it (e.g. from APKMirror).
3. The mode installs the next version before every account
   (downgrades allowed), prints which version each account used,
   and the account data is wiped after install — so accounts are
   created across different Lite versions, one after another.
   If an install fails, it simply continues with the installed
   version and tells you.

## Keeping accounts from getting linked/suspended

What actually links accounts created on one phone, and what the
mode does about each:

- **App data / Lite's own device ID** — wiped (`pm clear`) before
  every account, so Lite generates fresh app-level IDs.
- **IP address** — the strongest signal. `proxies.txt` rotation
  (you'll be asked y/n), or on mobile data the built-in option to
  toggle Airplane mode yourself before each account for a fresh IP.
- **Lite version** — rotated from `lite_apks` (above).
- **Speed** — 45–90s random gap between accounts; creating many
  accounts back-to-back at machine speed is the #1 trigger. Keep
  daily counts modest on one device.
- **What cannot be changed without root:** IMEI/Android ID — but
  Android 10+ does not let Lite read the IMEI anyway, and the items
  above are what Facebook actually weighs.
- ⚠️ **Warning:** every account wipes Lite's data — do NOT stay
  logged into your personal account in Facebook Lite on that phone
  (keep your personal account in the main Facebook app instead).
- In Termux, run `termux-wake-lock` and turn OFF battery
  optimization for Termux, so a long run is not killed mid-account.

## Different Facebook Lite versions

Lite versions word their screens differently ("Create New Account"
vs "Create new account", buttons "Next" vs "Continue", and in some
versions Gender comes before Date of birth). This mode is built for
that: all known wording variants live in the `TEXTS` block at the top
of `android_lite_register.py`, the DOB/Gender steps run in whichever
order the screen presents them, a single full-name field is handled,
and if a version puts the password field on the same screen as the
email/number, that is filled there too. So an account that can be
created on any given Lite version, this mode can create.

## Proxies (permanent, all modes)

Put your proxies in **`proxies.txt`** next to `main.py` — every mode
finds them automatically and rotates one proxy per account, and you
never type proxies in the terminal again. **Proxies stay optional:**
whenever a mode finds `proxies.txt` it first asks
`use karni hain? (y/n)` — answer `n` and that run goes direct (in
Modes 1/4 the old manual prompt then appears as before, where Enter
also means direct).

- Mode 1 (HTTP): already loads `proxies.txt` first.
- Mode 2 (FB Auto Create) and Mode 3 (FB Automation): every browser
  context gets the next proxy automatically.
- Mode 4 (Outlook): per-context rotation (already built in).
- Mode 2 → Android Setup (this one): applied on the Android device per account —
  no-password proxies via the Android global proxy setting; proxies
  WITH username/password on an **emulator** by relaunching it with
  `-http-proxy` (Android's own system proxy cannot do passwords, so
  on a real phone use an emulator, or whitelist your IP with your
  proxy provider so no password is needed).

No `proxies.txt` = direct connection, exactly as before.
