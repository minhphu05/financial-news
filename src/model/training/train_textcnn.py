import os
import sys
import yaml
import torch
import numpy as np
from torch.utils.data import DataLoader
from torch import nn, optim
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report
from tqdm import tqdm
import logging
from os import path

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)

from DataUtils.NER_dataset import phoNERT, Vocab, collate_fn
from model.TextCNN import TextCNN_NER

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
device = torch.device("mps" if torch.mps.is_available() else "cpu")

# TextCNN Config
with open("../config/TextCNN.yaml") as f:
    config = yaml.safe_load(f)

def train(model: nn.Module, 
          data: DataLoader, 
          epoch: int, 
          loss_fn: nn.Module, 
          optimizer: optim.Optimizer) -> float:

    model.train()
    running_loss = []
    pbar = tqdm(data, desc=f"Epoch {epoch} - Training")

    for batch in pbar:
        input_ids = batch["input_ids"].to(device)
        tags_ids = batch["tags_ids"].to(device) 
        lengths = batch["lengths"] 

        optimizer.zero_grad()
        
        # Forward pass
        logits = model(input_ids, lengths) 

        # Flatten output và labels để tính Loss
        # Logits: [Batch * Seq, Num_Tags]
        # Labels: [Batch * Seq]
        loss = loss_fn(logits.view(-1, logits.shape[-1]), tags_ids.view(-1))

        loss.backward()
        optimizer.step()

        running_loss.append(loss.item())
        pbar.set_postfix({"loss": sum(running_loss)/len(running_loss)})
    
    return sum(running_loss)/len(running_loss)

def evaluate(model: nn.Module, data: DataLoader, epoch: int) -> float:
    model.eval()
    true_labels = []
    predictions = []

    pbar = tqdm(data, desc=f"Epoch {epoch} - Evaluation")
    
    with torch.no_grad():
        for batch in pbar:
            input_ids = batch["input_ids"].to(device)
            tags_ids = batch["tags_ids"].to(device)
            lengths = batch["lengths"]

            logits = model(input_ids, lengths)
            predicted_tags = torch.argmax(logits, dim=-1)

            # Lọc bỏ padding (-100) để tính điểm chính xác
            mask = tags_ids != -100
            
            valid_tags = tags_ids[mask].cpu().numpy()
            valid_preds = predicted_tags[mask].cpu().numpy()

            true_labels.extend(valid_tags)
            predictions.extend(valid_preds)
            
    # Tính toán Metrics
    precision = precision_score(true_labels, predictions, average='macro', zero_division=0)
    recall = recall_score(true_labels, predictions, average='macro', zero_division=0)
    f1 = f1_score(true_labels, predictions, average='macro', zero_division=0)

    logging.info(f"Precision: {precision:.4f}")
    logging.info(f"Recall: {recall:.4f}")
    logging.info(f"F1 Score: {f1:.4f}")
    logging.info("----------------------------------")

    # Thêm bước in Báo cáo Phân loại Chi tiết
    logging.info("--- Detailed Classification Report ---")
    
    # Cần tạo danh sách tên nhãn (tag names)
    # Giả sử self.idx2tag của Vocab chứa mapping đúng.
    # Lấy các index có trong kết quả và map ngược lại
    unique_labels = np.unique(true_labels)
    # Lấy tên của các nhãn (trừ -100)
    target_names = [vocab.idx2tag[i] for i in unique_labels if i != -100] 
    
    # In ra báo cáo chi tiết
    report = classification_report(
        true_labels, 
        predictions, 
        labels=[i for i in unique_labels if i != -100], 
        target_names=target_names, 
        zero_division=0
    )
    logging.info(report)
    logging.info("----------------------------------")

    return f1

if __name__ == "__main__":
    data_dir = "/Users/kittnguyen/Documents/DS201_Finance/data/labeled/ner/syllables"
    output_dir = "/Users/kittnguyen/Documents/DS201_Finance/model_result" 
    
    train_path = path.join(data_dir, "train_vifinner.jsonl")
    dev_path = path.join(data_dir, "dev_vifinner.jsonl")
    test_path = path.join(data_dir, "test_vifinner.jsonl")
    
    best_model_path = path.join(output_dir, "bilstm_best_model.pt")

    logging.info(f"Device being used: {device}")

    logging.info("Loading vocab ... ")
    vocab = Vocab(filepath=train_path)

    logging.info("Loading dataset ... ")
    train_dataset = phoNERT(train_path, vocab=vocab)
    dev_dataset = phoNERT(dev_path, vocab=vocab)
    test_dataset = phoNERT(test_path, vocab=vocab)

    logging.info("Creating dataloader ... ")
    train_dataloader = DataLoader(
        train_dataset, 
        batch_size=32, 
        shuffle=True, 
        collate_fn=collate_fn
    )
    dev_dataloader = DataLoader(
        dev_dataset, 
        batch_size=32, 
        shuffle=False, 
        collate_fn=collate_fn
    )
    test_dataloader = DataLoader(
        test_dataset, 
        batch_size=1, 
        shuffle=False, 
        collate_fn=collate_fn
    )

    logging.info("Building Bi-LSTM NER model ... ")
    model = TextCNN_NER(
        vocab_size=config["vocab_size"],
        embedding_dim=config["embedding_dim"],
        filter_size=config["filter_size"],
        num_tags=config["num_tags"],
        padding_idx=config["padding_idx"],
        n_filters=config["n_filters"],
        dropout=config["dropout"]
    ).to(device)
    
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
    optimizer = optim.Adam(model.parameters(), lr=1e-3) 

    epoch = 0
    best_f1 = 0
    patience = 0
    patience_limit = 10
    
    logging.info("Starting training ...")
    
    while True:
        epoch += 1
        train_loss = train(model, train_dataloader, epoch, loss_fn, optimizer)
        f1 = evaluate(model, dev_dataloader, epoch)
        
        if f1 > best_f1:
            best_f1 = f1
            patience = 0
            torch.save(model.state_dict(), best_model_path)
            logging.info(f"New best F1: {best_f1:.4f}. Saved model.")
        else:
            patience += 1
            logging.info(f"No improvement. Patience: {patience}/{patience_limit}")
        
        if ((patience == patience_limit) or (epoch == 100)): 
            logging.info("Stopping training.")
            break
                  
    logging.info("Loading best model for final test ...")
    model.load_state_dict(torch.load(best_model_path))
    model.to(device)
          
    test_f1 = evaluate(model, test_dataloader, epoch)
    logging.info(f"Final F1 score on TEST set: {test_f1}")
