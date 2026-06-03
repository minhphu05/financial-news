import fasttext
from DataUtils.embeddings import build_embedding_matrix
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

from DataUtils.NER_dataset import phoNERT, Vocab, build_collate_fn
from model.BiLSTM_CRF_Pretrained_Embedding import BiLSTM_CRF

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# BiLSTM Config
with open("/kaggle/working/training_model/config/bilstm_crf.yaml") as f:
    cfg = yaml.safe_load(f)

model_cfg = cfg["model"]

def train(model: nn.Module,
          data: DataLoader,
          epoch: int,
          optimizer: optim.Optimizer) -> float:

    model.train()
    running_loss = []

    pbar = tqdm(data, desc=f"Epoch {epoch} - Training")

    for batch in pbar:
        input_ids = batch["input_ids"].to(device)
        tags_ids = batch["tags_ids"].to(device)
        lengths = batch["lengths"]

        optimizer.zero_grad()

        # CRF trả về LOSS
        loss = model(input_ids, lengths, tags_ids)

        loss.backward()
        optimizer.step()

        running_loss.append(loss.item())
        pbar.set_postfix({"loss": sum(running_loss) / len(running_loss)})

    return sum(running_loss) / len(running_loss)

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

            # CRF decode → List[List[int]]
            preds = model(input_ids, lengths)

            for pred_seq, true_seq, l in zip(preds, tags_ids, lengths):
                true_labels.extend(true_seq[:l].cpu().tolist())
                predictions.extend(pred_seq[:l])
            assert len(true_labels) == len(predictions), \
                f"Mismatch: y_true={len(true_labels)}, y_pred={len(predictions)}"

    precision = precision_score(true_labels, predictions, average="macro", zero_division=0)
    recall = recall_score(true_labels, predictions, average="macro", zero_division=0)
    f1 = f1_score(true_labels, predictions, average="macro", zero_division=0)

    logging.info(f"Precision: {precision:.4f}")
    logging.info(f"Recall: {recall:.4f}")
    logging.info(f"F1 Score: {f1:.4f}")
    logging.info("----------------------------------")

    # Classification report
    unique_labels = np.unique(true_labels)
    target_names = [vocab.idx2tag[i] for i in unique_labels]

    report = classification_report(
        true_labels,
        predictions,
        labels=unique_labels,
        target_names=target_names,
        zero_division=0
    )
    logging.info(report)
    logging.info("----------------------------------")

    return f1

if __name__ == "__main__":
    data_dir = "/kaggle/input/ner-dataset-crf"
    output_dir = "/kaggle/working/" 
    
    train_path = path.join(data_dir, "train_vifinner.jsonl")
    dev_path = path.join(data_dir, "dev_vifinner.jsonl")
    test_path = path.join(data_dir, "test_vifinner.jsonl")
    
    best_model_path = path.join(output_dir, "bilstm_crf_best_model.pt")

    logging.info(f"Device being used: {device}")

    logging.info("Loading vocab ... ")
    vocab = Vocab(filepath=train_path)

    # LOAD FASTTEXT SAU KHI CÓ VOCAB
    logging.info("Loading fastText ...")
    ft = fasttext.load_model("cc.vi.300.bin")

    logging.info("Building embedding matrix ...")
    embedding_matrix = build_embedding_matrix(
        vocab,
        ft,
        embedding_dim=300
    )
    embedding_matrix = embedding_matrix.to(device)

    logging.info("Loading dataset ... ")
    train_dataset = phoNERT(train_path, vocab=vocab)
    dev_dataset = phoNERT(dev_path, vocab=vocab)
    test_dataset = phoNERT(test_path, vocab=vocab)

    logging.info("Creating dataloader ... ")
    collate_fn = build_collate_fn(vocab)
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

    logging.info("Building Bi-LSTM CRF NER model ... ")
    model = BiLSTM_CRF(
        vocab_size=vocab.vocab_size,
        num_tags=vocab.num_tags,
        embedding_dim=300,
        hidden_size=model_cfg["encoder"]["hidden_size"],
        num_layers=model_cfg["encoder"]["num_layers"],
        dropout=model_cfg["encoder"]["dropout"],
        padding_idx=model_cfg["embedding"]["padding_idx"],
        pretrained_embeddings=embedding_matrix,
        freeze_embedding=False   # hoặc True nếu muốn freeze
    ).to(device)

    optimizer = optim.Adam(model.parameters(), lr=1e-3) 

    epoch = 0
    best_f1 = 0
    patience = 0
    patience_limit = 20
    
    logging.info("Starting training ...")
    
    while True:
        epoch += 1
        train_loss = train(model, train_dataloader, epoch, optimizer)
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