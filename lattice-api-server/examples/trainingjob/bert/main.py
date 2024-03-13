import argparse
from datasets import load_dataset
from transformers import AutoTokenizer
from transformers import AutoModelForSequenceClassification
from torch.utils.data import DataLoader
from torch.optim import AdamW
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from datetime import timedelta
from transformers import get_scheduler
from tqdm.auto import tqdm
import torch
import numpy as np
import evaluate
import argparse
import os
import boto3
import io

from pathlib import Path

argparser = argparse.ArgumentParser()
argparser.add_argument('--batch-size', type=int, default=8)
argparser.add_argument('--max_epochs', type=int, default=100)

LOCAL_RANK=0

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return metric.compute(predictions=predictions, references=labels)


def get_dataset():

    def tokenize_function(examples):
        return tokenizer(examples["text"], padding="max_length", truncation=True)

    dataset_dir = os.path.join(Path.home(), 'data')
    dataset = load_dataset("yelp_review_full", data_dir=dataset_dir, name='yelp_review_full', cache_dir=dataset_dir)
    tokenizer = AutoTokenizer.from_pretrained("bert-base-cased")
    tokenized_datasets = dataset.map(tokenize_function, batched=True)
    tokenized_datasets = tokenized_datasets.remove_columns(["text"])

    tokenized_datasets = tokenized_datasets.rename_column("label", "labels")
    tokenized_datasets.set_format("torch")

    train_dataset = tokenized_datasets["train"].shuffle(seed=42).select(range(10000))
    eval_dataset = tokenized_datasets["test"].shuffle(seed=42).select(range(1000))

    return train_dataset, eval_dataset


def run_train(epoch: int, num_training_steps: int, model: torch.nn.Module, optimizer: torch.optim.Optimizer, train_loader, lr_scheduler):
    train_loader.sampler.set_epoch(epoch)

    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    model.train()

    for s, batch in enumerate(train_loader):
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        lr_scheduler.step()
        optimizer.zero_grad()
        print(f"Epoch {epoch}, Step {s}: Loss {loss.item()}")


def full_train(test_loader,max_epochs, model, loader, optimizer):
    num_training_steps = max_epochs * len(loader)
    lr_scheduler = get_scheduler(
        name="linear", optimizer=optimizer, num_warmup_steps=0,
        num_training_steps=num_training_steps)


    for e in range(max_epochs):
        print("Starting epoch", e)
        run_train(e, num_training_steps, model, optimizer, loader, lr_scheduler)
        run_eval(model, test_loader)


def run_eval(model, eval_dataloader):
    metric = evaluate.load("accuracy")
    model.eval()
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    for batch in eval_dataloader:
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.no_grad():
            outputs = model(**batch)

        logits = outputs.logits
        predictions = torch.argmax(logits, dim=-1)
        metric.add_batch(predictions=predictions, references=batch["labels"])

    try:
        metric.compute()
    except ValueError:
        return


def save_model_to_s3(model: torch.nn.Module):
    s3_file_path = os.environ.get("S3URL")
    if not s3_file_path:
        raise ValueError("S3URL environment variable is not set")
    
    bucket_name, object_key = s3_file_path.replace('s3://', '').split('/', 1)

    try:
        print('Saving model to s3 ...')
        s3_client = boto3.client('s3')
        buffer = io.BytesIO()
        torch.save(model.state_dict(), buffer)

        s3_client.put_object(Bucket=bucket_name, Key=object_key, Body=buffer.getvalue())

        print('Model saved')
    except Exception as e:
        print(f"Error saving model to S3: {e}")
        raise


def main():
    train_dataset, eval_dataset = get_dataset()
    train_sampler = torch.utils.data.distributed.DistributedSampler(
        train_dataset, num_replicas=int(os.environ['WORLD_SIZE']), rank=int(os.environ['RANK'])
    )
    train_dataloader = DataLoader(train_dataset, batch_size=8, sampler=train_sampler)

    eval_dataloader = DataLoader(eval_dataset, batch_size=8)

    model = AutoModelForSequenceClassification.from_pretrained("bert-base-cased", num_labels=5)
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    model.to(device)
    model = DDP(model)
    optimizer = AdamW(model.parameters(), lr=5e-5)
    full_train(eval_dataloader, max_epochs=args.max_epochs, model=model, loader=train_dataloader, optimizer=optimizer)
    save_model_to_s3(model)


if __name__ == '__main__':
    args = argparser.parse_args()
    local_rank = os.getenv('LOCAL_RANK', None)
    if local_rank and torch.cuda.is_available():
        args.device = f'cuda:{local_rank}'
        LOCAL_RANK = int(local_rank)
        torch.cuda.set_device(LOCAL_RANK)

    backend = 'nccl' if torch.cuda.is_available() else 'gloo'
    dist.init_process_group(backend=backend, timeout=timedelta(seconds=30))
    main()
