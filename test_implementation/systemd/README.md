# Systemd Service Installation Guide

## Quick Installation

**On the Raspberry Pi (server):**

```bash
# 1. Copy service files to systemd directory
sudo cp systemd/remote-audio.service /etc/systemd/system/
sudo cp systemd/jacktrip.service /etc/systemd/system/

# 2. Edit remote-audio.service to match your setup
sudo nano /etc/systemd/system/remote-audio.service
# Change these lines if needed:
#   User=tomas                    # Your username
#   ExecStart=... -d hw:3,0 ...   # Your QMX+ card number (from aplay -l)

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Enable services (auto-start at boot)
sudo systemctl enable remote-audio.service

# 5. Start services now
sudo systemctl start remote-audio.service

# 6. Verify they're running
sudo systemctl status remote-audio.service
sudo systemctl status jacktrip.service
```

## Service Control Commands

```bash
# Start
sudo systemctl start remote-audio.service

# Stop
sudo systemctl stop remote-audio.service

# Restart
sudo systemctl restart remote-audio.service

# Check status
sudo systemctl status remote-audio.service
sudo systemctl status jacktrip.service

# View logs
journalctl -u remote-audio.service -f
journalctl -u jacktrip.service -f

# Disable auto-start
sudo systemctl disable remote-audio.service

# Enable auto-start
sudo systemctl enable remote-audio.service
```

## What This Does

✅ **Auto-starts at boot** - Services start automatically when Pi boots  
✅ **Auto-restarts on crash** - If JACK or JackTrip crash, systemd restarts them  
✅ **Proper dependencies** - JackTrip waits for JACK to be ready  
✅ **Clean shutdown** - Proper cleanup when stopping  
✅ **System logs** - All output goes to systemd journal  
✅ **Manual control** - Easy start/stop/restart commands  

## Monitoring

**Watch logs in real-time:**
```bash
journalctl -u remote-audio.service -u jacktrip.service -f
```

**Check for errors:**
```bash
journalctl -u remote-audio.service --since "1 hour ago" | grep -i error
```

**See restart history:**
```bash
systemctl status remote-audio.service | grep -i restart
```

## Troubleshooting

**Service fails to start:**
```bash
# Check why it failed
sudo systemctl status remote-audio.service
journalctl -u remote-audio.service -n 50

# Common issues:
# 1. Wrong audio device (hw:3,0)
#    Fix: Edit service file with correct device from: aplay -l
sudo nano /etc/systemd/system/remote-audio.service
sudo systemctl daemon-reload
sudo systemctl restart remote-audio.service

# 2. User doesn't exist or wrong permissions
#    Fix: Change User= line to your username
#    Add user to audio group: sudo usermod -a -G audio tomas

# 3. JACK/JackTrip not installed in /usr/bin
#    Check paths: which jackd; which jacktrip
#    Update ExecStart= paths in service file
```

**Service keeps restarting:**
```bash
# Watch what's happening
journalctl -u remote-audio.service -f

# If JACK fails due to device busy:
# Check what's using the audio device
fuser -v /dev/snd/*

# Kill the process
sudo fuser -k /dev/snd/pcmC3D0c

# Restart service
sudo systemctl restart remote-audio.service
```

**Disable auto-start temporarily:**
```bash
# Stop and disable
sudo systemctl stop remote-audio.service
sudo systemctl disable remote-audio.service

# Run manually when needed
~/remote-audio-server.sh
```

## Configuration Changes

**After editing service files:**
```bash
# 1. Reload systemd configuration
sudo systemctl daemon-reload

# 2. Restart services
sudo systemctl restart remote-audio.service

# 3. Verify changes
sudo systemctl status remote-audio.service
```

## Checking if Services are Running

```bash
# Quick check
sudo systemctl is-active remote-audio.service
sudo systemctl is-active jacktrip.service

# Both should show: active

# Detailed status
sudo systemctl status remote-audio.service
```

## Uninstallation

```bash
# Stop and disable services
sudo systemctl stop remote-audio.service
sudo systemctl disable remote-audio.service

# Remove service files
sudo rm /etc/systemd/system/remote-audio.service
sudo rm /etc/systemd/system/jacktrip.service

# Reload systemd
sudo systemctl daemon-reload
```

## Why This is Better Than Manual Start

| Manual Start | Systemd Service |
|-------------|----------------|
| ❌ Must SSH and run commands after reboot | ✅ Starts automatically at boot |
| ❌ If crash, stays down | ✅ Auto-restarts on failure |
| ❌ Terminal must stay open | ✅ Runs in background |
| ❌ No logs | ✅ Full logging via journalctl |
| ❌ Complex startup order | ✅ Proper dependency management |
| ❌ Hard to monitor | ✅ systemctl status shows everything |

## Advanced: Email Notifications on Failure

**Optional: Get notified when service fails:**

```bash
# Install mail utilities
sudo apt install mailutils

# Create notification script
sudo nano /usr/local/bin/notify-audio-failure.sh
```

Add:
```bash
#!/bin/bash
echo "Remote audio service failed at $(date)" | mail -s "Audio Server Alert" your@email.com
```

Make executable:
```bash
sudo chmod +x /usr/local/bin/notify-audio-failure.sh
```

Edit service file:
```bash
sudo nano /etc/systemd/system/remote-audio.service
```

Add under [Service]:
```ini
OnFailure=notify-audio-failure.service
```

Create notification service:
```bash
sudo nano /etc/systemd/system/notify-audio-failure.service
```

```ini
[Unit]
Description=Send notification on audio service failure

[Service]
Type=oneshot
ExecStart=/usr/local/bin/notify-audio-failure.sh
```

Reload:
```bash
sudo systemctl daemon-reload
```

Now you'll get email when the service fails!

## Summary

**You ARE running real JACK on Raspberry Pi!** The systemd services just make it:
- Auto-start reliably
- Auto-restart on crashes
- Easy to control
- Properly logged

This is the **professional way** to run services on Linux. Much better than manual terminal commands that stop when you disconnect SSH!
