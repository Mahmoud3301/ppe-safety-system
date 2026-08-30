"""
YOLOv8 Training Script for PPE Detection
=========================================
Trains a YOLOv8n model on the PPEs dataset using GPU,
then prints train, validation, and test accuracy (mAP50).
"""

import os
import torch
from ultralytics import YOLO

# ─── Configuration ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.join(BASE_DIR, "PPEs_balanced", "data.yaml")  # balanced dataset
MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")

EPOCHS = 100
IMG_SIZE = 640
BATCH_SIZE = 16
DEVICE = "0" if torch.cuda.is_available() else "cpu"
PROJECT_NAME = os.path.join(BASE_DIR, "runs")
EXPERIMENT_NAME = "ppe_detection"

# ─── Check GPU Availability ─────────────────────────────────────────────────────
if torch.cuda.is_available():
    print(f"✅ GPU detected: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    print("⚠️  No GPU detected — training will run on CPU (this will be very slow)")

# ─── Load Pretrained Model ──────────────────────────────────────────────────────
print(f"\n📦 Loading pretrained model: {MODEL_PATH}")
model = YOLO(MODEL_PATH)

# ─── Train the Model ────────────────────────────────────────────────────────────
print(f"\n🚀 Starting training for {EPOCHS} epochs on device: {DEVICE}")
print(f"   Dataset: {DATA_YAML}")
print(f"   Image size: {IMG_SIZE} | Batch size: {BATCH_SIZE}\n")

results = model.train(
    data=DATA_YAML,
    epochs=EPOCHS,
    imgsz=IMG_SIZE,
    batch=BATCH_SIZE,
    device=DEVICE,
    project=PROJECT_NAME,
    name=EXPERIMENT_NAME,
    exist_ok=True,
    pretrained=True,
    patience=20,        # early stopping patience
    save=True,
    save_period=10,     # save checkpoint every 10 epochs
    plots=True,
    verbose=True,
)

# ─── Path to Best Trained Weights ───────────────────────────────────────────────
best_weights = os.path.join(PROJECT_NAME, EXPERIMENT_NAME, "weights", "best.pt")
print(f"\n📁 Best weights saved at: {best_weights}")

# ─── Load Best Model for Evaluation ─────────────────────────────────────────────
best_model = YOLO(best_weights)

# ─── Evaluate on Validation Set ─────────────────────────────────────────────────
print("\n📊 Evaluating on VALIDATION set...")
val_metrics = best_model.val(
    data=DATA_YAML,
    split="val",
    device=DEVICE,
    verbose=False,
)
val_map50 = val_metrics.box.map50  # mAP at IoU=0.50

# ─── Evaluate on Train Set ──────────────────────────────────────────────────────
print("📊 Evaluating on TRAIN set...")
train_metrics = best_model.val(
    data=DATA_YAML,
    split="train",
    device=DEVICE,
    verbose=False,
)
train_map50 = train_metrics.box.map50

# ─── Evaluate on Test Set ───────────────────────────────────────────────────────
print("📊 Evaluating on TEST set...")
test_metrics = best_model.val(
    data=DATA_YAML,
    split="test",
    device=DEVICE,
    verbose=False,
)
test_map50 = test_metrics.box.map50

# ─── Print Final Summary ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("✅ TRAINING IS DONE!")
print("=" * 60)
print(f"   🏋️  Train Accuracy  (mAP50): {train_map50 * 100:.2f}%")
print(f"   📋 Validation Accuracy (mAP50): {val_map50 * 100:.2f}%")
print(f"   🧪 Test Accuracy  (mAP50): {test_map50 * 100:.2f}%")
print("=" * 60)
print(f"\n💾 Best model weights: {best_weights}")
print(f"📂 All results saved in: {os.path.join(PROJECT_NAME, EXPERIMENT_NAME)}")





