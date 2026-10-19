# Setting up the daily upload

The code is finished and tested offline. What's left is the part only you can do: create the
developer apps and sign in once. Nothing here posts anything until you run `publish_daily.py`.

## 0. On the computer that will run it

- Python 3.10+ and ffmpeg installed (`ffmpeg -version` should work).
- In this folder: `pip install -r requirements.txt`
- `copy .env.example .env` (Windows) or `cp .env.example .env` (Mac/Linux). All secrets go in `.env`.
- On Windows use `python` where this guide says `python3`.

Check it works end to end without touching any network: `python3 -m unittest test_uploaders -v`

## 1. Instagram + Facebook (one Meta app covers both)

Instagram and Facebook share one login and one token here. This route (Facebook Login) lets the
script upload the video file directly, so you don't need a website to host the videos.

**Accounts first**
1. A Facebook Page you are admin of (create one if needed).
2. Your Instagram account switched to Professional (Business or Creator) and linked to that Page.
   (Instagram: Settings > Account type and tools; link the Page from Edit profile.)

**Meta app**
3. Go to developers.facebook.com > My Apps > Create App. Pick the use case that includes the Pages
   and Instagram APIs, and add Facebook Login for Business. (Meta renames these menus often, so
   follow the closest match.)
4. App settings > Basic: copy **App ID** and **App secret** into `.env` as `META_APP_ID` and
   `META_APP_SECRET`.
5. Tools > Graph API Explorer. Pick your app, click Generate Access Token, and add these
   permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `pages_manage_engagement`, `instagram_basic`, `instagram_content_publish`,
   `instagram_manage_comments`. In the dialog that follows, tick your Page and your Instagram
   account. Copy the token.
6. Run: `python3 meta_setup.py --user-token PASTE_TOKEN_HERE`
   It exchanges the token for a long-lived Page token, finds your Instagram ID, saves everything to
   `.env`, and tells you if any permission is missing. A Page token made this way normally never expires.

Keep the app in Development mode. As the app's admin and the Page's admin you should be able to use
these permissions on your own accounts without Meta's App Review. If you get a "permission not
granted" error, check this first.

## 1b. Homepage + privacy policy (both Google and Meta ask for these links)

The `docs/` folder has a ready homepage (`index.html`) and `privacy.html`. Open `privacy.html`, replace
`YOUR-EMAIL-HERE` with a contact email, then host the folder free with GitHub Pages: repo > Settings >
Pages > Deploy from a branch > main, folder `/docs`. The links become
`https://USERNAME.github.io/REPO/` and `https://USERNAME.github.io/REPO/privacy.html`.

Google says the homepage must be on a domain you own and have verified, and its page doesn't say whether
github.io counts. If the Branding page rejects the github.io address, the reliable fix is a cheap custom domain
pointed at GitHub Pages and verified in Google Search Console.

## 2. YouTube

1. console.cloud.google.com > create a project.
2. APIs & Services > Library > **YouTube Data API v3** > Enable.
3. OAuth consent screen: User type External, fill in the app name and your email, and add your Google
   account under **Test users**.
4. Credentials > Create credentials > OAuth client ID > application type **Desktop app**. Copy the
   Client ID and secret into `.env` as `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET`.
5. Run `python3 youtube_auth.py`. Your browser opens, you pick the account/channel and approve. The
   refresh token is saved to `.env` and the script prints the channel name it will upload to.
6. Back on the consent screen, change Publishing status from Testing to **In production**. While an app
   is in Testing, Google expires the sign-in after 7 days, which would silently stop your uploads. You'll see
   an "unverified app" warning when signing in; for your own account click Advanced and continue.
   (This 7-day rule is from my own knowledge, not something I could re-check today.)

**Watch out: possible private lock.** YouTube restricts videos uploaded through the API from
unaudited Google projects to private, whatever privacy you request. My sources disagreed on whether this
still applies, so the first upload decides it. The script prints a warning if YouTube made the video
private. If it did, the fix is Google's compliance audit (see "Quota and Compliance Audits" in the
YouTube API docs). Until then you can switch each video to public by hand in YouTube Studio.

## 3. Test safely, in this order

1. `python3 publish_daily.py --dry-run` shows what would happen and which platforms are configured.
2. YouTube as private: `python3 publish_daily.py --platforms yt --yt-privacy private --no-comment`
3. Facebook as a draft: `python3 publish_daily.py --platforms fb --fb-state DRAFT --no-comment`
4. Instagram has no private or draft mode. The first real post is public, so check the video first.

After a test upload, delete the test video in YouTube Studio / Facebook, then delete
`out/<date>/posted.json`, otherwise the script thinks that day is already done.

## 4. Run it every day

On a computer that is switched on at that time:

- Mac/Linux (`crontab -e`), 9:30 every day:
  `30 9 * * * cd /path/to/mathreel && python3 publish_daily.py >> publish.log 2>&1`
- Windows: Task Scheduler > Create Basic Task > Daily > Start a program: `python`, arguments
  `publish_daily.py`, start in the mathreel folder.

**Answer later instead of straight away** (gives people time to guess): schedule two runs.
Morning `publish_daily.py --no-comment`, afternoon `publish_daily.py --answers-only`.

The script makes the day's video itself if it doesn't exist yet. Safe to re-run: anything already
published is remembered and skipped, and a failure on one platform doesn't stop the others.

## 4b. GitHub Actions (always on, no computer needed)

1. On GitHub, create a **private** repository and upload this folder to it (never upload `.env`; it is
   already in `.gitignore`).
2. Repo > Settings > Secrets and variables > Actions > New repository secret. Add these six, copying the
   values from your `.env`: `META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_USER_ID`, `YOUTUBE_CLIENT_ID`,
   `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
3. Repo > Settings > Actions > General > Workflow permissions: choose **Read and write permissions**, so the
   job can save what it posted (in `state/`) and never double-posts on a re-run.
4. Actions tab > "Daily brain teaser" > Run workflow, with **Dry run** ticked, to test.
5. The daily time is the `cron` line in `.github/workflows/daily.yml` (UTC; 03:30 UTC = 09:00 IST).

The workflow posts without an answer comment for now (`--no-comment`); we'll revisit that.

## 5. Things I couldn't verify (check if something fails)

- Facebook's docs use both `finish` and `complete` for the last Reel upload step; the code tries
  `finish`, then `complete`.
- Commenting on a Facebook Reel and on a YouTube video can't be pinned through the APIs; pin the answer
  by hand if you want it at the top.
- If a Meta call fails, the error text from Meta is printed as-is and usually says exactly what's missing.
