#!/usr/bin/env python3
import os
import subprocess
import serial
import time

# -------------------------
# Serial write helper
# -------------------------
def write_serial(ser, message):
    """Writes a message to the serial port with CR+LF."""
    ser.write(f"{message}\r\n".encode('utf-8'))

# -------------------------
# Serial read helper
# -------------------------
def read_serial_input(ser):
    """Safely reads a complete line from the serial port."""
    input_line = b''
    while True:
        try:
            if ser.in_waiting > 0:
                data = ser.read(1)
                input_line += data
                if data in [b'\r', b'\n']:
                    break
            else:
                time.sleep(0.01)  # small delay to prevent CPU spinning
        except serial.SerialException:
            # Ignore transient serial errors, continue reading
            continue
    return input_line.decode('utf-8').strip()

# -------------------------
# Load existing configuration
# -------------------------
def load_existing_config(device_type):
    """Loads network configuration from device-specific text file."""
    filename = f"{device_type.lower()}.txt"
    config = {
        "TYPE": device_type,
        "IP": "",
        "SUBNET": "",
        "GATEWAY": "",
        "PORT": ""
    }
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        with open(filename, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    config[key] = value
    return config

# -------------------------
# Apply network settings live
# -------------------------
def apply_network_live(config, ser):
    """Applies the IP configuration immediately to the system."""
    ip = config["IP"]
    subnet = config["SUBNET"]
    gw = config["GATEWAY"]

    if ip == "" or subnet == "":
        write_serial(ser, "[NET] Skipped: IP/SUBNET not configured.")
        return

    write_serial(ser, "[NET] Applying network settings LIVE...")

    try:
        # Write static config to dhcpcd.conf
        with open("/etc/dhcpcd.conf", "w") as f:
            f.write("interface eth0\n")
            f.write(f"static ip_address={ip}/{subnet}\n")
            if gw != "":
                f.write(f"static routers={gw}\n")
            f.write("static domain_name_servers=8.8.8.8 1.1.1.1\n")
        write_serial(ser, "[NET] dhcpcd.conf updated.")
    except Exception as e:
        write_serial(ser, f"[NET] ERROR writing dhcpcd.conf: {e}")
        return

    # Restart dhcpcd service
    subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    write_serial(ser, "[NET] dhcpcd restarted.")

    # Reinitialize network interface
    subprocess.run(["sudo", "ip", "link", "set", "eth0", "down"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)
    subprocess.run(["sudo", "ip", "address", "flush", "dev", "eth0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["sudo", "ip", "link", "set", "eth0", "up"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    write_serial(ser, f"[NET] New IP applied: {ip}")
    write_serial(ser, "[NET] Network reloaded successfully.")

# -------------------------
# Save config to file
# -------------------------
def save_config_to_file(device_type, config, ser):
    filename = f"{device_type.lower()}.txt"
    with open(filename, "w") as f:
        for key in ["TYPE", "IP", "SUBNET", "GATEWAY", "PORT"]:
            f.write(f"{key}={config[key]}\n")

    write_serial(ser, f"[NET] Configuration saved to {filename}")
    apply_network_live(config, ser)

# -------------------------
# Edit configuration via serial
# -------------------------
def edit_config(config, ser, device_type):
    """Allows the user to edit configuration values via serial console."""
    write_serial(ser, f"\n\n\r--- EDIT {device_type} CONFIGURATION ---")
    for key in ["IP", "SUBNET", "GATEWAY", "PORT"]:
        current_value = config[key]
        ser.write(f"\n\r{key} [{current_value}]: ".encode('utf-8'))
        new_value = read_serial_input(ser)
        if new_value:
            config[key] = new_value
    return config

# -------------------------
# Handle configuration process
# -------------------------
def handle_config(device_type, ser):
    config = load_existing_config(device_type)
    config = edit_config(config, ser, device_type)
    save_config_to_file(device_type, config, ser)

# -------------------------
# Show main menu
# -------------------------
def show_menu(ser):
    write_serial(ser, "\n=== CONFIGURATION MENU ===")
    write_serial(ser, "1. Configure RCU")
    write_serial(ser, "2. Configure FCU")
    write_serial(ser, "3. Exit")
    ser.write(b"Select an option: ")

# -------------------------
# Main program
# -------------------------
def main():
    ser = None
    while ser is None:
        try:
            ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
            write_serial(ser, "*** Serial Configuration Program is Ready ***")
        except serial.SerialException as e:
            print(f"Serial error: {e}. Retrying in 5s...")
            time.sleep(5)
            continue

    while True:
        try:
            show_menu(ser)
            choice = read_serial_input(ser)
            if choice == '1':
                handle_config("RCU", ser)
            elif choice == '2':
                handle_config("FCU", ser)
            elif choice == '3':
                write_serial(ser, "Exiting program.")
                break
            else:
                write_serial(ser, "[!] Invalid option. Please select 1, 2, or 3.")
        except serial.SerialException as e:
            print(f"Serial error: {e}. Reconnecting...")
            try:
                ser.close()
            except:
                pass
            ser = None
            while ser is None:
                try:
                    ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
                    write_serial(ser, "*** Reconnected ***")
                except:
                    time.sleep(5)

if __name__ == "__main__":
    main()