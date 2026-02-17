import threading
import cv2
import logging
from screen import *
from options import *

dx = None
obs_camera = None
logger = logging.getLogger(__name__)

def thread_hook(args):
    if 'DXCamera' in str(args.thread) and 'cannot join current thread' in str(args.exc_value):
        logger.error(
            "DXCamera thread failed: fullscreen mode is likely enabled. "
            "Switch game to windowed or borderless mode."
        )


def _validate_capture_method_selection() -> None:
    enabled = int(Dxcam_capture) + int(Obs_capture) + int(native_Windows_capture)
    if enabled != 1:
        raise ValueError("Exactly one capture method must be enabled in options.py")

def get_new_frame():
    global dx
    global obs_camera

    threading.excepthook = thread_hook
    _validate_capture_method_selection()

    img = None
    if Dxcam_capture and dx is None:
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError("DXCam is required when Dxcam_capture=True") from exc
        dx = dxcam.create(device_idx=dxcam_monitor_id, output_idx=dxcam_gpu_id, output_color="BGR", max_buffer_len=dxcam_max_buffer_len)
        if dx.is_capturing == False:
            dx.start(Calculate_screen_offset(), target_fps=dxcam_capture_fps)
            logger.info("DXCam capture started")
    if Dxcam_capture and dx is not None:
        img = dx.get_latest_frame()

    if Obs_capture and obs_camera is None:
        obs_camera = cv2.VideoCapture(Obs_camera_id)
        obs_camera.set(cv2.CAP_PROP_FRAME_WIDTH, detection_window_width)
        obs_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, detection_window_height)
        obs_camera.set(cv2.CAP_PROP_FPS, Obs_capture_fps)
        logger.info("OBS camera capture initialized")
    if Obs_capture and obs_camera is not None:
        ret_val, img = obs_camera.read()
        if not ret_val:
            logger.warning("OBS camera returned no frame")
            return None
        
    if native_Windows_capture:
        img = windows_grab_screen(Calculate_screen_offset())

    return img


def cleanup_capture():
    global dx
    global obs_camera

    if dx is not None:
        try:
            if dx.is_capturing:
                dx.stop()
                logger.info("DXCam capture stopped")
        except Exception:
            logger.exception("Failed while stopping DXCam capture")
        finally:
            dx = None

    if obs_camera is not None:
        try:
            obs_camera.release()
            logger.info("OBS camera released")
        except Exception:
            logger.exception("Failed while releasing OBS camera")
        finally:
            obs_camera = None

def speed(annotated_frame, speed_preprocess, speed_inference, speed_postprocess):
    cv2.putText(annotated_frame, 'preprocess:', (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(annotated_frame, str(speed_preprocess), (150, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

    cv2.putText(annotated_frame, 'inference:', (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(annotated_frame, str(speed_inference), (150, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

    cv2.putText(annotated_frame, 'postprocess:', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(annotated_frame, str(speed_postprocess), (150, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    return annotated_frame

def draw_helpers(annotated_frame, boxes):
    for item in boxes:
        if item is not None:
            for xyxy in item.xyxy:
                if show_boxes:
                    annotated_frame = cv2.rectangle(annotated_frame, (int(xyxy[0].item()), int(xyxy[1].item())), (int(xyxy[2].item()), int(xyxy[3].item())), (0, 200, 0), 0)
                    if show_labels:
                        str_cls = ''
                        for cls in item.cls:
                            match cls:
                                case 0:
                                    str_cls = 'player'
                                case 1:
                                    str_cls = 'bot'
                                case 2:
                                    str_cls = 'weapon'
                                case 3:
                                    str_cls = 'teammate_nickname'
                                case 4:
                                    str_cls = 'dead_body'
                                case 5:
                                    str_cls = 'hideout_target_human'
                                case 6:
                                    str_cls = 'hideout_target_balls'
                                case 7:
                                    str_cls = 'head'
                                case 8:
                                    str_cls = 'smoke'
                                case 9:
                                    str_cls = 'fire'
                            if show_conf == False:
                                annotated_frame = cv2.putText(annotated_frame, str_cls, (int(xyxy[0].item()), int(xyxy[1].item() - 5)), cv2.FONT_HERSHEY_SIMPLEX , 1, (0, 200, 0), 1, cv2.LINE_AA)
                    if show_conf:
                        for conf in item.conf:
                            annotated_frame = cv2.putText(annotated_frame, str('{} {:.2f}'.format(str_cls,conf.item())), (int(xyxy[0].item()), int(xyxy[1].item() - 5)), cv2.FONT_HERSHEY_SIMPLEX , 1, (0, 200, 0), 1, cv2.LINE_AA)
    return annotated_frame
