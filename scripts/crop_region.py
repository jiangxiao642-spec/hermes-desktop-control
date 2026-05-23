"""Crop a 200x200 region from a screenshot centered on given coordinates.

Usage: python3 crop_region.py <input_path> <x> <y> [--size 200] [--output <path>]

Output: cropped PNG path, printed to stdout.
"""

import sys
import os
from PIL import Image


def crop_region(image_path: str, x: int, y: int, size: int = 200,
                output_path: str = None) -> str:
    img = Image.open(image_path)
    half = size // 2
    left = max(0, x - half)
    top = max(0, y - half)
    right = min(img.width, left + size)
    bottom = min(img.height, top + size)
    cropped = img.crop((left, top, right, bottom))
    if output_path is None:
        base, ext = os.path.splitext(image_path)
        output_path = f"{base}_crop_{x}_{y}.png"
    cropped.save(output_path)
    return output_path


def main():
    if len(sys.argv) < 3:
        print("Usage: crop_region.py <image> <x> <y> [--size 200] [--output path]", file=sys.stderr)
        sys.exit(1)
    image_path = sys.argv[1]
    x = int(sys.argv[2])
    y = int(sys.argv[3])
    size = 200
    output_path = None
    args = sys.argv[4:]
    while args:
        if args[0] == "--size" and len(args) > 1:
            size = int(args[1])
            args = args[2:]
        elif args[0] == "--output" and len(args) > 1:
            output_path = args[1]
            args = args[2:]
        else:
            args = args[1:]
    result = crop_region(image_path, x, y, size, output_path)
    print(result)


if __name__ == "__main__":
    main()
