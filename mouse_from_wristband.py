import math
import time
import msvcrt
import serial
import pyautogui

PORT = "COM10"
BAUD = 115200

GAIN_X = 2.0
GAIN_Y = 2.0
DEADZONE_DEG = 5.0
MAX_STEP = 18
SMOOTHING = 0.20

CALIBRATION_SECONDS = 2.0
PACKET_TIMEOUT = 0.10  # seconds

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def read_packet(ser):
    raw = ser.readline()
    if not raw:
        return None

    line = raw.decode("utf-8", errors="ignore").strip()
    if not line.startswith("WB,"):
        return None

    parts = line.split(",")
    if len(parts) != 14:
        return None

    try:
        return {
            "seq": int(parts[1]),
            "uptime": int(parts[2]),
            "ax": int(parts[3]),
            "ay": int(parts[4]),
            "az": int(parts[5]),
            "tof1": int(parts[12]),
            "tof2": int(parts[13]),
        }
    except ValueError:
        return None

def accel_to_angles(ax, ay, az):
    ax_g = ax / 16384.0
    ay_g = ay / 16384.0
    az_g = az / 16384.0

    pitch = math.degrees(math.atan2(-ax_g, math.sqrt(ay_g * ay_g + az_g * az_g)))
    roll = math.degrees(math.atan2(ay_g, az_g))
    return pitch, roll

def get_key():
    if msvcrt.kbhit():
        ch = msvcrt.getch()
        try:
            return ch.decode("utf-8", errors="ignore").lower()
        except Exception:
            return ""
    return ""

def flush_serial_input(ser):
    ser.reset_input_buffer()
    time.sleep(0.1)
    ser.reset_input_buffer()

def calibrate_center(ser):
    print("Hold wristband at neutral position.")
    print(f"Calibrating for {CALIBRATION_SECONDS:.1f} seconds...")
    print("Press Q to stop.")

    flush_serial_input(ser)

    pitch_sum = 0.0
    roll_sum = 0.0
    samples = 0
    start = time.time()

    while time.time() - start < CALIBRATION_SECONDS:
        key = get_key()
        if key == "q":
            raise KeyboardInterrupt

        pkt = read_packet(ser)
        if pkt is None:
            continue

        pitch, roll = accel_to_angles(pkt["ax"], pkt["ay"], pkt["az"])
        pitch_sum += pitch
        roll_sum += roll
        samples += 1

    if samples == 0:
        raise RuntimeError("No packets received during calibration")

    pitch_zero = pitch_sum / samples
    roll_zero = roll_sum / samples

    print(f"Calibration done: pitch_zero={pitch_zero:.2f}, roll_zero={roll_zero:.2f}")
    return pitch_zero, roll_zero

def main():
    print(f"Opening {PORT}...")
    ser = serial.Serial(PORT, BAUD, timeout=0.02)
    time.sleep(2)

    flush_serial_input(ser)

    print(f"Listening on {PORT}")
    print("Q = quit, R = recalibrate\n")

    pitch_zero, roll_zero = calibrate_center(ser)

    smooth_dx = 0.0
    smooth_dy = 0.0
    counter = 0
    last_packet_time = 0.0

    while True:
        key = get_key()
        if key == "q":
            print("\nStopped by user.")
            break
        elif key == "r":
            print("\nRecalibrating...")
            pitch_zero, roll_zero = calibrate_center(ser)
            smooth_dx = 0.0
            smooth_dy = 0.0
            last_packet_time = 0.0
            continue

        pkt = read_packet(ser)

        if pkt is not None:
            last_packet_time = time.time()

            pitch, roll = accel_to_angles(pkt["ax"], pkt["ay"], pkt["az"])
            pitch -= pitch_zero
            roll -= roll_zero

            move_x = 0.0
            move_y = 0.0

            if abs(roll) > DEADZONE_DEG:
                move_x = (roll - math.copysign(DEADZONE_DEG, roll)) * GAIN_X

            if abs(pitch) > DEADZONE_DEG:
                move_y = (pitch - math.copysign(DEADZONE_DEG, pitch)) * GAIN_Y

            move_y = -move_y

            smooth_dx = (1.0 - SMOOTHING) * smooth_dx + SMOOTHING * move_x
            smooth_dy = (1.0 - SMOOTHING) * smooth_dy + SMOOTHING * move_y

            dx = int(clamp(round(smooth_dx), -MAX_STEP, MAX_STEP))
            dy = int(clamp(round(smooth_dy), -MAX_STEP, MAX_STEP))

            if dx != 0 or dy != 0:
                pyautogui.moveRel(dx, dy, duration=0)

            counter += 1
            if counter % 10 == 0:
                print(
                    f"seq={pkt['seq']} pitch={pitch:7.2f} roll={roll:7.2f} "
                    f"dx={dx:3d} dy={dy:3d} tof1={pkt['tof1']:4d} tof2={pkt['tof2']:4d}   ",
                    end="\r",
                    flush=True
                )

        else:
            # No fresh packet: force motion to zero quickly
            if last_packet_time != 0.0 and (time.time() - last_packet_time) > PACKET_TIMEOUT:
                smooth_dx = 0.0
                smooth_dy = 0.0

            time.sleep(0.002)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"\nError: {e}")