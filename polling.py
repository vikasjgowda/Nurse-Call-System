import socket
import time
import os
import subprocess  # This import is not used in the provided code, but it's present in the original.
# --- CONFIGURATION LOADING ---
def load_config(device_type):
    """
    Function to load configuration from file.
    This function reads a configuration file (e.g., 'rcu.txt') to get
    settings like IP, port, and other parameters needed for the client.
    """
    filename = f"{device_type.lower()}.txt"
    config = {}
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                try:
                    # Parses key=value lines to extract configuration data.
                    key, value = line.strip().split("=", 1)
                    config[key] = value
                except ValueError:
                    # Skips lines that don't conform to the 'key=value' format.
                    continue
    return config

def run_rcu_polling_loop(shutdown_event=None):
    """
    Main function to run the RCU polling loop (acting as the FCU client).
    It continuously polls a defined range of RCU servers for their status.
    """
    # --- INITIAL SETUP ---
    # Load network configuration settings
    rcu_config = load_config("RCU")
    
    # Determines the common IP prefix for all RCU devices based on the configured RCU IP
    if "IP" in rcu_config:
        ip_parts = rcu_config["IP"].split('.')
        RCU_IP_PREFIX = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}."
    else:
        RCU_IP_PREFIX = "172.15.11."
        
    # Determines the target port for polling RCU servers
    RCU_PORT = int(rcu_config.get("RCU_PORT", 1600))
    
    POLL_REQUEST = "ACK:20" # The command sent to RCUs to request status
    NUM_RCUS = 24 # The total number of RCU devices to poll
    SERVER_STATUS_FILE = "Server.txt" # File to store the consolidated status of all RCUs
    rcu_responses = [] # List to accumulate the status responses
    
    # --- POLLING FUNCTION ---
    def poll_rcu(ip, port, timeout=0.2):
        """
        Connects to a single RCU server via TCP, sends a poll request, 
        and processes the hexadecimal status response.
        """
        try:
            # Set up the TCP socket connection
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((ip, port))
                print(f"INSIDE... Connected to {ip}")
                
                # Send the poll request command
                s.sendall(POLL_REQUEST.encode('utf-8'))
                
                # Receive the response data
                response_bytes = s.recv(1024)
                
                if response_bytes:
                    hex_response = response_bytes.hex().upper()
                    print(f"Print Received HEX Data : {hex_response}")
                    
                    # Validates the response format
                    if len(hex_response) >= 4 and hex_response.endswith("02"):
                        # Extracts the status byte (second to last byte)
                        hex_status_byte = hex_response[-4:-2]
                        try:
                            # Converts the status byte to its original binary string
                            original_binary_str = format(int(hex_status_byte, 16), '08b')
                        except ValueError:
                            print(f"  ? Invalid hex status byte '{hex_status_byte}' received from {ip}.")
                            return 'A0' # Return error code
                        
                        # Logic to adjust the binary status for internal use (setting top 3 bits to '111')
                        adjusted_binary_str = "111" + original_binary_str[3:]
                        integer_from_binary = int(adjusted_binary_str, 2)
                        
                        # Returns the final processed status as a two-digit hex string
                        final_hex_value = format(integer_from_binary, '02X')
                        return final_hex_value
                    else:
                        print(f"  ? Invalid/short response from {ip}: {hex_response}")
                        return 'A0' # Return error code
                        
                print(f"No data received from {ip}. Assuming inactive.")
                return 'A0' # Return inactive code if no data is received
                
        # Handle connection errors, timeouts, or invalid data conversion
        except (socket.error, socket.timeout, ValueError) as e:
            print(f"Not Successful to {ip}:{port}. Assuming inactive.")
            return 'A0' # Return inactive code upon failure
            
    # --- MAIN LOOP ---
    print("Polling Client is running...")
    
    while True:
        # Check for external shutdown signal (when running as a thread)
        if shutdown_event and shutdown_event.is_set():
            print("[RCU] Shutdown signal received. Exiting polling loop.")
            break
            
        rcu_responses.clear()
        
        # Iterate and poll every RCU device (1 up to NUM_RCUS)
        for i in range(1, NUM_RCUS + 1):
            # Construct the target IP address
            ip = f"{RCU_IP_PREFIX}{i}"
            print(f"Polling {ip}")
            
            # Poll the specific RCU
            hex_status = poll_rcu(ip, RCU_PORT)
            rcu_responses.append(hex_status)
            print(f"Counter.... {i}")
            
        # Concatenate all 24 individual hex statuses into one long status string
        consolidated_status = "".join(rcu_responses)
        print(f"Total....{consolidated_status}")
        
        # Write the consolidated status to the server status file
        try:
            with open(SERVER_STATUS_FILE, "w") as f:
                f.write(consolidated_status)
            print(f"Status saved to {SERVER_STATUS_FILE}")
        except Exception as e:
            print(f"Error writing to file: {e}")
            
        # Pause before the next polling cycle
        time.sleep(1)

# --- RUN DIRECTLY (for standalone test) ---
# Allows the script to be executed independently for testing purposes
if __name__ == "__main__":
    run_rcu_polling_loop()