import argparse
from datetime import timedelta
import os
import time
import logging

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

import torchvision
import torchvision.models as models
import torchvision.transforms as transforms

import boto3
import io

CIFAR10_TRAIN_MEAN = (0.5070751592371323, 0.48654887331495095, 0.4409178433670343)
CIFAR10_TRAIN_STD = (0.2673342858792401, 0.2564384629170883, 0.27615047132568404)

LOCAL_RANK=0

argparser = argparse.ArgumentParser()
argparser.add_argument('--batch-size', type=int, default=64)
argparser.add_argument('--model', type=str, default='resnet18')
argparser.add_argument('--max-epochs', type=int, default=100)
argparser.add_argument('--target-acc', '-ta', type=float, default=1.0)


def get_datasets():
    transform_train = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ToTensor(),
        transforms.Normalize(CIFAR10_TRAIN_MEAN, CIFAR10_TRAIN_STD)
    ])
    cifar10_training = torchvision.datasets.CIFAR10(root='./data', train=True, download=True,
                                                      transform=transform_train)

    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(CIFAR10_TRAIN_MEAN, CIFAR10_TRAIN_STD)
    ])
    cifar10_testing = torchvision.datasets.CIFAR10(root='./data', train=False, download=True,
                                                     transform=transform_test)
    return cifar10_training, cifar10_testing


def accuracy(outputs: torch.Tensor, labels: torch.Tensor):
    _, preds = outputs.max(1)
    correct = preds.eq(labels).sum()

    return correct


def run_eval(model: torch.nn.Module,
             loss_fn,
             test_loader):
    print('Running eval')
    total_loss = torch.tensor([0.0])
    total_correct = torch.tensor([0]).to(args.device)

    with torch.no_grad():
        for i, (inputs, labels) in enumerate(test_loader):
            model.eval()
            inputs = inputs.to(args.device)
            labels = labels.to(args.device)

            outputs = model(inputs)

            total_loss += loss_fn(outputs, labels).item()
            total_correct += accuracy(outputs, labels)

    if len(test_loader) == 0:
        return

    total_loss = total_loss.to(args.device)
    total_correct = total_correct.to(args.device)
    dist.all_reduce(total_loss, dist.ReduceOp.SUM)
    dist.all_reduce(total_correct, dist.ReduceOp.SUM)

    loss = total_loss.item() / float(len(test_loader))
    acc = float(total_correct.item()) / len(test_loader.dataset)
    print('Results for this round of eval:')
    print(f'Loss: {loss:.4f}')
    print('Correct:', total_correct.item(), 'Acc:', acc)
    print()

    return acc >= args.target_acc


def run_train(epoch: int, model: torch.nn.Module, optimizer: torch.optim.Optimizer, loss_fn, train_loader):
    train_loader.sampler.set_epoch(epoch)
    for i, (inputs, labels) in enumerate(train_loader):
        print()
        model.train()
        start = time.time()
        optimizer.zero_grad()
        inputs = inputs.to(args.device)
        labels = labels.to(args.device)

        outputs = model(inputs)

        loss = loss_fn(outputs, labels)

        loss.backward()

        optimizer.step()

        end = time.time()
        print(f'Epoch {epoch}, Step {i}: Loss {loss.item():0.4f}, time: {end - start:.3f}s')


def full_train(max_epochs, model: torch.nn.Module, loader, optimizer: torch.optim.Optimizer, loss_fn, test_loader):
    for e in range(0, max_epochs):
        print("Starting epoch", e)

        run_train(e, model, optimizer, loss_fn, loader)

        target_acc_reached = run_eval(model, loss_fn, test_loader)
        if target_acc_reached:
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


def load_model_from_s3(model: torch.nn.Module):
    s3_client = boto3.client('s3')
    s3_file_path = os.environ.get("S3URL")
    if not s3_file_path:
        raise ValueError("S3URL environment variable is not set")

    bucket_name, object_key = s3_file_path.replace('s3://', '').split('/', 1)

    try:
        print('Loading model from s3 ...')
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key=object_key
        )

        state_dict_bytes = response['Body'].read()
        state_dict = torch.load(io.BytesIO(state_dict_bytes))
        model.load_state_dict(state_dict)

        print('Model loaded')
    except Exception as e:
        print(f"Error loading model from S3: {e}")
        raise


def main():
    model = models.__dict__[args.model](num_classes=10).to(args.device)
    ddp_model = DDP(model)

    optimizer = torch.optim.Adam(ddp_model.parameters(), lr=0.0001, weight_decay=5e-4)

    loss_fn = torch.nn.CrossEntropyLoss()

    trainset, testset = get_datasets()

    train_sampler = torch.utils.data.distributed.DistributedSampler(
        trainset, num_replicas=int(os.environ['WORLD_SIZE']), rank=int(os.environ['RANK'])
    )
    train_loader = torch.utils.data.DataLoader(
        trainset, batch_size=args.batch_size, sampler=train_sampler
    )

    test_sampler = torch.utils.data.distributed.DistributedSampler(
        testset, num_replicas=int(os.environ['WORLD_SIZE']), rank=int(os.environ['RANK'])
    )
    test_loader = torch.utils.data.DataLoader(
        testset, batch_size=args.batch_size, sampler=test_sampler
    )

    full_train(max_epochs=args.max_epochs, model=ddp_model, loader=train_loader, optimizer=optimizer, loss_fn=loss_fn,
               test_loader=test_loader)
    
    save_model_to_s3(model)


if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
    args = argparser.parse_args()

    args.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    local_rank = os.getenv('LOCAL_RANK', None)
    if local_rank and torch.cuda.is_available():
        args.device = f'cuda:{local_rank}'
        LOCAL_RANK = int(local_rank)
        torch.cuda.set_device(LOCAL_RANK)

    backend = 'gloo' if args.device == 'cpu' else 'nccl'
    dist.init_process_group(backend=backend, timeout=timedelta(seconds=30))
    main()
