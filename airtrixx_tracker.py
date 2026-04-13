import time
import threading
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import mediapipe as mp
import serial

PORT = "COM10"
BAUD = 115200

CAM_INDEX = 0
FRAME_W = 640
FRAME_H = 480
TARGET_FPS = 30

SERVO_MIN_US = 900
SERVO_MAX_US = 2100

CAM_PAN_CENTER = 1500
CAM_TILT_CENTER = 1500

L_PAN_CENTER = 1500
L_TILT_CENTER = 1500

R_PAN_CENTER = 1500
R_TILT_CENTER = 1500

Kp_CAM_PAN = 140.0
Kp_CAM_TILT = 120.0
Kp_TOF_PAN = 140.0
Kp_TOF_TILT = 120.0

DEADBAND_FACE = 0.03
DEADBAND_HAND = 0.03

MAX_STEP_CAM = 28
MAX_STEP_TOF = 30

FACE_LOCK_ERR = 0.05
LOCK_HOLD_SEC = 0.8
FACE_LOST_UNLOCK_SEC = 1.0

FLIP_VIEW = False


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def norm_err(px: float, size: int) -> float:
    return (px - size / 2.0) / (size / 2.0)


def apply_p_controller(us: int, err: float, kp: float, deadband: float, max_step: int) -> int:
    if abs(err) < deadband:
        return us
    delta = kp * err
    delta = clamp(delta, -max_step, max_step)
    return int(us + delta)


@dataclass
class Telemetry:
    ms: int = 0
    wb_valid: int = 0
    seq: int = 0
    uptime: int = 0
    ax: int = 0
    ay: int = 0
    az: int = 0
    gx: int = 0
    gy: int = 0
    gz: int = 0
    mx: int = 0
    my: int = 0
    mz: int = 0
    tofL: int = -1
    tofR: int = -1
    last_rx_time: float = 0.0


class SharedTelemetry:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = Telemetry()

    def update_from_line(self, line: str):
        parts = line.split(",")
        if len(parts) != 16 or parts[0] != "CD":
            return

        t = Telemetry(
            ms=int(parts[1]),
            wb_valid=int(parts[2]),
            seq=int(parts[3]),
            uptime=int(parts[4]),
            ax=int(parts[5]),
            ay=int(parts[6]),
            az=int(parts[7]),
            gx=int(parts[8]),
            gy=int(parts[9]),
            gz=int(parts[10]),
            mx=int(parts[11]),
            my=int(parts[12]),
            mz=int(parts[13]),
            tofL=int(parts[14]),
            tofR=int(parts[15]),
            last_rx_time=time.time(),
        )

        with self.lock:
            self.data = t

    def snapshot(self) -> Telemetry:
        with self.lock:
            return Telemetry(**self.data.__dict__)


class CamDockLink:
    def __init__(self, port: str, baud: int):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        time.sleep(1.5)
        self.ser.reset_input_buffer()
        self.last_sent = None

    def send_sva(self, cam_pan: int, cam_tilt: int, l_pan: int, l_tilt: int, r_pan: int, r_tilt: int):
        payload = (cam_pan, cam_tilt, l_pan, l_tilt, r_pan, r_tilt)
        if payload == self.last_sent:
            return
        self.last_sent = payload
        cmd = f"SVA,{cam_pan},{cam_tilt},{l_pan},{l_tilt},{r_pan},{r_tilt}\n"
        self.ser.write(cmd.encode("ascii", errors="ignore"))

    def send_center(self):
        self.ser.write(b"CENTER\n")

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def serial_reader(link: CamDockLink, shared: SharedTelemetry, stop_flag):
    while not stop_flag["stop"]:
        try:
            raw = link.ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("CD,"):
                shared.update_from_line(line)
        except Exception:
            time.sleep(0.05)


def detect_targets(frame_bgr, hands, face_det):
    if FLIP_VIEW:
        frame_bgr = cv2.flip(frame_bgr, 1)

    h, w = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    face_center = None
    face_results = face_det.process(rgb)
    if face_results.detections:
        det = max(face_results.detections, key=lambda d: d.score[0])
        bbox = det.location_data.relative_bounding_box
        cx = int((bbox.xmin + bbox.width * 0.5) * w)
        cy = int((bbox.ymin + bbox.height * 0.5) * h)
        face_center = (cx, cy)

    left_hand = None
    right_hand = None

    hand_results = hands.process(rgb)
    if hand_results.multi_hand_landmarks:
        for idx, lm_set in enumerate(hand_results.multi_hand_landmarks):
            wrist = lm_set.landmark[0]
            hx = int(wrist.x * w)
            hy = int(wrist.y * h)

            label = None
            if hand_results.multi_handedness and idx < len(hand_results.multi_handedness):
                label = hand_results.multi_handedness[idx].classification[0].label

            if label == "Left":
                left_hand = (hx, hy)
            elif label == "Right":
                right_hand = (hx, hy)

            mp.solutions.drawing_utils.draw_landmarks(
                frame_bgr, lm_set, mp.solutions.hands.HAND_CONNECTIONS
            )

        if left_hand is None or right_hand is None:
            pts = []
            for lm_set in hand_results.multi_hand_landmarks:
                wrist = lm_set.landmark[0]
                pts.append((int(wrist.x * w), int(wrist.y * h)))
            pts = sorted(pts, key=lambda p: p[0])
            if len(pts) >= 1 and left_hand is None:
                left_hand = pts[0]
            if len(pts) >= 2 and right_hand is None:
                right_hand = pts[-1]

    if face_center is not None:
        cv2.circle(frame_bgr, face_center, 6, (0, 255, 255), -1)
    if left_hand is not None:
        cv2.circle(frame_bgr, left_hand, 8, (255, 0, 0), -1)
    if right_hand is not None:
        cv2.circle(frame_bgr, right_hand, 8, (0, 0, 255), -1)

    return frame_bgr, face_center, left_hand, right_hand


def xy_norm(pt: Optional[Tuple[int, int]], w: int, h: int):
    if pt is None:
        return -1.0, -1.0
    return pt[0] / w, pt[1] / h


def main():
    print("Starting AirTrixx tracker...")
    print("q = quit | c = re-center all servos")

    link = CamDockLink(PORT, BAUD)
    shared = SharedTelemetry()

    stop_flag = {"stop": False}
    t = threading.Thread(target=serial_reader, args=(link, shared, stop_flag), daemon=True)
    t.start()

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

    mp_hands = mp.solutions.hands
    mp_face = mp.solutions.face_detection

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    face_det = mp_face.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.5,
    )

    cam_pan = CAM_PAN_CENTER
    cam_tilt = CAM_TILT_CENTER

    l_pan = L_PAN_CENTER
    l_tilt = L_TILT_CENTER

    r_pan = R_PAN_CENTER
    r_tilt = R_TILT_CENTER

    camera_locked = False
    lock_start = None
    last_face_seen = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue

        frame, face_center, left_hand, right_hand = detect_targets(frame, hands, face_det)

        h, w = frame.shape[:2]
        now = time.time()

        if face_center is not None:
            last_face_seen = now
            ex = norm_err(face_center[0], w)
            ey = norm_err(face_center[1], h)

            if not camera_locked:
                cam_pan = apply_p_controller(cam_pan, ex, Kp_CAM_PAN, DEADBAND_FACE, MAX_STEP_CAM)
                cam_tilt = apply_p_controller(cam_tilt, ey, Kp_CAM_TILT, DEADBAND_FACE, MAX_STEP_CAM)

            both_hands = (left_hand is not None and right_hand is not None)
            face_centered = abs(ex) < FACE_LOCK_ERR and abs(ey) < FACE_LOCK_ERR

            if not camera_locked and both_hands and face_centered:
                if lock_start is None:
                    lock_start = now
                elif now - lock_start >= LOCK_HOLD_SEC:
                    camera_locked = True
            else:
                if not camera_locked:
                    lock_start = None
        else:
            if now - last_face_seen > FACE_LOST_UNLOCK_SEC:
                camera_locked = False
                lock_start = None

        if left_hand is not None:
            ex_left = norm_err(left_hand[0], w)
            ey_left = norm_err(left_hand[1], h)
            l_pan = apply_p_controller(l_pan, ex_left, Kp_TOF_PAN, DEADBAND_HAND, MAX_STEP_TOF)
            l_tilt = apply_p_controller(l_tilt, ey_left, Kp_TOF_TILT, DEADBAND_HAND, MAX_STEP_TOF)

        if right_hand is not None:
            ex_right = norm_err(right_hand[0], w)
            ey_right = norm_err(right_hand[1], h)
            r_pan = apply_p_controller(r_pan, ex_right, Kp_TOF_PAN, DEADBAND_HAND, MAX_STEP_TOF)
            r_tilt = apply_p_controller(r_tilt, ey_right, Kp_TOF_TILT, DEADBAND_HAND, MAX_STEP_TOF)

        cam_pan = clamp(cam_pan, SERVO_MIN_US, SERVO_MAX_US)
        cam_tilt = clamp(cam_tilt, SERVO_MIN_US, SERVO_MAX_US)

        l_pan = clamp(l_pan, SERVO_MIN_US, SERVO_MAX_US)
        l_tilt = clamp(l_tilt, SERVO_MIN_US, SERVO_MAX_US)

        r_pan = clamp(r_pan, SERVO_MIN_US, SERVO_MAX_US)
        r_tilt = clamp(r_tilt, SERVO_MIN_US, SERVO_MAX_US)

        link.send_sva(cam_pan, cam_tilt, l_pan, l_tilt, r_pan, r_tilt)

        telem = shared.snapshot()
        if time.time() - telem.last_rx_time > 0.5:
            telem.wb_valid = 0
            telem.tofL = -1
            telem.tofR = -1

        lx, ly = xy_norm(left_hand, w, h)
        rx, ry = xy_norm(right_hand, w, h)

        left_z = telem.tofL
        right_z = telem.tofR

        if telem.wb_valid:
            print(
                f"LEFT {lx:.3f},{ly:.3f},{left_z} | "
                f"RIGHT {rx:.3f},{ry:.3f},{right_z} | "
                f"RIGHT_ACC {telem.ax},{telem.ay},{telem.az} | "
                f"RIGHT_GYRO {telem.gx},{telem.gy},{telem.gz} | "
                f"RIGHT_MAG {telem.mx},{telem.my},{telem.mz}",
                end="\r",
                flush=True,
            )
        else:
            print(
                f"LEFT {lx:.3f},{ly:.3f},{left_z} | "
                f"RIGHT {rx:.3f},{ry:.3f},{right_z} | "
                f"RIGHT_ACC N/A | RIGHT_GYRO N/A | RIGHT_MAG N/A",
                end="\r",
                flush=True,
            )

        cv2.putText(
            frame,
            f"camera_locked={camera_locked}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )

        cv2.imshow("AirTrixx Tracker", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q") or key == 27:
            break
        elif key == ord("c"):
            camera_locked = False
            lock_start = None

            cam_pan = CAM_PAN_CENTER
            cam_tilt = CAM_TILT_CENTER

            l_pan = L_PAN_CENTER
            l_tilt = L_TILT_CENTER

            r_pan = R_PAN_CENTER
            r_tilt = R_TILT_CENTER

            link.send_center()

    stop_flag["stop"] = True
    cap.release()
    cv2.destroyAllWindows()
    link.close()
    print("\nStopped.")


if __name__ == "__main__":
    main()