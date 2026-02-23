# Permission Issue Diagnosis and Solution

**Last Updated: 30/01/2026, 9:20 PM (Thursday) - Brisbane**

## Problem Summary

The orchestrator is failing with:
```
[Errno 1] Operation not permitted: '/Users/projects/Documents/Fields_Orchestrator/config/process_commands.yaml'
```

## Root Cause Analysis

### ❌ NOT a Traditional Permission Issue

The error is **NOT** caused by:
- File permissions (file has correct `rw-r--r--` permissions)
- Extended attributes (`com.apple.provenance` is benign)
- Missing Full Disk Access for Python

### ✅ The ACTUAL Problem: Wrong Python Binary

**The launchd daemon is using a DIFFERENT Python than the one with Full Disk Access!**

1. **LaunchAgent Configuration** (`launchd/com.fields.orchestrator.plist`):
   ```xml
   <string>/usr/bin/python3</string>
   ```
   - This points to **Python 3.9.6** (system Python)

2. **Full Disk Access Granted To**:
   - **Python 3.6.9** at `/usr/bin/python3` (but this is likely a different binary)

3. **The Issue**:
   - macOS Full Disk Access is granted to **specific binary files** by their path
   - `/usr/bin/python3` (Python 3.9.6) does NOT have Full Disk Access
   - When launchd runs the orchestrator, it uses Python 3.9.6 which lacks permissions

## Why No macOS Popup?

You didn't get a macOS permission popup because:
- The system Python (`/usr/bin/python3`) is trying to access files in your **own Documents folder**
- macOS only shows popups for certain protected locations (Desktop, Documents, Downloads) when accessed by **apps**, not system utilities
- The error `[Errno 1] Operation not permitted` is a low-level POSIX error, not a macOS TCC (Transparency, Consent, and Control) denial

## Solution Options

### Option 1: Grant Full Disk Access to CommandLineTools Python (RECOMMENDED)

**IMPORTANT UPDATE**: The actual Python being used is at:
`/Library/Developer/CommandLineTools/usr/bin/python3`

This is the CommandLineTools Python, not the system Python!

1. **Grant Full Disk Access to the CORRECT Python**:
   - Open **System Settings** → **Privacy & Security** → **Full Disk Access**
   - Click the **+** button
   - Press **Cmd+Shift+G** and enter: `/Library/Developer/CommandLineTools/usr/bin/python3`
   - Select the file and click **Open**
   - Enable the checkbox next to Python

2. **Restart the launchd agent**:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.fields.orchestrator.plist
   launchctl load ~/Library/LaunchAgents/com.fields.orchestrator.plist
   ```

**Note**: `/usr/bin/python3` is actually a symlink or wrapper that points to the CommandLineTools Python.

### Option 2: Use Python 3.6.9 in LaunchAgent

If Python 3.6.9 already has Full Disk Access, update the plist to use it:

1. **Find Python 3.6.9 location**:
   ```bash
   which python3.6
   # or
   /usr/local/bin/python3.6 --version
   ```

2. **Update the plist** to use the correct Python path

3. **Reload the agent**

### Option 3: Use a Wrapper Script (MOST ROBUST)

Create a shell script that explicitly uses the Python with Full Disk Access:

1. **Create wrapper script** (`scripts/start_orchestrator_wrapper.sh`):
   ```bash
   #!/bin/bash
   # Use the Python that has Full Disk Access
   /path/to/python3.6 /Users/projects/Documents/Fields_Orchestrator/src/orchestrator_daemon.py
   ```

2. **Update plist** to call the wrapper script instead

## Verification Steps

After applying the fix:

1. **Check if Python can read the file**:
   ```bash
   /usr/bin/python3 -c "import yaml; print(yaml.safe_load(open('/Users/projects/Documents/Fields_Orchestrator/config/process_commands.yaml')))"
   ```

2. **Monitor the log**:
   ```bash
   tail -f /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log
   ```

3. **Check launchd status**:
   ```bash
   launchctl list | grep fields.orchestrator
   ```

## Additional Notes

### About Extended Attributes

The `@` symbol and `com.apple.provenance` attribute you see is:
- Added by macOS when files are created/modified by certain apps
- **NOT** a security restriction
- **NOT** related to this permission issue
- Can be safely ignored

### About macOS TCC (Transparency, Consent, and Control)

- Full Disk Access is part of macOS TCC system
- TCC permissions are granted to **specific binary files**
- If a binary is replaced or updated, permissions may need to be re-granted
- System Python updates can cause this issue

## Recommended Action

**Go with Option 1**: Grant Full Disk Access to `/usr/bin/python3` (Python 3.9.6) since that's what the launchd agent is configured to use.

This is the cleanest solution and ensures the orchestrator works with the system Python.
