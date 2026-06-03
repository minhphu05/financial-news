"""Unified training script for all transformer-based NER models.

Supports training of:
- XLM-RoBERTa Base + CRF
- XLM-RoBERTa Large + CRF
- PhoBERT + CRF
- XLM-RoBERTa + BiLSTM + CRF
- XLM-RoBERTa + Multi-Head Attention + CRF
- XLM-RoBERTa + Adaptive Layer Fusion + CRF
- Focal-CRF + XLM-RoBERTa
- Dice Loss + XLM-RoBERTa

Usage:
    python train_advanced.py --model xlmr_bilstm_crf --epochs 30 --lr 3e-5
    python train_advanced.py --model xlmr_multihead_attn_crf --epochs 30
    python train_advanced.py --model focal_crf_xlmr --focal_gamma 2.0
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import classification_report, f1_score
from torch import nn, optim
from torch.utils.data import DataLoader
from tqdm import tqdm

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from DataUtils.xlmr_dataset import NERDataset
from model.XLM_R import XLMR_CRF
from model.XLMR_Large import XLMR_Large_CRF
from model.PhoBERT_CRF import PhoBERT_CRF
from model.XLMR_BiLSTM_CRF import XLMR_BiLSTM_CRF
from model.XLMR_MultiHead_Attn_CRF import XLMR_MultiHead_Attn_CRF
from model.XLMR_Adaptive_Fusion_CRF import XLMR_Adaptive_Fusion_CRF
from model.loss_models import DiceLoss_XLMR, FocalCRF_XLMR

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MODEL_REGISTRY: dict[str, type[nn.Module]] = {
    "xlmr_crf": XLMR_CRF,
    "xlmr_large_crf": XLMR_Large_CRF,
    "phobert_crf": PhoBERT_CRF,
    "xlmr_bilstm_crf": XLMR_BiLSTM_CRF,
    "xlmr_multihead_attn_crf": XLMR_MultiHead_Attn_CRF,
    "xlmr_adaptive_fusion_crf": XLMR_Adaptive_Fusion_CRF,
    "focal_crf_xlmr": FocalCRF_XLMR,
    "dice_loss_xlmr": DiceLoss_XLMR,
}

TOKENIZER_MAP: dict[str, str] = {
    "xlmr_crf": "xlm-roberta-base",
    "xlmr_large_crf": "xlm-roberta-large",
    "phobert_crf": "vinai/phobert-base-v2",
    "xlmr_bilstm_crf": "xlm-roberta-base",
    "xlmr_multihead_attn_crf": "xlm-roberta-base",
    "xlmr_adaptive_fusion_crf": "xlm-roberta-base",
    "focal_crf_xlmr": "xlm-roberta-base",
    "dice_loss_xlmr": "xlm-roberta-base",
}


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------
def read_jsonl(filepath: str) -> list[dict[str, Any]]:
    """Read JSONL file into a list of dictionaries.

    Args:
        filepath: Path to the JSONL file.

    Returns:
        List of parsed JSON objects.
    """
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def build_label_vocab(train_data: list[dict]) -> dict[str, int]:
    """Build label-to-ID mapping from training data.

    Args:
        train_data: List of training samples with 'tags' field.

    Returns:
        Dictionary mapping tag strings to integer IDs.
    """
    all_labels = set()
    for sample in train_data:
        all_labels.update(sample["tags"])
    return {label: idx for idx, label in enumerate(sorted(all_labels))}


def get_device() -> torch.device:
    """Detect the best available compute device.

    Returns:
        torch.device for CUDA, MPS, or CPU (in priority order).
    """
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def compute_class_weights(
    train_data: list[dict],
    label2id: dict[str, int],
    device: torch.device,
) -> torch.Tensor:
    """Compute inverse-frequency class weights for focal loss.

    Args:
        train_data: Training data samples.
        label2id: Label-to-ID mapping.
        device: Target device for the weight tensor.

    Returns:
        Normalized class weight tensor.
    """
    from collections import Counter

    tag_counter = Counter()
    for sample in train_data:
        for tag in sample["tags"]:
            tag_counter[tag] += 1

    num_classes = len(label2id)
    weights = torch.ones(num_classes, device=device)
    total = sum(tag_counter.values())

    for tag, idx in label2id.items():
        count = tag_counter.get(tag, 1)
        weights[idx] = total / (num_classes * count)

    # Normalize to sum to num_classes
    weights = weights / weights.sum() * num_classes
    return weights


# ---------------------------------------------------------------------------
# Training and Evaluation
# ---------------------------------------------------------------------------
def train_one_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: optim.Optimizer,
    device: torch.device,
    epoch: int,
    max_grad_norm: float = 1.0,
) -> float:
    """Train model for one epoch.

    Args:
        model: The NER model.
        dataloader: Training data loader.
        optimizer: Optimizer instance.
        device: Compute device.
        epoch: Current epoch number (for progress bar).
        max_grad_norm: Maximum gradient norm for clipping.

    Returns:
        Average training loss for the epoch.
    """
    model.train()
    total_loss = 0.0
    num_batches = 0

    progress = tqdm(dataloader, desc=f"Epoch {epoch:02d} [Train]")
    for batch in progress:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels = batch["labels"].to(device)

        optimizer.zero_grad()

        loss = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels,
        )

        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()

        total_loss += loss.item()
        num_batches += 1
        progress.set_postfix(loss=f"{total_loss / num_batches:.4f}")

    return total_loss / num_batches


def evaluate(
    model: nn.Module,
    dataloader: DataLoader,
    device: torch.device,
    id2label: dict[int, str] | None = None,
    print_report: bool = False,
) -> dict[str, float]:
    """Evaluate model on a dataset.

    Args:
        model: The NER model.
        dataloader: Evaluation data loader.
        device: Compute device.
        id2label: ID-to-label mapping for classification report.
        print_report: Whether to print per-class classification report.

    Returns:
        Dictionary with 'macro_f1', 'micro_f1', and 'weighted_f1' scores.
    """
    model.eval()
    all_true = []
    all_pred = []

    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Evaluating"):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            predictions = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
            )

            for pred_seq, label_seq, mask_seq in zip(
                predictions, labels, attention_mask
            ):
                valid_len = mask_seq.sum().item()
                label_arr = label_seq[:valid_len].cpu().numpy()
                pred_arr = np.array(pred_seq[:valid_len])

                # Filter out padding labels (-100)
                valid_mask = label_arr != -100
                all_true.extend(label_arr[valid_mask].tolist())
                all_pred.extend(pred_arr[valid_mask].tolist())

    results = {
        "macro_f1": f1_score(all_true, all_pred, average="macro", zero_division=0),
        "micro_f1": f1_score(all_true, all_pred, average="micro", zero_division=0),
        "weighted_f1": f1_score(all_true, all_pred, average="weighted", zero_division=0),
    }

    if print_report and id2label:
        unique_labels = sorted(set(all_true + all_pred))
        target_names = [id2label.get(i, f"TAG_{i}") for i in unique_labels]
        report = classification_report(
            all_true,
            all_pred,
            labels=unique_labels,
            target_names=target_names,
            zero_division=0,
        )
        logger.info(f"\nClassification Report:\n{report}")

    return results


# ---------------------------------------------------------------------------
# Model Builder
# ---------------------------------------------------------------------------
def build_model(
    model_name: str,
    num_tags: int,
    args: argparse.Namespace,
    class_weights: torch.Tensor | None = None,
) -> nn.Module:
    """Instantiate a model by name with appropriate hyperparameters.

    Args:
        model_name: Key in MODEL_REGISTRY.
        num_tags: Number of NER tag classes.
        args: Command-line arguments with model-specific params.
        class_weights: Class weights for focal loss models.

    Returns:
        Instantiated model.
    """
    if model_name == "xlmr_crf":
        return XLMR_CRF(num_tags=num_tags, dropout=args.dropout)
    elif model_name == "xlmr_large_crf":
        return XLMR_Large_CRF(num_tags=num_tags, dropout=args.dropout)
    elif model_name == "phobert_crf":
        return PhoBERT_CRF(num_tags=num_tags, dropout=args.dropout)
    elif model_name == "xlmr_bilstm_crf":
        return XLMR_BiLSTM_CRF(
            num_tags=num_tags,
            lstm_hidden_size=args.lstm_hidden_size,
            lstm_num_layers=args.lstm_num_layers,
            dropout=args.dropout,
        )
    elif model_name == "xlmr_multihead_attn_crf":
        return XLMR_MultiHead_Attn_CRF(
            num_tags=num_tags,
            num_attn_heads=args.num_attn_heads,
            attn_dropout=args.attn_dropout,
            classifier_dropout=args.dropout,
        )
    elif model_name == "xlmr_adaptive_fusion_crf":
        return XLMR_Adaptive_Fusion_CRF(
            num_tags=num_tags,
            dropout=args.dropout,
        )
    elif model_name == "focal_crf_xlmr":
        return FocalCRF_XLMR(
            num_tags=num_tags,
            focal_gamma=args.focal_gamma,
            focal_alpha=class_weights,
            crf_weight=args.crf_weight,
            dropout=args.dropout,
        )
    elif model_name == "dice_loss_xlmr":
        return DiceLoss_XLMR(
            num_tags=num_tags,
            crf_weight=args.crf_weight,
            dropout=args.dropout,
        )
    else:
        raise ValueError(f"Unknown model: {model_name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Train advanced NER models for Vietnamese Financial NER"
    )

    # Data paths
    parser.add_argument(
        "--data_dir",
        type=str,
        default="../../data/labeled/ner/syllables",
        help="Directory containing train/dev/test JSONL files",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="../../outputs",
        help="Directory to save model checkpoints and logs",
    )

    # Model selection
    parser.add_argument(
        "--model",
        type=str,
        default="xlmr_bilstm_crf",
        choices=list(MODEL_REGISTRY.keys()),
        help="Model architecture to train",
    )

    # Training hyperparameters
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--max_len", type=int, default=128)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--max_grad_norm", type=float, default=1.0)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)

    # Model-specific hyperparameters
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lstm_hidden_size", type=int, default=256)
    parser.add_argument("--lstm_num_layers", type=int, default=1)
    parser.add_argument("--num_attn_heads", type=int, default=8)
    parser.add_argument("--attn_dropout", type=float, default=0.1)
    parser.add_argument("--focal_gamma", type=float, default=2.0)
    parser.add_argument("--crf_weight", type=float, default=0.5)

    # Misc
    parser.add_argument("--seed", type=int, default=42)

    return parser.parse_args()


def set_seed(seed: int) -> None:
    """Set random seeds for reproducibility."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def main() -> None:
    """Main training loop."""
    args = parse_args()
    set_seed(args.seed)

    device = get_device()
    logger.info(f"Device: {device}")
    logger.info(f"Model: {args.model}")

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / args.model / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save args
    with open(run_dir / "args.json", "w") as f:
        json.dump(vars(args), f, indent=2)

    # Load data
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = Path(ROOT_DIR) / data_dir

    train_path = data_dir / "final_train_vifinner.jsonl"
    dev_path = data_dir / "final_dev_vifinner.jsonl"
    test_path = data_dir / "final_test_vifinner.jsonl"

    # Fallback to non-final versions
    if not train_path.exists():
        train_path = data_dir / "train_vifinner.jsonl"
        dev_path = data_dir / "dev_vifinner.jsonl"
        test_path = data_dir / "test_vifinner.jsonl"

    logger.info(f"Loading data from: {data_dir}")
    train_data = read_jsonl(str(train_path))
    dev_data = read_jsonl(str(dev_path))
    test_data = read_jsonl(str(test_path))

    logger.info(f"Train: {len(train_data)} | Dev: {len(dev_data)} | Test: {len(test_data)}")

    # Build label vocab
    label2id = build_label_vocab(train_data)
    id2label = {v: k for k, v in label2id.items()}
    num_tags = len(label2id)

    logger.info(f"Number of tags: {num_tags}")
    logger.info(f"Labels: {label2id}")

    # Save label mapping
    with open(run_dir / "label2id.json", "w") as f:
        json.dump(label2id, f, indent=2)

    # Build datasets
    tokenizer_name = TOKENIZER_MAP[args.model]
    train_dataset = NERDataset(train_data, label2id, max_len=args.max_len)
    dev_dataset = NERDataset(dev_data, label2id, max_len=args.max_len)
    test_dataset = NERDataset(test_data, label2id, max_len=args.max_len)

    # Override tokenizer if needed
    if tokenizer_name != "xlm-roberta-base":
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        train_dataset.tokenizer = tokenizer
        dev_dataset.tokenizer = tokenizer
        test_dataset.tokenizer = tokenizer

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    dev_loader = DataLoader(dev_dataset, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    # Compute class weights (for focal loss)
    class_weights = None
    if args.model in ("focal_crf_xlmr",):
        class_weights = compute_class_weights(train_data, label2id, device)
        logger.info(f"Class weights: {class_weights}")

    # Build model
    model = build_model(args.model, num_tags, args, class_weights)
    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Total parameters: {total_params:,}")
    logger.info(f"Trainable parameters: {trainable_params:,}")

    # Optimizer with weight decay
    no_decay = ["bias", "LayerNorm.weight", "layer_norm.weight"]
    optimizer_grouped_params = [
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if not any(nd in n for nd in no_decay) and p.requires_grad
            ],
            "weight_decay": args.weight_decay,
        },
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if any(nd in n for nd in no_decay) and p.requires_grad
            ],
            "weight_decay": 0.0,
        },
    ]
    optimizer = optim.AdamW(optimizer_grouped_params, lr=args.lr)

    # Learning rate scheduler with warmup
    total_steps = len(train_loader) * args.epochs
    warmup_steps = int(total_steps * args.warmup_ratio)

    scheduler = optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=args.lr,
        total_steps=total_steps,
        pct_start=args.warmup_ratio,
        anneal_strategy="cos",
    )

    # Training loop
    best_f1 = 0.0
    patience_counter = 0
    history = []

    logger.info("Starting training...")

    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(
            model, train_loader, optimizer, device, epoch, args.max_grad_norm
        )

        dev_results = evaluate(model, dev_loader, device)
        dev_f1 = dev_results["macro_f1"]

        # Log metrics
        epoch_log = {
            "epoch": epoch,
            "train_loss": train_loss,
            "dev_macro_f1": dev_results["macro_f1"],
            "dev_micro_f1": dev_results["micro_f1"],
            "dev_weighted_f1": dev_results["weighted_f1"],
            "lr": optimizer.param_groups[0]["lr"],
        }
        history.append(epoch_log)

        logger.info(
            f"Epoch {epoch:02d} | Loss: {train_loss:.4f} | "
            f"Dev F1: {dev_f1:.4f} (macro) | "
            f"LR: {optimizer.param_groups[0]['lr']:.2e}"
        )

        # Early stopping
        if dev_f1 > best_f1:
            best_f1 = dev_f1
            patience_counter = 0
            torch.save(model.state_dict(), run_dir / "best_model.pt")
            logger.info(f"  -> New best model saved (F1={best_f1:.4f})")
        else:
            patience_counter += 1
            logger.info(f"  -> No improvement ({patience_counter}/{args.patience})")

        if patience_counter >= args.patience:
            logger.info("Early stopping triggered.")
            break

    # Final evaluation on test set
    logger.info("\nLoading best model for final test evaluation...")
    model.load_state_dict(torch.load(run_dir / "best_model.pt", weights_only=True))

    test_results = evaluate(
        model, test_loader, device, id2label=id2label, print_report=True
    )

    logger.info(f"\nFinal Test Results:")
    logger.info(f"  Macro F1:    {test_results['macro_f1']:.4f}")
    logger.info(f"  Micro F1:    {test_results['micro_f1']:.4f}")
    logger.info(f"  Weighted F1: {test_results['weighted_f1']:.4f}")

    # Save training history and final results
    final_results = {
        "model": args.model,
        "best_dev_f1": best_f1,
        "test_results": test_results,
        "total_epochs": epoch,
        "history": history,
    }

    with open(run_dir / "results.json", "w") as f:
        json.dump(final_results, f, indent=2)

    logger.info(f"\nAll artifacts saved to: {run_dir}")


if __name__ == "__main__":
    main()
