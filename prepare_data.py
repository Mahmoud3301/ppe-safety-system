"""
Data Preparation Script for PPE Dataset
========================================
1. Merges all splits (train/valid/test) into one pool
2. Re-splits with stratified sampling so every class appears in every split
3. Augments underrepresented classes to balance the dataset
"""

import os
import shutil
import random
import yaml
from pathlib import Path
from collections import defaultdict, Counter
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

random.seed(42)
np.random.seed(42)

# ─── Configuration ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "PPEs.v8-allclasses-roboflow-fast-model.yolov8"
OUTPUT_DIR = BASE_DIR / "PPEs_balanced"  # new balanced dataset

SPLIT_RATIOS = {"train": 0.70, "valid": 0.20, "test": 0.10}

# Target: augment rare classes so they have at least this many annotations
MIN_ANNOTATIONS_TARGET = 1500

CLASS_NAMES = [
    "glove", "goggles", "helmet", "mask", "no-suit", "no_glove",
    "no_goggles", "no_helmet", "no_mask", "no_shoes", "shoes", "suit"
]


# ─── Step 1: Collect all images and labels ──────────────────────────────────────
def collect_all_samples():
    """Merge train/valid/test into a single pool of (image_path, label_path) pairs."""
    samples = []
    splits = ["train", "valid", "test"]

    for split in splits:
        img_dir = DATASET_DIR / split / "images"
        lbl_dir = DATASET_DIR / split / "labels"

        if not img_dir.exists():
            continue

        for img_file in sorted(img_dir.iterdir()):
            if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                # Find matching label
                lbl_file = lbl_dir / (img_file.stem + ".txt")
                if lbl_file.exists():
                    samples.append((img_file, lbl_file))

    print(f"📦 Total samples collected: {len(samples)}")
    return samples


# ─── Step 2: Analyze class distribution per image ──────────────────────────────
def get_image_classes(label_path):
    """Return set of class IDs present in a label file."""
    classes = set()
    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if parts:
                classes.add(int(parts[0]))
    return classes


def analyze_distribution(samples):
    """Count annotations per class across all samples."""
    class_counts = Counter()
    for _, lbl_path in samples:
        with open(lbl_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    class_counts[int(parts[0])] += 1
    return class_counts


# ─── Step 3: Stratified Split ───────────────────────────────────────────────────
def stratified_split(samples):
    """
    Split samples ensuring every class appears in every split.
    Uses the 'primary class' (rarest class in an image) for stratification.
    """
    # Get global class counts to know which classes are rare
    global_counts = analyze_distribution(samples)
    print("\n📊 Class distribution BEFORE re-split:")
    for cls_id in sorted(global_counts.keys()):
        name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
        print(f"   {cls_id:2d} ({name:12s}): {global_counts[cls_id]:,}")

    # Group images by their rarest class (for stratification)
    class_to_images = defaultdict(list)
    for img_path, lbl_path in samples:
        classes = get_image_classes(lbl_path)
        if not classes:
            continue
        # Assign to the rarest class for stratification purposes
        rarest = min(classes, key=lambda c: global_counts.get(c, 0))
        class_to_images[rarest].append((img_path, lbl_path))

    # Split each group proportionally
    splits = {"train": [], "valid": [], "test": []}

    for cls_id in sorted(class_to_images.keys()):
        group = class_to_images[cls_id]
        random.shuffle(group)

        n = len(group)
        n_train = max(1, int(n * SPLIT_RATIOS["train"]))
        n_valid = max(1, int(n * SPLIT_RATIOS["valid"]))
        # Ensure at least 1 in each split
        if n >= 3:
            n_test = n - n_train - n_valid
            if n_test < 1:
                n_train -= 1
                n_test = 1
        else:
            # Very few samples: put 1 in each
            n_train = max(1, n - 2)
            n_valid = 1 if n > 1 else 0
            n_test = 1 if n > 2 else 0

        splits["train"].extend(group[:n_train])
        splits["valid"].extend(group[n_train:n_train + n_valid])
        splits["test"].extend(group[n_train + n_valid:])

    for split_name, split_data in splits.items():
        print(f"   {split_name}: {len(split_data):,} images")

    return splits


# ─── Step 4: Augmentation Functions ─────────────────────────────────────────────
def augment_image(img, aug_type):
    """Apply a specific augmentation to a PIL Image."""
    if aug_type == "hflip":
        return img.transpose(Image.FLIP_LEFT_RIGHT)
    elif aug_type == "vflip":
        return img.transpose(Image.FLIP_TOP_BOTTOM)
    elif aug_type == "rotate90":
        return img.transpose(Image.ROTATE_90)
    elif aug_type == "rotate270":
        return img.transpose(Image.ROTATE_270)
    elif aug_type == "brightness_up":
        return ImageEnhance.Brightness(img).enhance(1.3)
    elif aug_type == "brightness_down":
        return ImageEnhance.Brightness(img).enhance(0.7)
    elif aug_type == "contrast":
        return ImageEnhance.Contrast(img).enhance(1.4)
    elif aug_type == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=1.5))
    elif aug_type == "sharpen":
        return ImageEnhance.Sharpness(img).enhance(2.0)
    elif aug_type == "color":
        return ImageEnhance.Color(img).enhance(1.3)
    return img


def augment_label(label_lines, aug_type, img_w, img_h):
    """Adjust YOLO label coordinates for geometric augmentations."""
    new_lines = []
    for line in label_lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls_id = parts[0]
        x_c, y_c, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])

        if aug_type == "hflip":
            x_c = 1.0 - x_c
        elif aug_type == "vflip":
            y_c = 1.0 - y_c
        elif aug_type == "rotate90":
            x_c, y_c = y_c, 1.0 - x_c
            w, h = h, w
        elif aug_type == "rotate270":
            x_c, y_c = 1.0 - y_c, x_c
            w, h = h, w
        # brightness/contrast/blur/sharpen/color don't change coordinates

        new_lines.append(f"{cls_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")
    return new_lines


# ─── Step 5: Copy files and augment ─────────────────────────────────────────────
def copy_split(split_name, samples, output_dir):
    """Copy images and labels to the new split directory."""
    img_out = output_dir / split_name / "images"
    lbl_out = output_dir / split_name / "labels"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    for img_path, lbl_path in samples:
        shutil.copy2(img_path, img_out / img_path.name)
        shutil.copy2(lbl_path, lbl_out / lbl_path.name)


def augment_rare_classes(train_dir, class_counts):
    """
    Augment images containing rare classes in the TRAIN split
    to reach MIN_ANNOTATIONS_TARGET annotations per class.
    """
    img_dir = train_dir / "images"
    lbl_dir = train_dir / "labels"

    aug_types = [
        "hflip", "vflip", "brightness_up", "brightness_down",
        "contrast", "blur", "sharpen", "color"
    ]

    # Find which classes need augmentation
    rare_classes = {}
    for cls_id, count in class_counts.items():
        if count < MIN_ANNOTATIONS_TARGET:
            rare_classes[cls_id] = count
            name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
            print(f"   🔄 {name} ({count:,} → target {MIN_ANNOTATIONS_TARGET:,})")

    if not rare_classes:
        print("   ✅ All classes already have enough annotations!")
        return

    # Collect train images containing rare classes
    rare_images = defaultdict(list)  # cls_id -> list of (img_path, lbl_path)
    for lbl_file in sorted(lbl_dir.iterdir()):
        if lbl_file.suffix != ".txt":
            continue
        with open(lbl_file, "r") as f:
            lines = f.readlines()
        classes_in_image = set()
        for line in lines:
            parts = line.strip().split()
            if parts:
                classes_in_image.add(int(parts[0]))

        for cls_id in classes_in_image:
            if cls_id in rare_classes:
                img_name = lbl_file.stem
                # Find matching image
                for ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
                    img_file = img_dir / (img_name + ext)
                    if img_file.exists():
                        rare_images[cls_id].append((img_file, lbl_file, lines))
                        break

    total_augmented = 0

    for cls_id, current_count in rare_classes.items():
        images_for_cls = rare_images.get(cls_id, [])
        if not images_for_cls:
            name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
            print(f"   ⚠️  No train images for {name} — cannot augment!")
            continue

        # How many more annotations do we need?
        needed = MIN_ANNOTATIONS_TARGET - current_count
        # Count annotations per image for this class
        annots_per_img = []
        for _, _, lines in images_for_cls:
            count = sum(1 for l in lines if l.strip().split() and int(l.strip().split()[0]) == cls_id)
            annots_per_img.append(count)
        avg_annots = max(1, sum(annots_per_img) / len(annots_per_img))

        # How many augmented images do we need?
        n_aug_images = int(np.ceil(needed / avg_annots))

        aug_idx = 0
        for i in range(n_aug_images):
            # Pick source image (cycle through available ones)
            src_img, src_lbl, src_lines = images_for_cls[i % len(images_for_cls)]
            aug_type = aug_types[aug_idx % len(aug_types)]
            aug_idx += 1

            # Generate augmented image
            try:
                img = Image.open(src_img).convert("RGB")
                aug_img = augment_image(img, aug_type)

                # Generate unique name
                aug_name = f"aug_{cls_id}_{i}_{aug_type}_{src_img.stem}"
                aug_img_path = img_dir / (aug_name + src_img.suffix)
                aug_lbl_path = lbl_dir / (aug_name + ".txt")

                # Save augmented image
                aug_img.save(aug_img_path, quality=95)

                # Save adjusted labels
                new_lines = augment_label(src_lines, aug_type, img.width, img.height)
                with open(aug_lbl_path, "w") as f:
                    f.writelines(new_lines)

                total_augmented += 1
            except Exception as e:
                print(f"   ⚠️  Error augmenting {src_img.name}: {e}")
                continue

    print(f"\n   ✅ Created {total_augmented:,} augmented images total")


# ─── Step 6: Create new data.yaml ──────────────────────────────────────────────
def create_data_yaml(output_dir):
    """Create a new data.yaml for the balanced dataset."""
    data = {
        "train": "../train/images",
        "val": "../valid/images",
        "test": "../test/images",
        "nc": len(CLASS_NAMES),
        "names": CLASS_NAMES,
    }
    yaml_path = output_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"\n📄 Created: {yaml_path}")


# ─── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🔧 PPE Dataset Balancing & Re-splitting")
    print("=" * 60)

    # Step 1: Collect
    samples = collect_all_samples()

    # Step 2: Stratified split
    print("\n🔀 Performing stratified re-split...")
    splits = stratified_split(samples)

    # Step 3: Create output directory
    if OUTPUT_DIR.exists():
        print(f"\n🗑️  Removing old output: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)

    # Step 4: Copy files
    print("\n📁 Copying files to new splits...")
    for split_name, split_samples in splits.items():
        copy_split(split_name, split_samples, OUTPUT_DIR)
        print(f"   ✅ {split_name}: {len(split_samples):,} images copied")

    # Step 5: Count train class distribution BEFORE augmentation
    print("\n📊 Train class distribution BEFORE augmentation:")
    train_counts = analyze_distribution(
        [(OUTPUT_DIR / "train" / "images" / p.name, OUTPUT_DIR / "train" / "labels" / l.name)
         for p, l in splits["train"]]
    )
    for cls_id in range(len(CLASS_NAMES)):
        count = train_counts.get(cls_id, 0)
        print(f"   {cls_id:2d} ({CLASS_NAMES[cls_id]:12s}): {count:,}")

    # Step 6: Augment rare classes
    print(f"\n🔄 Augmenting rare classes (target: {MIN_ANNOTATIONS_TARGET:,} annotations each)...")
    augment_rare_classes(OUTPUT_DIR / "train", train_counts)

    # Step 7: Final distribution
    print("\n📊 Train class distribution AFTER augmentation:")
    final_train_dir = OUTPUT_DIR / "train"
    final_counts = Counter()
    for lbl_file in sorted((final_train_dir / "labels").iterdir()):
        if lbl_file.suffix == ".txt":
            with open(lbl_file, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        final_counts[int(parts[0])] += 1
    for cls_id in range(len(CLASS_NAMES)):
        count = final_counts.get(cls_id, 0)
        print(f"   {cls_id:2d} ({CLASS_NAMES[cls_id]:12s}): {count:,}")

    # Step 8: Count all splits
    print("\n📊 Final split sizes:")
    for split in ["train", "valid", "test"]:
        img_count = len(list((OUTPUT_DIR / split / "images").iterdir()))
        print(f"   {split}: {img_count:,} images")

    # Step 9: Create data.yaml
    create_data_yaml(OUTPUT_DIR)

    print("\n" + "=" * 60)
    print("✅ DONE! Use the new dataset for training:")
    print(f"   data: {OUTPUT_DIR / 'data.yaml'}")
    print("=" * 60)
