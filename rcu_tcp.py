#!/usr/bin/env python3
import socket
import os
import time
import sys
import threading

def run_rcu_server():
    # --- CONFIGURATION LOADING ---
    def load_config(device_type):
        """Loads configuration settings (IP, PORT, etc.) from the device-specific text file (rcu.txt)."""
        filename = f"{device_type.lower()}.txt"
        config = {}
        if os.path.exists(filename):
            with open(filename, "r") as f:
                for line in f:
                    try:
                        key, value = line.strip().split("=", 1)
                        config[key] = value
                    except ValueError:
                        continue
        return config

    # --- INITIAL CONFIG ---
    rcu_config = load_config("RCU")
    HOST = rcu_config.get("IP", "127.0.0.1")
    try:
        PORT = int(rcu_config.get("PORT", 1600))
    except ValueError:
        PORT = 1600

    DATA_FILE = 'status_state.txt'  # File used to store the binary status bits

    # --- STATUS FILE MANAGEMENT ---
    def update_status_file(call_type):
        try:
            if not os.path.exists(DATA_FILE):
                with open(DATA_FILE, "w") as f:
                    f.write("11100000")
                return

            with open(DATA_FILE, "r") as f:
                current_status_bin = f.read().strip()
                if not current_status_bin or len(current_status_bin) != 8:
                    current_status_bin = "11100000"

            current_status_int = int(current_status_bin, 2)
            bit_to_reset = {'E1': 0, 'E2': 1, 'E4': 2, 'E8': 3, 'F0': 4}.get(call_type)
            if bit_to_reset is None:
                return

            reset_mask = 1 << bit_to_reset
            new_status_int = current_status_int & (~reset_mask)
            top_bits_mask = 0b11100000
            new_status_int |= top_bits_mask
            new_status_bin = format(new_status_int, '08b')

            with open(DATA_FILE, "w") as f:
                f.write(new_status_bin)

            print(f"Successfully reset call {call_type}. New status: {new_status_bin}")
        except Exception as e:
            print(f"Error updating status file: {e}")

    # --- CONFIG MONITOR THREAD ---
    def monitor_config():
        last_ip = HOST
        last_port = PORT
        while True:
            time.sleep(1)  # Check every 1 second
            new_cfg = load_config("RCU")
            new_ip = new_cfg.get("IP", last_ip)
            try:
                new_port = int(new_cfg.get("PORT", last_port))
            except:
                new_port = last_port

            if new_ip != last_ip or new_port != last_port:
                print("\n[RCU] CONFIG CHANGE DETECTED!")
                print(f"[RCU] OLD IP:   {last_ip}, NEW IP:   {new_ip}")
                print(f"[RCU] OLD PORT: {last_port}, NEW PORT: {new_port}")
                print("[RCU] RESTARTING PROGRAM WITH NEW CONFIG...\n")
                time.sleep(1)
                os.execv(sys.executable, ['python3'] + sys.argv)

    # Start the config monitor in a separate thread
    threading.Thread(target=monitor_config, daemon=True).start()

    # --- TCP LISTENER ---
    def Start_TCP_listner():
        nonlocal HOST, PORT
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((HOST, PORT))
                print(f"[RCU] Listening ON {HOST}:{PORT}")
                server_socket.listen(5)

                while True:
                    client_socket, client_address = server_socket.accept()
                    print(f"[RCU] Connection Established with {client_address}")

                    with client_socket:
                        data = client_socket.recv(1024)
                        if not data:
                            continue
                        try:
                            received_data = data.decode(errors='ignore').strip()
                        except UnicodeDecodeError:
                            received_data = data.hex().upper()

                        print(f"[RCU] Received Data: {received_data}")

                        # --- Handle Binary Poll Request ---
                        if received_data.startswith("REQ:20") or received_data.startswith("ACK:20"):
                            print("[RCU] Text Poll Request received from FCU")
                            try:
                                with open(DATA_FILE, "r") as f:
                                    binary_status_from_file = f.read().strip()
                                if len(binary_status_from_file) != 8:
                                    binary_status_from_file = "11100000"
                            except FileNotFoundError:
                                binary_status_from_file = "11100000"

                            last_5_bits = binary_status_from_file[3:]
                            wire_binary_status = "101" + last_5_bits
                            hex_status_xx = format(int(wire_binary_status, 2), '02X')
                            full_hex_response = f"5245513A33300181{hex_status_xx}02"
                            response_bytes_to_send = bytes.fromhex(full_hex_response)
                            client_socket.sendall(response_bytes_to_send)
                            print(f"[RCU] Sent HEX: {full_hex_response} (From {binary_status_from_file})")


                        # --- Handle ACK:25 RESET PACKET ---
                        elif received_data.startswith("ACK:25"):

                            # Convert full incoming bytes to HEX
                            full_hex = data.hex().upper()

                            # New prefix to remove
                            prefix = "41434B3A3235"

                            if full_hex.startswith(prefix):
                                stripped = full_hex[len(prefix):]
                            else:
                                stripped = full_hex  # fallback

                            # Scan until first A–F (start of reset code)
                            idx = None
                            for i, ch in enumerate(stripped):
                                if ch in "ABCDEF":
                                    idx = i
                                    break

                            if idx is not None and idx + 1 < len(stripped):
                                call_type = stripped[idx:idx+2]

                                print(f"[RCU] Received reset code: {stripped}")
                                print(f"[RCU] Extracted Reset Code: {call_type}")

                                update_status_file(call_type)
                                client_socket.sendall(b"ACK")
                            else:
                                # No valid reset character found
                                continue

 

        except socket.error as e:
            print(f"[RCU] Server socket error: {e}. Retrying bind in 5 seconds...")
            time.sleep(5)
            Start_TCP_listner()

    # --- MAIN EXECUTION ---
    Start_TCP_listner()


if __name__ == "__main__":
    run_rcu_server()