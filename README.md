# 🏥 Hinduja Hospital Nurse Call System

A Raspberry Pi-based Nurse Call and Emergency Communication System designed to provide reliable communication between patients and hospital staff.

## 📌 Overview

The system consists of **Room Call Units (RCUs)**, a central **Floor Call Unit (FCU)**, and a monitoring server.

Each RCU handles:

- Nurse Call
- Attendant Call
- Emergency Call
- Call Reset
- LED and Door Lamp indication

The FCU continuously polls **24 RCUs**, collects their 8-bit status, converts the data to hexadecimal, consolidates all RCU statuses, and sends the information to the central server over TCP/IP.

## 🏗️ System Architecture

```text
Patient
   |
   v
+---------+
|   RCU   |  ← Nurse / Attendant / Emergency Calls
+----+----+
     |
     | TCP/IP
     v
+---------+
|   FCU   |  ← Polls 24 RCUs & Consolidates Status
+----+----+
     |
     | TCP/IP
     v
+---------+
| Server  |  ← Central Monitoring
+---------+

🔧 Hardware
Raspberry Pi
MCP23017 GPIO Expanders
Call and Reset Buttons
Status LEDs
Door Lamps
Current-Limiting Resistors
Breadboard and Jumper Wires

💻 Technologies
Python
Raspberry Pi GPIO
TCP/IP Socket Programming
I2C Communication
MCP23017
Bitwise Operations
Linux Network Configuration
File-Based State Persistence

🔢 RCU Status
Each RCU uses an 8-bit status value to represent system and call conditions.

Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0
       |       |       |       |       |       |       |
       |       |       |       |       |       |       +-- R1 Nurse
       |       |       |       |       |       |---------- R1 Attendant
       |       |       |       |       +------------------ R2 Attendant
       |       |       |       +-------------------------- Emergency
       |       |       +---------------------------------- Installed
       |       +------------------------------------------ Working
       +-------------------------------------------------- Reserved

Example status codes:

A0 → No response / inactive
E1 → R1 Nurse Call
E3 → R1 Nurse + Attendant
E7 → R1 Nurse + R1 Attendant + R2 Nurse
EF → All standard calls
F0 → Emergency
FF → All buttons pressed

📂 Main Files
File	Description
GPIO_ports.py	Handles RCU GPIO inputs, outputs and call states
Polling.py	Polls all 24 RCUs
RCU-TCP.py	TCP server for RCU communication
FCU-TCP.py	Sends consolidated data to server
FCU-LED.py	Controls FCU LEDs using MCP23017
serial_config_program.py	Configures RCU/FCU network settings

⭐ Key Features
24-RCU centralized polling
Nurse, attendant and emergency calls
Latched call states
Physical reset mechanism
LED and door-lamp indication
Persistent call-state recovery
TCP/IP communication
8-bit status representation
MCP23017 GPIO expansion
Automatic handling of unreachable RCUs
⚠️ Disclaimer
This project is documented for engineering and educational purposes. Any use in a real clinical or safety-critical environment requires appropriate hardware, software, electrical, security, and regulatory validation.
