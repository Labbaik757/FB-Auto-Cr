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
   - Real phone: USB debugging ON (Developer options), connected by USB.
2. **Facebook Lite installed** on that device (Play Store), or an APK
   file — the mode asks for the APK path if Lite is missing.
3. Nothing else: the mode uses only `adb` + Android's built-in
   `uiautomator`. No new pip packages.

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
