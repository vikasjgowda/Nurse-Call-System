import RPi.GPIO as GPIO
import time
import os
import threading  # used for standalone test mode and graceful shutdown

def run_gpio_system(shutdown_event):
    """
    Main function to initialize and run the entire GPIO nurse call system.
    This runs in a separate thread when integrated with a main application.
    """         
    print("[GPIO] Thread started.", flush=True)
    STATE_FILE = 'status_state.txt' # File used for persistent storage of the system's call state
    
    # --- GPIO SETUP ---
    try:
        # Set the GPIO pin numbering mode to BCM (Broadcom chip-specific numbering)
        GPIO.setmode(GPIO.BCM)
        # Suppress warnings that might appear when running the script multiple times
        GPIO.setwarnings(False)
    except Exception as e:
        # Handle fatal error if GPIO mode cannot be set (e.g., not on a Pi)
        print(f"[GPIO] FATAL: Error setting up GPIO mode: {e}", flush=True)
        return  # Exit the thread immediately
        
    print("[GPIO] GPIO mode set to BCM.", flush=True)
    
    # --- PIN DEFINITIONS ---
    # Dictionary mapping functional names to their BCM pin numbers for all input buttons
    button_pins = {
        'r1_nurse_call': 17, 'r1_att_call': 27,
        'r2_nurse_call': 22, 'r2_att_call': 5,
        'emergency_call': 25,
        'r1_nurse_reset': 6, 'r1_att_reset': 26,
        'r2_nurse_reset': 23, 'r2_att_reset': 24,
        'emergency_reset': 8,
    }
    # Dictionary mapping functional names to their BCM pin numbers for all output LEDs
    led_pins = {
        'green_led': 7, 'red_led': 1,
        'n1_led': 13, 'a1_led': 12,
        'emergency_led': 18, 'n2_led': 4,
        'a2_led': 16
    }
    
    # Configure pins
    # Set up all button pins as inputs with a pull-down resistor
    for pin in button_pins.values():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    
    # Set up all LED pins as outputs and ensure they start in the OFF (LOW) state
    for pin in led_pins.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        
    print("[GPIO] All pins configured.", flush=True)
    
    # --- SYSTEM STATE CONFIGURATION ---
    # Defines the bit position within the 8-bit 'status' variable for each call type
    call_bits = {
        'r1_nurse_call': 0, 'r1_att_call': 1,
        'r2_nurse_call': 2, 'r2_att_call': 3,
        'emergency_call': 4,
    }
    
    # Maps call types to their specific room/attendant LED pin numbers
    call_to_led_map = {
        'r1_nurse_call': led_pins['n1_led'],
        'r1_att_call': led_pins['a1_led'],
        'r2_nurse_call': led_pins['n2_led'],
        'r2_att_call': led_pins['a2_led'],
        'emergency_call': led_pins['emergency_led'],
    }
    
    # Tracks the latched state (True/False) of each call, independent of the status integer
    latched = {key: False for key in call_bits.keys()}
    
    # --- FUNCTIONS ---
    
    def save_status():
        """Writes the current integer status (as an 8-bit binary string) to the state file."""
        nonlocal status
        with open(STATE_FILE, 'w') as f:
            f.write(format(status, '08b'))
            
    def load_status():
        """
        Reads the status from the state file and converts it to an integer. 
        Returns a default status if the file is missing or invalid.
        """
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                bin_str = f.read().strip()
                # Ensure the loaded string is exactly 8 bits long
                if len(bin_str) == 8:
                    print(f"[GPIO] Loaded saved status: {bin_str}", flush=True)
                    return int(bin_str, 2)
        # Default status value when no valid file is found (0b11100000)
        print("[GPIO] No state file found, using default.", flush=True)
        return 0b11100000 
        
    def restore_leds():
        """
        Initializes the LED outputs based on the status loaded from the file.
        Used primarily upon system startup.
        """
        nonlocal status
        for name, bit in call_bits.items():
            # Check if the corresponding bit is set in the status integer
            if status & (1 << bit):
                latched[name] = True
                turn_on_led(name)
                
    def turn_on_led(name):
        """Sets the appropriate call/room LED HIGH, and controls master LEDs (red/green)."""
        # Set the call button's input pin HIGH temporarily (functionality seems unusual here)
        if name in call_bits:
            pin_number = button_pins[name]
            GPIO.setup(pin_number, GPIO.OUT)
            GPIO.output(pin_number, GPIO.HIGH)
        
        if name == 'emergency_call':
            # Activate master red LED and the emergency LED
            GPIO.output(led_pins['red_led'], GPIO.HIGH)
            GPIO.output(led_pins['emergency_led'], GPIO.HIGH)
        else:
            # Activate the specific room/attendant LED and the master green LED
            GPIO.output(call_to_led_map[name], GPIO.HIGH)
            GPIO.output(led_pins['green_led'], GPIO.HIGH)
            
    def turn_off_led(name):
        """Sets the appropriate call/room LED LOW, and resets the input pin to PUD_DOWN."""
        # Reset the call button pin back to input PUD_DOWN state
        if name in call_bits:
            pin_number = button_pins[name]
            GPIO.output(pin_number, GPIO.LOW)
            time.sleep(0.05)
            # Reconfigure the pin as an input with pull-down
            GPIO.setup(pin_number, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            # Update the button state cache
            button_state[name] = GPIO.input(pin_number) == GPIO.LOW
            
        if name == 'emergency_call':
            # Deactivate master red LED and emergency LED
            GPIO.output(led_pins['red_led'], GPIO.LOW)
            GPIO.output(led_pins['emergency_led'], GPIO.LOW)
        else:
            # Deactivate the specific room/attendant LED
            GPIO.output(call_to_led_map[name], GPIO.LOW)
            
    def check_clear():
        """Checks if all non-emergency calls are cleared and turns off the master green LED if so."""
        nurse_att_calls = ['r1_nurse_call', 'r1_att_call', 'r2_nurse_call', 'r2_att_call']
        # Check if *any* of these calls are currently latched
        if not any(latched[call] for call in nurse_att_calls):
            # If no calls are latched, turn off the green master LED
            GPIO.output(led_pins['green_led'], GPIO.LOW)
            
    def handle_press(name):
        """
        Processes a button press event (call or reset).
        Updates the latched state, status integer, LED, and saves the status.
        """
        nonlocal status
        if name in call_bits:
            # Handle Call Button Press (Latch)
            if not latched[name]:
                latched[name] = True
                status |= (1 << call_bits[name]) # Set the corresponding status bit
                turn_on_led(name)
        elif name.endswith('_reset'):
            # Handle Reset Button Press (Clear)
            call_name = name.replace('_reset', '_call')
            if latched.get(call_name, False):
                status &= ~(1 << call_bits[call_name]) # Clear the corresponding status bit
                latched[call_name] = False
                turn_off_led(call_name)
                check_clear() # Check if master green LED needs to be turned off
                
        # The status line below ensures the top three bits (0b11100000) are always set.
        status |= 0b11100000 
        save_status()
        print(f"[GPIO] {name} processed. Status: {format(status, '08b')}", flush=True)
        
    def sync_with_file():
        """
        Periodically checks the status file for external changes (e.g., from an API/Web app)
        and updates the internal state and physical LEDs accordingly.
        """
        nonlocal status
        file_status_str = None
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    file_status_str = f.read().strip()
                    if len(file_status_str) == 8:
                        file_status = int(file_status_str, 2)
                        
                        # Check if the status read from the file differs from the internal status
                        if file_status != status:
                            print("[GPIO] Status change detected. Syncing.", flush=True)
                            changed_bits = status ^ file_status # XOR to find changed bits
                            status = file_status # Update internal status to match the file
                            
                            # Iterate through all call bits to update state/LEDs based on changes
                            for name, bit in call_bits.items():
                                if changed_bits & (1 << bit):
                                    if status & (1 << bit):
                                        # Bit changed from 0 to 1 (Call triggered)
                                        latched[name] = True
                                        turn_on_led(name)
                                    else:
                                        # Bit changed from 1 to 0 (Call reset)
                                        latched[name] = False
                                        turn_off_led(name)
                            check_clear() # Update master green LED state
                            
        except Exception as e:
            print(f"[GPIO] Error during file sync: {e}", flush=True)
            
    # --- MAIN PROGRAM EXECUTION ---
    
    # Load the persistent status from the file
    status = load_status()
    
    # Restore the physical LED state to match the loaded status
    restore_leds()
    
    # Save the status again (useful if default status was loaded)
    save_status()
    
    # Initial read and cache of all button states (True=Pressed, False=Not Pressed)
    button_state = {
        name: GPIO.input(pin) == GPIO.LOW
        for name, pin in button_pins.items()
    }
    
    print("[GPIO] Nurse call system running....", flush=True)
    
    # Main polling loop. Continues until the shutdown event is set.
    while not shutdown_event.is_set():
        
        # 1. Input Polling (Edge detection via polling)
        for name, pin in button_pins.items():
            # Read current physical state
            pressed = GPIO.input(pin) == GPIO.LOW
            
            # Check for rising edge (pressed now, but wasn't pressed last time)
            if pressed and not button_state[name]:
                button_state[name] = True # Update cache
                handle_press(name) # Process the event
            
            # Check for falling edge (not pressed now, but was pressed last time)
            elif not pressed and button_state[name]:
                button_state[name] = False # Update cache (debounce handled implicitly by polling speed)
                
        # 2. State Synchronization
        # Check the status file for external updates
        sync_with_file()
        
        # 3. Controlled Sleep (Allows quick exit upon shutdown event)
        # Sleep for a short duration, checking the shutdown event multiple times
        for _ in range(5):
            if shutdown_event.is_set():
                break
            time.sleep(0.01) # Total sleep time ~50ms
            
    # Cleanup and exit message when loop breaks
    print("\n[GPIO] Shutdown signal received. Exiting thread.", flush=True)

# --- Standalone Mode ---
# Code block to allow the script to be run independently for testing
if __name__ == "__main__":
    print("[GPIO] Standalone mode started. Press Ctrl+C to exit.")
    shutdown_event = threading.Event()
    try:
        # Run the main system function
        run_gpio_system(shutdown_event)
    except KeyboardInterrupt:
        print("\n[GPIO] Ctrl+C detected. Shutting down...")
        shutdown_event.set() # Signal the running thread to stop
        time.sleep(0.5) # Wait briefly for the thread to exit gracefully
        GPIO.cleanup() # Reset all GPIO pin configurations
        print("[GPIO] Clean exit complete.")