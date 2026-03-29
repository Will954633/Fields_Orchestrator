# Fields Voice Agent — Android App Setup

Step-by-step instructions to get the app running on your phone.

---

## What You Need

- A Mac or Windows PC
- An Android phone (Android 8.0+ / API 26+)
- A USB cable to connect your phone to your computer
- Wi-Fi or mobile data (the app talks to your VM over the internet)

---

## Step 1: Install Android Studio

1. Go to https://developer.android.com/studio
2. Download Android Studio (it's free)
3. Run the installer — accept all defaults
4. When it asks about SDK components, leave everything checked
5. Wait for the initial setup to finish (it downloads ~2GB of SDK files)

This takes about 10-15 minutes on a decent connection.

---

## Step 2: Get the Code onto Your Computer

**Option A — Download from GitHub (easiest):**

1. Go to https://github.com/Will954633/Fields_Orchestrator
2. Click the green **Code** button → **Download ZIP**
3. Unzip the file
4. The Android project is inside: `Fields_Orchestrator-main/voice-agent/android-app/`

**Option B — Clone with git (if you have git installed):**

```bash
git clone https://github.com/Will954633/Fields_Orchestrator.git
cd Fields_Orchestrator/voice-agent/android-app
```

---

## Step 3: Open the Project in Android Studio

1. Open Android Studio
2. Click **"Open"** (not "New Project")
3. Navigate to the `voice-agent/android-app` folder and select it
4. Click **OK**
5. Android Studio will start syncing the project — this downloads dependencies (1-2 min)
6. If it asks to install SDK version 35 or any missing components, click **Install** and wait

**If you see a "Gradle sync failed" error:**
- Look at the error message at the bottom
- It usually means a missing SDK version — click the blue link in the error to auto-install
- Then click **"Try Again"** or **File → Sync Project with Gradle Files**

---

## Step 4: Enable Developer Mode on Your Phone

You only need to do this once:

1. On your phone, go to **Settings → About Phone**
2. Scroll down to **"Build Number"**
3. Tap **"Build Number" 7 times** rapidly
4. You'll see a toast message: "You are now a developer!"
5. Go back to **Settings → System → Developer Options**
6. Turn on **USB Debugging**

(On Samsung phones: Settings → About Phone → Software Information → Build Number)

---

## Step 5: Connect Your Phone

1. Plug your phone into your computer with a USB cable
2. Your phone will ask **"Allow USB debugging?"** — tap **Allow** (check "Always allow" too)
3. In Android Studio, look at the **toolbar** near the top — you should see your phone's name appear in the device dropdown (e.g., "Pixel 7" or "Samsung SM-G991B")

**If your phone doesn't appear:**
- Try a different USB cable (some are charge-only)
- Make sure USB Debugging is on (Step 4)
- On your phone, pull down the notification shade and tap the USB notification → change to **"File Transfer"** mode

---

## Step 6: Build and Run

1. In Android Studio, make sure your phone is selected in the device dropdown (top toolbar)
2. Click the **green play button ▶️** (or press Shift+F10)
3. The first build takes 1-3 minutes (subsequent builds are faster)
4. The app will install and open on your phone automatically

**If the build fails:**
- Read the error in the "Build" panel at the bottom
- Common fix: File → Sync Project with Gradle Files, then try again
- If it says "License not accepted": Tools → SDK Manager → SDK Tools → check "Android SDK Command-line Tools" → Apply

---

## Step 7: Use the App

1. The app will ask for **microphone permission** — tap **Allow**
2. It does a health check to your VM — you should see "Connected"
3. **Press and hold** the blue microphone button to speak
4. **Release** when you're done — it sends your audio to the VM
5. Wait 2-3 seconds — you'll see the transcript + reply, and hear the audio response

### The Two Modes

Toggle at the top of the screen:

- **Work Mode** — talks to Claude Sonnet on your VM. Can run scripts, check pipeline status, query the database, read files. Ask it anything you'd ask in the Claude Code terminal.

- **Strategy Mode** — talks to GPT-5.4 (OpenAI's frontier model, 1M context). For business strategy, brainstorming, market analysis. No VM access — pure conversation.

### Example Things to Say

**Work Mode:**
- "What's the pipeline status?"
- "How many active listings do we have in Robina?"
- "Check if there are any failed steps in the last run"
- "Read the latest fix history"
- "Run the coverage check"

**Strategy Mode:**
- "What's the best way to get our first paying customer?"
- "Help me think through pricing for pre-sale reports"
- "What should our Q2 marketing priorities be?"
- "How do other proptech startups acquire their first 1000 users?"

---

## Troubleshooting

### "Cannot reach server"
- Make sure you have internet on your phone
- Test in a browser: go to `https://vm.fieldsestate.com.au/api/health` — you should see JSON
- If the VM is down, SSH in and run: `sudo systemctl restart fields-voice-agent`

### Audio not playing
- Check your phone volume is up
- Make sure the phone isn't on silent/vibrate

### "Hold the button longer to record"
- You need to hold the button for at least half a second
- Press firmly and hold, speak, then release

### App crashes on launch
- In Android Studio: Run → Debug (the bug icon instead of play)
- Check the "Logcat" panel at the bottom for the crash stack trace

---

## Optional: Set an Auth Token

For security, you can require a token for all API calls:

1. On the VM, add a token to `.env`:
   ```
   VOICE_AGENT_TOKEN=pick-a-random-string-here
   ```
2. Restart the service: `sudo systemctl restart fields-voice-agent`
3. In the Android project, edit `app/build.gradle.kts`:
   ```kotlin
   buildConfigField("String", "API_TOKEN", "\"pick-a-random-string-here\"")
   ```
4. Rebuild the app

---

## Updating the App Later

If I make changes to the backend or app code:
- **Backend changes** are live immediately after `sudo systemctl restart fields-voice-agent`
- **App changes** require you to re-open in Android Studio and click ▶️ again
