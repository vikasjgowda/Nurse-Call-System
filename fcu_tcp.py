#!/usr/bin/env python3
# FCU_TCP.py
# Implements a highly resilient FCU client that dynamically loads configuration
# (Master Server target IP from GATEWAY, Port from PORT) on every loop iteration
# to survive external network changes and use the correct server address.

import socket
import time
import os
import sys
import threading

# ==============================================
# CONFIGURATION LOADER (Dynamically called in the loop)
# ==============================================
FCU_CONFIG_FILE = "fcu.txt"

def load_config(device_type):
    """
    Loads configuration settings from the device-specific text file dynamically.
    Used to retrieve the current Master Server IP and Port on every loop iteration.
    """
    filename = f"{device_type.lower()}.txt"
    config = {}
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    # Parses key=value pairs from the configuration file
                    key, value = line.strip().split("=", 1)
                    config[key] = value
    return config

# ==============================================
# RCU PREFIX (Used for sending reset commands to individual RCUs)
# ==============================================
# This is where the FCU sends commands *down* to individual RCUs after receiving a directive from the Master Server.
RCU_IP_PREFIX = "172.15.11."  # Assumed static IP prefix for all RCU devices
RCU_PORT = 1600  # Fixed port for RCU reset commands

# ==============================================
# HEX MARKERS AND STATUS FILES
# ==============================================
SERVER_STATUS_FILE = "Server.txt"             # File containing the consolidated status data polled from all RCUs
FCU_SERVER_STATUS_FILE = "fcu_server_status.txt" # File used to track the FCU's connection status to the Master Server
REQ_DATA = "5245513A323001"                   # Hex header for the data packet (part of the protocol)
END_OF_DATA = "808002"                        # Hex trailer for the data packet (part of the protocol)

def update_server_status(status):
    """Writes the current connection status ('ACTIVE' or 'INACTIVE') to a local file."""
    try:
        with open(FCU_SERVER_STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(status)
    except Exception:
        # Silently fails if file writing is not possible
        pass

# ==============================================
# SEND RESET COMMAND TO RCU
# ==============================================
def send_raw_packet_to_rcu(room_id, raw_bytes):
    rcu_ip = f"{RCU_IP_PREFIX}{room_id}"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((rcu_ip, RCU_PORT))
            s.sendall(raw_bytes)
            print(f"[FCU] RAW packet forwarded to RCU {room_id}.")
    except Exception as e:
        print(f"[FCU] Failed to send RAW packet to RCU {room_id}: {e}")


# ==============================================
# SEND DATA TO MASTER SERVER (The Gateway)
# ==============================================
def send_to_server(fcu_config):
    """
    Reads the consolidated status data, formats it into a protocol packet,
    sends it to the Master Server, and processes any reset directives received in response.
    """
    # CRITICAL MAPPING: Get Master Server IP from GATEWAY field in fcu.txt
    MASTER_SERVER_IP = fcu_config.get("GATEWAY")

    # CRITICAL MAPPING: Get Master Server Port from PORT field in fcu.txt
    try:
        MASTER_SERVER_PORT = int(fcu_config.get("PORT", 1500))
    except (ValueError, TypeError):
        MASTER_SERVER_PORT = 1500

    if not MASTER_SERVER_IP:
        # Exits if the Master Server IP (Gateway) is not configured
        return

    update_server_status("INACTIVE") # Assume inactive until connection is proven

    # Requires the RCU polling data file to proceed
    if not os.path.exists(SERVER_STATUS_FILE):
        return

    try:
        # Read the consolidated hex status string from the RCU polling client file
        with open(SERVER_STATUS_FILE, "r", encoding="utf-8") as f:
            hex_string = f.read().strip()

        if not hex_string:
            return

        # Constructs the full hex packet: Header + Status Data + Trailer
        full_hex = REQ_DATA + hex_string + END_OF_DATA
        packet = bytearray.fromhex(full_hex)
        print(f"[FCU] Attempting connect to Master Server: {MASTER_SERVER_IP}:{MASTER_SERVER_PORT}")

        # Connect and send data to the Master Server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            # Connection uses the Master Server's IP/Port from the dynamically loaded config
            s.connect((MASTER_SERVER_IP, MASTER_SERVER_PORT))

            update_server_status("ACTIVE") # Connection successful

            # Send the status packet
            s.sendall(packet)

            # Receive the response packet
            response = s.recv(1024)
            raw_server_packet = response  # store original bytes

            if not response:
                update_server_status("INACTIVE")
                return

            update_server_status("ACTIVE")

            received_hex = response.hex().upper()

            # --- Response Parsing Logic (Checks for ACK and extracts reset directive) ---

            # Check for the ACK protocol header
            # --- Handle ACK:25 RESET PACKET (same logic as RCU side) ---
            if response.startswith(b"ACK:25"):

                full_hex = response.hex().upper()

                prefix = "41434B3A3235018"
                if full_hex.startswith(prefix):
                    stripped = full_hex[len(prefix):]
                else:
                    stripped = full_hex

                idx = None
                for i, ch in enumerate(stripped):
                    if ch in "ABCDEF":
                        idx = i
                        break

                if idx is not None and idx + 1 < len(stripped):
                                call_type = stripped[idx:idx+2]

                print(f"[FCU] Received reset code HEX payload: {stripped}")
                print(f"[FCU] Extracted Reset Code: {call_type}")

                # Map reset codes to commands
                reset_map = {
                    "E1": "RES:E1",
                    "E2": "RES:E2",
                    "E4": "RES:E4",
                    "E8": "RES:E8",
                    "F0": "RES:F0"
                }

                if call_type not in reset_map:
                    return

                # ROOM logic: first part before the code (hex room number)
                room_hex = stripped[:idx]

                if not room_hex:
                    return

                try:
                    room_id = int(room_hex, 16)
                except:
                    return

                print(f"[FCU] Master Server requests reset for Room {room_id}")
                send_raw_packet_to_rcu(room_id, raw_server_packet)

                return


    # Aggressively catch all network errors (socket errors, timeouts, etc.)
    except Exception as e:
        update_server_status("INACTIVE")
        # This error is expected during the serial script's IP change
        print(f"[FCU] CRITICAL CONNECTION ERROR: {e}. Network likely down/unstable. Retrying...")


# ==============================================
# MAIN LOOP
# ==============================================
def run_fcu_client_loop(shutdown_event):
    """Runs the main client loop for sending data and ensures dynamic configuration loading."""
    print("[FCU] Client running...")

    while not shutdown_event.is_set():
        # Load configuration on every iteration (dynamically picks up new Master Server IP/Port)
        current_config = load_config("FCU")

        try:
            # Executes the network communication logic
            send_to_server(current_config)
        except Exception as e:
            # Catches unexpected internal errors
            print(f"[FCU] Unhandled loop error: {e}. Waiting 5s.")
            time.sleep(5)

        time.sleep(1) # Poll interval before the next transmission attempt

    print("[FCU] Client thread shutting down gracefully.")


# ==============================================
# ENTRYPOINT
# ==============================================
if __name__ == "__main__":
    try:
        # NOTE: When run standalone, we need a dummy shutdown event to control the loop
        dummy_event = threading.Event()
        run_fcu_client_loop(dummy_event)
    except KeyboardInterrupt:
        print("Stopping FCU client...")