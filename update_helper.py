import os
import shutil


def apply_update(source_dir, target_dir, skip_names=None):
    skip_names = set(skip_names or [])
    os.makedirs(target_dir, exist_ok=True)
    for name in os.listdir(source_dir):
        if name in skip_names:
            continue
        source_path = os.path.join(source_dir, name)
        target_path = os.path.join(target_dir, name)
        if os.path.isdir(source_path):
            os.makedirs(target_path, exist_ok=True)
            apply_update(source_path, target_path, skip_names=None)
        else:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source_path, target_path)


if __name__ == '__main__':
    import sys
    apply_update(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
