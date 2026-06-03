import os, sys
from os import path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
import torch
import numpy as np
import logging
from torch.utils.data import DataLoader
from torch import optim
from sklearn.metrics import f1_score
from tqdm import tqdm

from DataUtils.xlmr_dataset import NERDataset

from DataUtils.NER_dataset import Vocab
from model.XLM_R import XLMR_CRF

# =====================
# SETUP
# =====================
logging.basicConfig(level=logging.INFO, format="%(message)s")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


import os
import logging
import numpy as np
from tqdm import tqdm
import torch
from torch import optim
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score

from transformers import AutoTokenizer

# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# logging.basicConfig(level=logging.INFO)

# Hàm train 1 epoch (giữ nguyên)
def train_one_epoch(model, dataloader, optimizer, epoch):
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


# Hàm evaluate (sửa lại để mask đúng)
def evaluate(model, dataloader):
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
            )  # list of list of tag ids (batch)

            # Lặp qua batch
            for pred_seq, label_seq, mask_seq in zip(preds, labels, attention_mask):
                valid_len = mask_seq.sum().item()
                # Lọc chỉ token không phải padding và không phải label -100
                label_seq = label_seq[:valid_len].cpu().numpy()
                pred_seq = pred_seq[:valid_len]

                mask_label = label_seq != -100
                y_true.extend(label_seq[mask_label])
                y_pred.extend(np.array(pred_seq)[mask_label])

    f1 = f1_score(y_true, y_pred, average="macro")
    return f1


def read_jsonl(path):
    import json
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    return data


if __name__ == "__main__":

    # ----- Đường dẫn data bạn chỉnh lại theo đúng máy bạn -----
    data_dir = "/Users/kittnguyen/Documents/DS201_Finance/data/labeled/ner/syllables"
    output_dir = "/Users/kittnguyen/Documents/DS201_Finance/model_result"
    os.makedirs(output_dir, exist_ok=True)

    train_path = os.path.join(data_dir, "train_vifinner.jsonl")
    dev_path   = os.path.join(data_dir, "dev_vifinner.jsonl")
    test_path  = os.path.join(data_dir, "test_vifinner.jsonl")

    best_model_path = os.path.join(output_dir, "xlmr_crf_best.pt")

    logging.info(f"Device: {device}")

    # ----- Load data -----
    logging.info("Loading datasets ...")
    train_data = read_jsonl(train_path)
    dev_data = read_jsonl(dev_path)
    test_data = read_jsonl(test_path)

    # ----- Build label vocab từ tập train -----
    all_labels = set()
    for sample in train_data:
        all_labels.update(sample["tags"])
    label2id = {label: i for i, label in enumerate(sorted(all_labels))}
    num_tags = len(label2id)

    logging.info(f"Number of tags: {num_tags}")
    logging.info(f"Label2ID: {label2id}")

    # ----- Dataset và DataLoader -----
    train_dataset = NERDataset(train_data, label2id, max_len=128)
    dev_dataset = NERDataset(dev_data, label2id, max_len=128)
    test_dataset = NERDataset(test_data, label2id, max_len=128)

    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    dev_loader = DataLoader(dev_dataset, batch_size=16, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False)

    # ----- Model -----
    logging.info("Building XLM-RoBERTa Large + CRF model ...")
    model = XLMR_CRF(num_tags=num_tags).to(device)

    optimizer = optim.AdamW(model.parameters(), lr=3e-5)

    # ----- Train loop -----
    best_f1 = 0.0
    patience = 0
    patience_limit = 5
    epoch = 0
    max_epoch = 30

    logging.info("Start training ...")

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

    # ----- Test -----
    logging.info("Evaluating best model on TEST set ...")
    model.load_state_dict(torch.load(best_model_path))
    test_f1 = evaluate(model, test_loader)
    logging.info(f"Final TEST F1: {test_f1:.4f}")
