#!/usr/bin/env python3
# final_rcu.py
# Runs GPIO + TCP listener. Network configuration is assumed to be handled externally (e.g., by serial_script.py).

import threading
import subprocess
import signal
import sys
import time
import os # Added os import for cleaner execution if needed, though not strictly required
import GPIO_Ports # Placeholder for GPIO module

shutdown_event = threading.Event()

def start_gpio():
    """Starts the GPIO control system in a thread."""
    print("[GPIO] Starting GPIO thread...")
    # NOTE: This assumes GPIO_Ports.py is defined and contains run_gpio_system
    # GPIO_Ports.run_gpio_system(shutdown_event)
    # Placeholder loop while GPIO_Ports is unavailable
    try:
        if 'GPIO_Ports' in globals() and hasattr(GPIO_Ports, 'run_gpio_system'):
            GPIO_Ports.run_gpio_system(shutdown_event)
        else:
             print("[GPIO] Placeholder running: GPIO module/function not available.")
             while not shutdown_event.is_set():
                 time.sleep(10)
    except Exception as e:
        print(f"[GPIO] Error in GPIO thread: {e}")

def start_tcp():
    """
    Start the TCP listener in a separate process.
    The TCP listener (RCU_TCP.py) now runs unconditionally, relying on the live
    IP address configured by the system.
    """
    cmd = ["python3", "RCU_TCP.py"]

    print("[TCP] Starting RCU TCP listener process...")
    # Using Popen allows the parent script to continue running
    try:
        subprocess.Popen(cmd, close_fds=True)
    except Exception as e:
        print(f"[TCP] Failed to start RCU_TCP.py subprocess: {e}")

def handle_exit(sig, frame):
    """Gracefully handles Ctrl+C shutdown."""
    print("\n[MAIN] Ctrl+C detected. Stopping...")
    # Signal the GPIO thread to stop gracefully
    shutdown_event.set()
    # Give components a moment to close connections/threads
    time.sleep(0.5)
    # The TCP process started with Popen will typically be killed on parent exit
    sys.exit(0)

# Set up signal handler for clean exit
signal.signal(signal.SIGINT, handle_exit)

if __name__ == "__main__":
    print("[MAIN] Starting RCU System (GPIO + TCP)...")

    # --- Network check logic removed ---

    # Start GPIO thread (Control/Polling logic)
    t_gpio = threading.Thread(target=start_gpio, daemon=True)
    t_gpio.start()

    # Start TCP listener (Network communication)
    start_tcp()

    print("[MAIN] RCU System initialized and running. Press Ctrl+C to stop.\n")

    # Keep the main thread alive indefinitely until shutdown_event is set
    try:
        while not shutdown_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        # Should be caught by handle_exit, but safe to include this.
        handle_exit(None, None)