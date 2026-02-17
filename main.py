import logging
import queue
import threading
import time

import cv2
import torch
import win32api
from ultralytics import YOLO

from config_validation import validate_runtime_options
from frame import cleanup_capture, draw_helpers, get_new_frame, speed
from logging_config import configure_logging
from mouse import mouse_close, win32_raw_mouse_move
from options import (
    AI_conf,
    AI_device,
    AI_image_size,
    AI_iou,
    AI_max_det,
    AI_model_path,
    aim_hold_vk,
    debug_window_name,
    debug_window_scale_percent,
    disable_headshot,
    exit_hotkey_vk,
    log_file_path,
    log_level,
    mouse_auto_aim,
    mouse_auto_shoot,
    show_boxes,
    show_fps,
    show_speed,
    show_window,
)
from targets import Targets

logger = logging.getLogger(__name__)


def _debug_window_exists(window_name: str) -> bool:
    try:
        return cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


class WorkQueueThread(threading.Thread):
    def __init__(self, max_size: int):
        super().__init__(name="WorkQueueThread", daemon=True)
        self.queue: queue.Queue[tuple[float, float, float, float, float, float, float] | None] = queue.Queue(
            maxsize=max_size
        )
        self._stop_event = threading.Event()

    def enqueue(self, item: tuple[float, float, float, float, float, float, float]) -> None:
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            logger.warning("Work queue is full, dropping target update")

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            logger.debug("Stop signal delayed because work queue is full")

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                self.queue.task_done()
                break

            try:
                self._process_item(item)
            except Exception:
                logger.exception("Failed while processing aim queue item")
            finally:
                self.queue.task_done()

    def _process_item(self, item: tuple[float, float, float, float, float, float, float]) -> None:
        x, y, target_x, target_y, target_w, target_h, distance = item
        aim_pressed = bool(win32api.GetAsyncKeyState(aim_hold_vk))

        if aim_pressed and not mouse_auto_aim:
            win32_raw_mouse_move(
                x=x, y=y, target_x=target_x, target_y=target_y, target_w=target_w, target_h=target_h, distance=distance
            )

        if mouse_auto_shoot and not mouse_auto_aim:
            win32_raw_mouse_move(
                x=None,
                y=None,
                target_x=target_x,
                target_y=target_y,
                target_w=target_w,
                target_h=target_h,
                distance=distance,
            )

        if mouse_auto_aim:
            win32_raw_mouse_move(
                x=x, y=y, target_x=target_x, target_y=target_y, target_w=target_w, target_h=target_h, distance=distance
            )


def append_queue(boxes, queue_worker: WorkQueueThread) -> None:
    shooting_queue: list[Targets] = []

    if not disable_headshot:
        for box in boxes:
            shooting_queue.append(
                Targets(
                    x=box.xywh[0][0].item(),
                    y=box.xywh[0][1].item(),
                    w=box.xywh[0][2].item(),
                    h=box.xywh[0][3].item(),
                    cls=int(box.cls.item()),
                )
            )
        head_target = len(shooting_queue) < 3 and any(target.cls == 7 for target in shooting_queue)
        if head_target:
            shooting_queue.sort(key=lambda target: target.cls != 7)
        else:
            shooting_queue.sort(key=lambda target: target.distance)
    else:
        for box in boxes:
            target_class = int(box.cls.item())
            if target_class in (0, 1, 5, 6):
                shooting_queue.append(
                    Targets(
                        x=box.xywh[0][0].item(),
                        y=box.xywh[0][1].item(),
                        w=box.xywh[0][2].item(),
                        h=box.xywh[0][3].item(),
                        cls=target_class,
                    )
                )
        shooting_queue.sort(key=lambda target: target.distance)

    if not shooting_queue:
        return

    first_target = shooting_queue[0]
    queue_worker.enqueue(
        (
            first_target.mouse_x,
            first_target.mouse_y,
            first_target.x,
            first_target.y,
            first_target.w,
            first_target.h,
            first_target.distance,
        )
    )


@torch.no_grad()
def init() -> None:
    configure_logging(log_file=log_file_path, level=log_level)

    try:
        validate_runtime_options()
    except ValueError:
        logger.exception("Invalid options configuration")
        return

    try:
        model = YOLO(AI_model_path, task="detect")
    except FileNotFoundError:
        logger.exception("Model file not found")
        return
    except Exception:
        logger.exception("Failed to initialize YOLO model")
        return

    if ".engine" in AI_model_path:
        logger.info("TensorRT engine loaded")
    if ".onnx" in AI_model_path:
        logger.info("ONNX model loaded")
    if ".pt" in AI_model_path:
        logger.info("PyTorch model loaded", extra={"model_info": str(model.info(detailed=False, verbose=False))})

    logger.info("Aimbot started")
    display_enabled = show_window

    if display_enabled:
        logger.info("Debug window is enabled and may reduce performance")
        cv2.namedWindow(debug_window_name)

    queue_worker: WorkQueueThread | None = WorkQueueThread(AI_max_det)
    queue_worker.start()

    prev_frame_time = time.time() if display_enabled and show_fps else 0.0

    try:
        while True:
            source_frame = get_new_frame()
            if source_frame is None:
                continue

            results = model.predict(
                source=source_frame,
                stream=True,
                cfg="game.yaml",
                imgsz=AI_image_size,
                stream_buffer=False,
                agnostic_nms=False,
                save=False,
                conf=AI_conf,
                iou=AI_iou,
                device=AI_device,
                half=False,
                max_det=AI_max_det,
                vid_stride=False,
                classes=range(9),
                verbose=False,
                show_boxes=False,
                show_labels=False,
                show_conf=False,
            )

            annotated_frame = source_frame.copy() if display_enabled else None

            for prediction in results:
                if display_enabled and show_speed and annotated_frame is not None:
                    annotated_frame = speed(
                        annotated_frame, prediction.speed["preprocess"], prediction.speed["inference"], prediction.speed["postprocess"]
                    )

                if len(prediction.boxes):
                    append_queue(prediction.boxes, queue_worker)
                    if display_enabled and show_boxes and annotated_frame is not None:
                        annotated_frame = draw_helpers(annotated_frame=annotated_frame, boxes=prediction.boxes)

            if display_enabled and show_fps and annotated_frame is not None:
                new_frame_time = time.time()
                delta = new_frame_time - prev_frame_time
                fps = 1 / delta if delta > 0 else 0
                prev_frame_time = new_frame_time
                fps_y = 100 if show_speed else 20
                cv2.putText(
                    annotated_frame,
                    f"FPS: {int(fps)}",
                    (10, fps_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

            if win32api.GetAsyncKeyState(exit_hotkey_vk):
                logger.info("Exit hotkey pressed")
                break

            if display_enabled and annotated_frame is not None:
                height = int(source_frame.shape[0] * debug_window_scale_percent / 100)
                width = int(source_frame.shape[1] * debug_window_scale_percent / 100)
                dim = (width, height)
                if not _debug_window_exists(debug_window_name):
                    logger.info("Debug window closed externally, continuing without debug display")
                    display_enabled = False
                    continue

                try:
                    cv2.resizeWindow(debug_window_name, dim)
                    resized = cv2.resize(annotated_frame, dim, cv2.INTER_NEAREST)
                    cv2.imshow(debug_window_name, resized)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("Exit requested from debug window")
                        break
                except cv2.error:
                    logger.warning("Debug window became unavailable, continuing without debug display")
                    display_enabled = False

    except KeyboardInterrupt:
        logger.info("Aimbot interrupted by user")
    except Exception:
        logger.exception("Fatal runtime error")
    finally:
        if queue_worker is not None:
            queue_worker.stop()
            queue_worker.join(timeout=2)
        cleanup_capture()
        mouse_close()
        if show_window:
            cv2.destroyAllWindows()
        logger.info("Aimbot stopped cleanly")


if __name__ == "__main__":
    init()
