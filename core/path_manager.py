import os
import sys
import platform

# Repository and folder name on mobile sdcard
REPO_FOLDER_NAME = "facebook-account-registration"


# Check if the current execution environment is Android / Termux
def is_termux_or_mobile():
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return True
    if os.path.exists("/sdcard"):
        return True
    if "ANDROID_ROOT" in os.environ:
        return True
    return False


# Get the base working directory for input and output files
def get_base_storage_dir():
    if is_termux_or_mobile():
        sdcard_path = "/sdcard"
        if os.path.exists(sdcard_path):
            target_dir = os.path.join(sdcard_path, REPO_FOLDER_NAME)
            try:
                os.makedirs(target_dir, exist_ok=True)
                return target_dir
            except Exception:
                pass
    return os.path.abspath(".")


# Get the primary directory path for output files
def get_output_dir():
    base_dir = get_base_storage_dir()
    out_dir = os.path.join(base_dir, "output")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        out_dir = os.path.join(".", "output")
        os.makedirs(out_dir, exist_ok=True)
    return out_dir


# Get list of paths where output should be written
def get_output_filepaths():
    paths = []
    # Primary storage path (sdcard on Termux, local on PC)
    primary_out = os.path.join(get_output_dir(), "success.txt")
    paths.append(primary_out)

    # If running on mobile, also write to local project output as a backup
    if is_termux_or_mobile():
        local_out = os.path.join(".", "output", "success.txt")
        local_abs = os.path.abspath(local_out)
        if os.path.abspath(primary_out) != local_abs:
            try:
                os.makedirs(os.path.dirname(local_abs), exist_ok=True)
                paths.append(local_abs)
            except Exception:
                pass
    return paths
