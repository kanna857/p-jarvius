"""
Vision Agent (Background Mode)
- No visible window
- Screenshot capture + OCR
- GPT-4o Vision for screen understanding
- Face/object detection on request
- Webcam runs hidden, frames stored in memory
"""

import cv2
import numpy as np
import threading
import time
import base64
from utils.logger import JarvisLogger
from utils.config import Config


class VisionAgent:
    def __init__(self, config: Config):
        self.config = config
        self.logger = JarvisLogger("Vision")
        self.cap = None
        self.running = False
        self.current_frame = None
        self._stop = threading.Event()

        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        
        self.mp_available = None
        self.yolo_available = None
        self.yolo = None
        self.hands = None
        
        self.logger.success("Vision agent ready (background mode, lazy loading active)")

    def _init_mediapipe(self):
        if self.hands is not None:
            return
        try:
            self.logger.info("Initializing MediaPipe...")
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                max_num_hands=1,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.7,
            )
            self.mp_available = True
            self.logger.success("MediaPipe initialized.")
        except ImportError:
            self.mp_available = False

    def _init_yolo(self):
        if self.yolo is not None:
            return
        try:
            self.logger.info("Loading YOLO object model...")
            from ultralytics import YOLO
            self.yolo = YOLO("yolov8n.pt")
            self.yolo_available = True
            self.logger.success("YOLO loaded successfully.")
        except ImportError:
            self.yolo_available = False

    def run_background(self):
        """
        Silently capture webcam frames in the background.
        No cv2.imshow — purely in-memory.
        """
        self.cap = cv2.VideoCapture(self.config.CAMERA_INDEX)
        if not self.cap.isOpened():
            self.logger.warning("Webcam not available — vision capture disabled.")
            return
        self.running = True
        self.logger.info("Webcam capturing silently...")
        while not self._stop.is_set():
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
            time.sleep(0.05)  # ~20 fps
        self.cap.release()

    def capture_screenshot(self) -> np.ndarray:
        """Capture full screen without opening any window"""
        import pyautogui
        from PIL import Image
        pil_img = pyautogui.screenshot()
        frame = np.array(pil_img)
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def run_ocr(self, image: np.ndarray = None) -> str:
        """Run OCR on screen or given image"""
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            if image is None:
                image = self.capture_screenshot()
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            text = pytesseract.image_to_string(gray)
            return text.strip()
        except ImportError:
            return "Tesseract not installed."
        except Exception as e:
            return f"OCR error: {e}"

    def analyze_screen_with_ai(self, openai_client, question: str = "What's on the screen?", max_tokens: int = 800) -> str:
        """Send screenshot to GPT-4o / Groq Vision"""
        screen = self.capture_screenshot()
        _, buf = cv2.imencode(".jpg", screen, [cv2.IMWRITE_JPEG_QUALITY, 70])
        b64 = base64.b64encode(buf).decode("utf-8")
        try:
            model_n = "gpt-4o"
            if hasattr(openai_client, "base_url") and openai_client.base_url:
                base_url_str = str(openai_client.base_url)
                if "groq" in base_url_str:
                    model_n = "meta-llama/llama-4-scout-17b-16e-instruct"
                elif "googleapis.com" in base_url_str:
                    model_n = "gemini-1.5-flash"
                elif "x.ai" in base_url_str:
                    model_n = "grok-2-1212"
                elif "11434" in base_url_str or "ollama" in base_url_str:
                    model_n = self.config.OLLAMA_MODEL
                
            resp = openai_client.chat.completions.create(
                model=model_n,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            self.logger.warning(f"Vision AI failed: {e}. Falling back to OCR analysis.")
            try:
                ocr_text = self.run_ocr(screen)
                if not ocr_text:
                    return "Vision AI failed, and OCR detected no text on the screen."
                
                text_model = "gpt-4o-mini"
                if hasattr(openai_client, "base_url") and openai_client.base_url:
                    base_url_str = str(openai_client.base_url)
                    if "groq" in base_url_str:
                        text_model = "llama-3.3-70b-versatile"
                    elif "11434" in base_url_str or "ollama" in base_url_str:
                        text_model = self.config.OLLAMA_MODEL
                
                resp = openai_client.chat.completions.create(
                    model=text_model,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"The user asked: '{question}'.\n"
                            f"We couldn't use the vision model, but we extracted the following text from their screen via OCR:\n\n"
                            f"--- OCR TEXT START ---\n{ocr_text}\n--- OCR TEXT END ---\n\n"
                            f"Please answer the user's question about their screen based on this OCR text."
                        )
                    }],
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content.strip()
            except Exception as ocr_err:
                return f"Vision AI error: {e} (OCR Fallback also failed: {ocr_err})"

    def count_faces(self) -> int:
        if self.current_frame is None:
            return 0
        gray = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
        return len(faces)

    def detect_objects(self) -> list[str]:
        if self.yolo is None:
            self._init_yolo()
            
        if not self.yolo_available or self.current_frame is None:
            return []
        results = self.yolo(self.current_frame, verbose=False)
        labels = []
        for r in results:
            for box in r.boxes:
                labels.append(self.yolo.names[int(box.cls)])
        return list(set(labels))[:8]

    def detect_gesture(self) -> str | None:
        if self.hands is None:
            self._init_mediapipe()

        if not self.mp_available or self.current_frame is None:
            return None
        rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)
        if not result.multi_hand_landmarks:
            return None
        lm = result.multi_hand_landmarks[0].landmark
        if lm[4].y < lm[3].y and all(lm[f].y > lm[f-2].y for f in [8, 12, 16, 20]):
            return "thumbs_up"
        if all(lm[f].y < lm[f-2].y for f in [8, 12, 16, 20]):
            return "open_palm"
        return None

    def handle_command(self, cmd: str) -> str:
        if any(k in cmd for k in ["screen", "what's on", "error", "read"]):
            text = self.run_ocr()
            if text:
                return f"I can read: {text[:300]}"
            return "Screen appears to have no readable text."
        elif "face" in cmd or "who" in cmd:
            n = self.count_faces()
            return f"I detect {n} face{'s' if n != 1 else ''} in the webcam view."
        elif "object" in cmd or "see" in cmd or "look" in cmd:
            objs = self.detect_objects()
            return f"I can see: {', '.join(objs)}." if objs else "No objects detected."
        elif "gesture" in cmd:
            g = self.detect_gesture()
            return f"Gesture detected: {g}." if g else "No gesture detected."
        return "Vision command not understood."

    def verify_user_face(self, openai_client, user_image_path: str) -> bool:
        """Uses AI to compare stored image with current webcam frame."""
        import os
        if not os.path.exists(user_image_path):
            self.logger.warning(f"Reference face image not found at {user_image_path}")
            return False
        
        if self.current_frame is None:
            return False

        try:
            # 1. Encode current frame
            _, buf1 = cv2.imencode(".jpg", self.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            cam_b64 = base64.b64encode(buf1).decode("utf-8")

            # 2. Load and encode user photo
            with open(user_image_path, "rb") as f:
                ref_b64 = base64.b64encode(f.read()).decode("utf-8")

            model_n = "gpt-4o"
            if hasattr(openai_client, "base_url") and openai_client.base_url:
                base_url_str = str(openai_client.base_url)
                if "groq" in base_url_str:
                    model_n = "meta-llama/llama-4-scout-17b-16e-instruct"
                elif "googleapis.com" in base_url_str:
                    model_n = "gemini-1.5-flash"
                elif "x.ai" in base_url_str:
                    model_n = "grok-2-1212"
                elif "11434" in base_url_str or "ollama" in base_url_str:
                    model_n = self.config.OLLAMA_MODEL

            resp = openai_client.chat.completions.create(
                model=model_n,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Assess these two images. Do they show the same human face/person? Disregard differences like glasses, lighting, or background. Answer ONLY with 'TRUE' if it is the same individual, or 'FALSE'."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{cam_b64}"}},
                    ],
                }],
                max_tokens=100,
                temperature=0.0
            )
            
            answer = resp.choices[0].message.content.strip().upper()
            self.logger.info(f"Face comparison result: {answer}")
            return "TRUE" in answer
        except Exception as e:
            self.logger.error(f"User face verification failed: {e}")
            return False

    def stop(self):
        self._stop.set()
        if self.cap:
            self.cap.release()
