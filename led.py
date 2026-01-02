import RPi.GPIO as GPIO
import time
import threading
import sys
import os
# --- CONFIGURATION ---
SERVER_STATUS_FILE = "Server.txt"             # File containing the consolidated status data polled from all RCUs
FCU_SERVER_STATUS_FILE = "fcu_server_status.txt" # File tracking the connection status to the Master Server
SERVER_STATUS_LED = 27                         # LED number used to indicate Master Server connection status
NUM_LEDS = 28                                  # Total number of individual LEDs in the display
NUM_RCUS = 24                                  # Total number of RCU devices being monitored
SYNC_FREQUENCY = 0.2                           # How often (in seconds) the status file is checked for updates
# --- 1. PIN SETUP ---
GPIO.setmode(GPIO.BOARD)                       # Set GPIO pin numbering mode to BOARD (physical pin numbers)
GPIO.setwarnings(False)                        # Disable GPIO warnings
J1 = [36, 32, 26, 24, 16, 12, 22, 18]          # List of physical pin numbers (J1 pins)
J2 = [38, 40, 37, 35, 33, 31, 29, 23]          # List of physical pin numbers (J2 pins)
# Configure all specified pins as outputs and ensure they are initially LOW (off)
for pin in J1 + J2:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)
# --- 2. LED MAPPING (NEW) ---
# Maps each LED number (1-28) to the triplet of GPIO pins controlling it: (Column Pin, Green Row Pin, Red Row Pin)
LED_MAP = {
    1: (38, 36, 32),
    2: (38, 26, 24),
    3: (38, 22, 18),
    4: (40, 36, 32),
    5: (40, 26, 24),
    6: (40, 22, 18),
    7: (37, 36, 32),
    8: (37, 26, 24),
    9: (37, 22, 18),
    11: (33, 36, 32),
    10: (35, 36, 32),
    25: (33, 22, 18),
    26: (33, 26, 24),
    14: (40, 12, 16),
    15: (23, 26, 24),
    16: (23, 22, 18),
    17: (38, 12, 16),
    18: (29, 26, 24),
    19: (29, 22, 18),
    20: (23, 36, 32),
    21: (31, 26, 24),
    22: (31, 22, 18),
    23: (29, 36, 32),
    24: (31, 36, 32),
    12: (35, 22, 18),
    13: (35, 26, 24),
    27: (37, 12, 16),
    28: (35, 12, 16),
}
# --- 3. STATE VARIABLES ---
led_states = {}  # Dictionary storing the current desired state ('RED', 'GREEN', or 'OFF') for each LED
running = True   # Flag to control the main execution loop of the threads
# --- 4. DISPLAY FUNCTION (NEW "BOTH HIGH" LOGIC) ---
def display_loop():
    """Continuously executes the LED multiplexing routine to display all current states."""
    global running
    while running:
        # Loop through every defined LED in the map
        for led, (col_pin, green_row, red_row) in LED_MAP.items():
            # Retrieves the target state for the current LED
            state = led_states.get(led, "RED")
            
            # Logic to set pins based on the desired LED color state
            if state == "GREEN":
                # Activate the GREEN connection path
                GPIO.output(col_pin, GPIO.HIGH)
                GPIO.output(green_row, GPIO.HIGH)
                GPIO.output(red_row, GPIO.LOW)
            elif state == "RED":
                # Activate the RED connection path
                GPIO.output(col_pin, GPIO.HIGH)
                GPIO.output(red_row, GPIO.HIGH)
                GPIO.output(green_row, GPIO.LOW)
            elif state == "OFF":
                # OFF state is managed by the cleanup step below
                pass 
                
            # Short pulse to light the LED briefly
            time.sleep(0.0007)
            
            # Turn OFF ALL pins related to this LED to prevent ghosting effects
            GPIO.output(col_pin, GPIO.LOW)
            GPIO.output(green_row, GPIO.LOW)
            GPIO.output(red_row, GPIO.LOW)
            
        # Small delay after cycling through all LEDs in the map
        time.sleep(0.002)
        
# --- 5. STATUS SYNCHRONIZATION THREAD (UNCHANGED) ---
def sync_status_loop():
    """Reads the consolidated status files and updates the global LED state dictionary."""
    global led_states
    global running
    while running:
        new_states = {}
        
        # --- Check FCU master connection status (LED 27) ---
        try:
            # Reads the local file updated by the FCU_TCP client
            if os.path.exists(FCU_SERVER_STATUS_FILE):
                with open(FCU_SERVER_STATUS_FILE, "r") as f:
                    status = f.read().strip()
                # Sets LED 27 state based on ACTIVE/INACTIVE status
                if status == "ACTIVE":
                    new_states[SERVER_STATUS_LED] = "GREEN"
                else:
                    new_states[SERVER_STATUS_LED] = "RED"
        except Exception as e:
            print(f"[ERROR] FCU status read: {e}")
            
        # --- Check RCU call statuses (LEDs 1-24, 28) ---
        try:
            # Reads the consolidated status file updated by the RCU polling client
            if not os.path.exists(SERVER_STATUS_FILE):
                print(f"[ERROR] Status file {SERVER_STATUS_FILE} not found.")
                time.sleep(1)
                continue
                
            with open(SERVER_STATUS_FILE, "r") as f:
                consolidated_status = f.read().strip()
                
            # Validates the length of the consolidated status string
            if not consolidated_status or len(consolidated_status) < NUM_RCUS * 2:
                print("[WARNING] Consolidated status incomplete.")
                time.sleep(0.5)
                continue
                
            # Iterates through the hex status pairs for each RCU
            for rcu_index in range(NUM_RCUS):
                start = rcu_index * 2
                rcu_status_hex = consolidated_status[start:start + 2]
                led_num = rcu_index + 1
                
                # --- Apply the specific status interpretation logic ---
                if rcu_status_hex == "A0":
                    new_states[led_num] = "RED"      # Inactive RCU / No connection
                elif rcu_status_hex == "E0":
                    new_states[led_num] = "OFF"      # RCU Active, but no call status is set
                else:
                    new_states[led_num] = "GREEN"    # RCU Active with an active call status
                    
            # Update the global LED states for the display loop to use
            led_states = new_states
            
        except Exception as e:
            print(f"[ERROR] During status sync: {e}")
            
        # Wait for the defined synchronization frequency before checking again
        time.sleep(SYNC_FREQUENCY)
        
# --- 6. WRAPPER FUNCTION (UNCHANGED) ---
def run_display_threads():
    """Initializes and starts the display multiplexing and status sync threads."""
    global running
    running = True
    # Create the display thread (controls the physical GPIO outputs)
    display_thread = threading.Thread(target=display_loop, daemon=True)
    # Create the sync thread (reads files and updates state)
    sync_thread = threading.Thread(target=sync_status_loop, daemon=True)
    
    display_thread.start()
    sync_thread.start()
    
    return (display_thread, sync_thread)
    
# --- 7. MAIN (UNCHANGED) ---
if __name__ == '__main__':
    """Main execution block for standalone running."""
    try:
        # Start the two worker threads
        run_display_threads()
        # Keep the main thread alive until interrupted
        while running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful shutdown sequence
        running = False
        time.sleep(0.01)
        GPIO.cleanup()
        print("\nGPIO cleaned up. Program exited.")