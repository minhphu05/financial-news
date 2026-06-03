"""
Training script for XLM-RoBERTa + CRF NER model.

Trains an XLM-RoBERTa Base encoder with CRF decoder on Vietnamese financial NER data.
Uses early stopping based on macro F1 score on the development set.

Usage:
    python train_xlmr_crf.py
"""

import os
import sys
import json
import logging
import numpy as np
from tqdm import tqdm
from os import path

import torch
from torch import optim
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)

from DataUtils.xlmr_dataset import NERDataset
from DataUtils.NER_dataset import Vocab
from model.XLM_R import XLMR_CRF

# Setup
logging.basicConfig(level=logging.INFO, format="%(message)s")
device = torch.device("mps" if torch.mps.is_available() else "cpu")


def train_one_epoch(model, dataloader, optimizer, epoch):
    """Train the model for one epoch.

    Args:
        model: XLMR_CRF model instance.
        dataloader: Training DataLoader.
        optimizer: Optimizer instance.
        epoch: Current epoch number (for display).

    Returns:
        Average training loss for the epoch.
    """
    model.train()
    losses = []

    for batch in tqdm(dataloader, desc=f"Epoch {epoch} - Train"):
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels = batch["labels"].to(device)

        optimizer.zero_grad()
        loss = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels
        )
        loss.backward()
        optimizer.step()

        losses.append(loss.item())

    return sum(losses) / len(losses)


def evaluate(model, dataloader):
    """Evaluate the model on a dataset.

    Masks out padding tokens and special tokens (label=-100) before
    computing macro F1 score.

    Args:
        model: XLMR_CRF model instance.
        dataloader: Evaluation DataLoader.

    Returns:
        Macro F1 score on the evaluation set.
    """
    model.eval()
    y_true, y_pred = [], []

    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Evaluate"):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            preds = model(
                input_ids=input_ids,
                attention_mask=attention_mask
            )

            for pred_seq, label_seq, mask_seq in zip(preds, labels, attention_mask):
                valid_len = mask_seq.sum().item()
                # Filter only non-padding, non-special tokens
                label_seq = label_seq[:valid_len].cpu().numpy()
                pred_seq = pred_seq[:valid_len]

                mask_label = label_seq != -100
                y_true.extend(label_seq[mask_label])
                y_pred.extend(np.array(pred_seq)[mask_label])

    f1 = f1_score(y_true, y_pred, average="macro")
    return f1


def read_jsonl(filepath: str) -> list[dict]:
    """Read a JSONL file and return a list of records.

    Args:
        filepath: Path to the JSONL file.

    Returns:
        List of dictionaries parsed from the file.
    """
    data = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    return data


if __name__ == "__main__":

    # Data paths (adjust to your environment)
    data_dir = "/Users/kittnguyen/Documents/DS201_Finance/data/labeled/ner/syllables"
    output_dir = "/Users/kittnguyen/Documents/DS201_Finance/model_result"
    os.makedirs(output_dir, exist_ok=True)

    train_path = os.path.join(data_dir, "train_vifinner.jsonl")
    dev_path = os.path.join(data_dir, "dev_vifinner.jsonl")
    test_path = os.path.join(data_dir, "test_vifinner.jsonl")

    best_model_path = os.path.join(output_dir, "xlmr_crf_best.pt")

    logging.info(f"Device: {device}")

    # Load data
    logging.info("Loading datasets ...")
    train_data = read_jsonl(train_path)
    dev_data = read_jsonl(dev_path)
    test_data = read_jsonl(test_path)

    # Build label vocabulary from training set
    all_labels = set()
    for sample in train_data:
        all_labels.update(sample["tags"])
    label2id = {label: i for i, label in enumerate(sorted(all_labels))}
    num_tags = len(label2id)

    logging.info(f"Number of tags: {num_tags}")
    logging.info(f"Label2ID: {label2id}")

    # Dataset and DataLoader
    train_dataset = NERDataset(train_data, label2id, max_len=128)
    dev_dataset = NERDataset(dev_data, label2id, max_len=128)
    test_dataset = NERDataset(test_data, label2id, max_len=128)

    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    dev_loader = DataLoader(dev_dataset, batch_size=16, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False)

    # Build model
    logging.info("Building XLM-RoBERTa + CRF model ...")
    model = XLMR_CRF(num_tags=num_tags).to(device)

    optimizer = optim.AdamW(model.parameters(), lr=3e-5)

    # Training loop with early stopping
    best_f1 = 0.0
    patience = 0
    patience_limit = 5
    epoch = 0
    max_epoch = 30

    logging.info("Starting training ...")

    while True:
        epoch += 1

        train_loss = train_one_epoch(model, train_loader, optimizer, epoch)
        f1 = evaluate(model, dev_loader)

        logging.info(f"Epoch {epoch} | Train loss: {train_loss:.4f} | Dev F1: {f1:.4f}")

        if f1 > best_f1:
            best_f1 = f1
            patience = 0
            torch.save(model.state_dict(), best_model_path)
            logging.info(f"New best model saved (F1={best_f1:.4f})")
        else:
            patience += 1
            logging.info(f"No improvement ({patience}/{patience_limit})")

        if patience >= patience_limit or epoch >= max_epoch:
            logging.info("Early stopping.")
            break

    # Final evaluation on test set
    logging.info("Evaluating best model on TEST set ...")
    model.load_state_dict(torch.load(best_model_path))
    test_f1 = evaluate(model, test_loader)
    logging.info(f"Final TEST F1: {test_f1:.4f}")
