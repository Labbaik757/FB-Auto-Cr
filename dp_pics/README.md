# DP pictures (file-based, no AI generation)

Put the photos here. Python picks one per account, it never
generates a picture.

```
dp_pics/
    male/      <- photos of men
    female/    <- photos of women
```

Accepted files: `.jpg`, `.jpeg`, `.png`, `.webp`.

## How the pick works

1. **Gender** — read from the account's About page ("Gender:
   Female / Male") when visible; otherwise the first name is
   looked up in a small built-in list. If neither works, gender
   is unknown.
2. **Name** — read from the profile after login. A file named
   after the person wins first, e.g. `Sophia Wilson.jpg` for
   Sophia Wilson. A file named after the first name
   (`sophia-1.jpg`) wins next.
3. Otherwise any picture in the gender folder that was not used
   before. If every picture was already used, the first one is
   reused (the log says so).
4. Gender unknown + no picture named for the person = the
   account is skipped honestly. A wrong-gender DP is never
   applied.

## Tips

- Name files after the person when you have a photo for a
  specific account: `Sophia Wilson.jpg`, `James Carter.png`.
- `output/used_dp_pics.txt` records which pictures were already
  used. Delete a line (or the file) to make a picture available
  again.
- One account is never given a picture from the other gender's
  folder unless the file is named for that account.
