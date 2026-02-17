from options import (
    AI_conf,
    AI_image_size,
    AI_iou,
    AI_max_det,
    Dxcam_capture,
    Obs_capture,
    aim_hold_vk,
    body_y_offset,
    debug_window_scale_percent,
    detection_window_height,
    detection_window_width,
    dxcam_capture_fps,
    dxcam_max_buffer_len,
    exit_hotkey_vk,
    mouse_smoothing,
    native_Windows_capture,
)


def validate_runtime_options() -> None:
    errors: list[str] = []

    if detection_window_width <= 0 or detection_window_height <= 0:
        errors.append("detection_window_width and detection_window_height must be > 0")
    if mouse_smoothing <= 0:
        errors.append("mouse_smoothing must be > 0")
    if not 0 <= body_y_offset <= 1:
        errors.append("body_y_offset must be between 0 and 1")
    if AI_image_size <= 0:
        errors.append("AI_image_size must be > 0")
    if AI_max_det <= 0:
        errors.append("AI_max_det must be > 0")
    if not 0 <= AI_conf <= 1:
        errors.append("AI_conf must be between 0 and 1")
    if not 0 <= AI_iou <= 1:
        errors.append("AI_iou must be between 0 and 1")
    if dxcam_capture_fps <= 0:
        errors.append("dxcam_capture_fps must be > 0")
    if dxcam_max_buffer_len <= 0:
        errors.append("dxcam_max_buffer_len must be > 0")
    if not 1 <= debug_window_scale_percent <= 400:
        errors.append("debug_window_scale_percent must be in range [1, 400]")
    if not 1 <= aim_hold_vk <= 255:
        errors.append("aim_hold_vk must be in range [1, 255]")
    if not 1 <= exit_hotkey_vk <= 255:
        errors.append("exit_hotkey_vk must be in range [1, 255]")

    enabled_capture_methods = int(Dxcam_capture) + int(Obs_capture) + int(native_Windows_capture)
    if enabled_capture_methods != 1:
        errors.append("Exactly one capture method must be enabled")

    if errors:
        raise ValueError("Invalid options:\n- " + "\n- ".join(errors))
