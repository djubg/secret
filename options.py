# Detection window resolution. In its current form, this is 20% of the screen resolution.
detection_window_width = 384
detection_window_height = 216 

# Dxcam Capture method
Dxcam_capture = True
dxcam_capture_fps = 60 # 30 fps is OK
dxcam_monitor_id = 0
dxcam_gpu_id = 0
dxcam_max_buffer_len = 64

# Obs capture method
Obs_capture = False
Obs_camera_id = 1
Obs_capture_fps = 30 # 30 fps is OK

# Windows capture method
native_Windows_capture = False

# Aim settings
body_y_offset = 0.24
hideout_targets = True
disable_headshot = False

# Mouse settings 
mouse_smoothing = 2.8
mouse_auto_shoot = True
mouse_auto_aim = True
mouse_native = True
mouse_wild_mouse = True

# AI options
AI_model_path = 'models/best.onnx'# You can find new improved models here https://boosty.to/sunone
AI_image_size = 320
AI_conf = 0.35
AI_iou = 0.1
AI_device = "cpu"
AI_max_det = 10

# Cv2 debug window settings
show_window = True
show_speed = False
show_fps = True
show_boxes = True
show_labels = True
show_conf = True
debug_window_scale_percent = 100
debug_window_name = 'YOLOv8 Debug'

# Input hotkeys (Win32 virtual-key codes)
aim_hold_vk = 0x02     # Right mouse button
exit_hotkey_vk = 0x71  # F2

# Native windows capture target. Leave both as None for desktop capture.
capture_window_class_name = None
capture_window_name = None

# DLL driver settings
ghub_dll_path = 'ghub_mouse.dll'
# Optional SHA-256 checksum. Leave empty to skip strict checksum validation.
ghub_dll_sha256 = ''

# Logging
log_file_path = 'logs/yolov8_aimbot.log'
log_level = 'INFO'
