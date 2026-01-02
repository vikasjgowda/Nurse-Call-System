#!/usr/bin/env python3
# FINAL_FCU.py
# This script serves as the main controller for the Flight Control Unit (FCU).
# It launches all necessary components (RCU polling, Master Server TCP client, and LED Display)
# as separate threads to ensure concurrent operation.
# ASSUMPTION: Network configuration (IP, Gateway, Port) is handled externally (e.g., by serial_script.py).

import threading
import time
import sys
import os
import subprocess
 
# Import your modules (These modules contain the main logic for each component)
import polling       # Module responsible for polling RCU status devices
import fcu_tcp       # Module responsible for communicating with the Master Server
import led       # Module responsible for the physical LED matrix display (FCU_GPIO.py logic)
 
# --- MAIN EXECUTION START ---
if __name__ == "__main__":
    print("\n=== FCU MASTER CONTROLLER (polling + TCP + Display) ===")
    
    # --- NETWORK CONFIGURATION REMOVED ---
    # The logic for applying network configuration is externalized to ensure
    # the system uses the configuration set by the serial configuration script.
    
    # Create a common shutdown event for all threads to monitor
    shutdown_event = threading.Event()
 
    # --- THREADS SETUP ---
    
    # Thread 1: polling RCUs and writing their consolidated status to Server.txt
    t_poll = threading.Thread(target=polling.run_rcu_polling_loop, args=(shutdown_event,), daemon=True)
 
    # Thread 2: FCU TCP client to read Server.txt and send data to the Master Server
    t_tcp = threading.Thread(target=fcu_tcp.run_fcu_client_loop, args=(shutdown_event,), daemon=True)
 
    # Thread 3: LED Matrix and Status Update
    # Starts the display and synchronization threads from the led module (FCU_GPIO.py)
    display_threads = led.run_display_threads()
 
    # --- START THREADS ---
    t_poll.start()
    t_tcp.start()
      
    print("[MAIN] All FCU components initialized.")
    print("[MAIN] System running. Press Ctrl + C to stop safely.\n")

    # --- MONITOR THREADS ---
    try:
        # Main loop keeps the program running until a shutdown signal is received
        while not shutdown_event.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        # Handles Ctrl+C signal for graceful termination
        print("\n[MAIN] Shutdown requested. Stopping all threads...")
        shutdown_event.set() # Set the event to signal all worker threads to stop
        
        # Give worker threads a moment to perform their internal cleanup (e.g., closing sockets, GPIO cleanup)
        time.sleep(1) 
        
        print("[MAIN] Cleanup complete. Exiting safely.")
        sys.exit(0)