# Training on a custom dataset

To train on a custom dataset, the first step is to make sure that there is
a way to access the dataset on the cluster.
We need two things:
1. A remote service running on the cluster that can host our datasets
   and that is accessible by the running applications
2. A way of accessing the datasets from within the application

Below, we provide instructions on how such restful dataset hosting service
could be setup, and how it could be connected with the cluster to make
datasets directly accessible to workers on the cluster.

## Preparing a Dataset for use on a cluster
To prepare a dataset to be used on the cluster,
you can follow the following steps.

First, you should set up some restful API service that can host the datasets
to allow users to quickly upload and access their datasets remotely.

Here is an example of such a restful service API:

### List the datasets
`GET /datasets`

Lists all datasets that have been created.

```
curl -X GET http://localhost:8080/datasets
```

Request:
```
GET /dataset
```

Response:
```
HTTP/1.1 200 OK
Content-Type: application/json

{
    "datasets": [
        {
            "name": "my_dataset",
            "location": "/dataset/my_dataset"
        },
        {
            "name": "another_dataset",
            "location": "/dataset/another_dataset"
        }
    ]
}
```

### Create a new dataset
`POST /datasets`

Creates a new dataset with a specified name. The name of the dataset should be passed in the body of the request.

```
curl -X POST -H "Content-Type: application/json" -d '{"name": "my_dataset"}' http://localhost:8080/datasets
```

Request:
```
POST /dataset HTTP/1.1
Content-Type: application/json

{
    "name": "my_dataset"
}
```

Response:
```
HTTP/1.1 201 Created
Location: /dataset/my_dataset
```

### Upload data to a dataset
`PUT /datasets/{dataset_name}`

Upload data to a dataset. The name of the dataset should be specified in the URL, and the data to be uploaded should be sent as a file or directory in the body of the request.

```
curl -X PUT -H "Content-Type: application/octet-stream" --data-binary @my_file.csv http://localhost:8080/datsets/{dataset_name}
```

Request:
```
PUT /dataset/my_dataset HTTP/1.1
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="my_file.csv"

[contents of my_file.csv]
```

Response:
```
HTTP/1.1 200 OK
```

### Download data from a dataset
`GET /datasets/{dataset_name}`

Download data from a dataset. The name of the dataset should be specified in the URL.

```
curl http://localhost:8080/datasets
```

Request:
```
GET /dataset/{dataset_name} HTTP/1.1
```

Response:
```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="my_file.csv"

[contents of my_file.csv]
```

## Working with Lattice

Now it's time to put this dataset service to use with our training job.
To do so, first let's see how we should write out application to access
the dataset.
Then, how we can launch a job to make that remote dataset accessible.

### Launching a job with the dataset

To use remote datasets with Lattice, you can specify a the name of a dataset
to use in the job.
You can see an example of this in the job file defined below.

```yaml
apiVersion: "breezeml.ai/v1"
kind: TrainingJob
metadata:
  name: example-job
  namespace: lattice
spec:
  minSize: 1
  maxSize: 3
  dataset: my_dataset
  replicaSpecs:
    template:
      spec:
        containers:
          - name: trainingjob
            image: breezeml/lattice-resnet
            imagePullPolicy: Always
            command: ["python", "-u", "main.py"]
```
- Here we have defined a new element of the spec called `dataset`
- This tells the operator which dataset to mount on the workers

Now, when you write your applications, you can assume that whichever
dataset you have prepared will be mounted in a persistent volume
on the pod at the locations `/datasets/my_dataset`.
Now the data is accessible to be used when running the training job.

### Access the dataset from your application

As mentioned above, when the job is launched you can assume that it will
be mounted at the location `/datasets/my_dataset`.
Therefore, when writing your application, you can access it at that location.
For example, assuming you are using a PyTorch `ImageFolder` for a dataset
like ImageNet, you could do the following:
```python
import torch
import torchvision

train_dataset = torchvision.datasets.ImageFolder('/dataset/imagenet/train', transforms=...)
valid_dataset = torchvision.datasets.ImageFolder('/dataset/imagenet/val', transforms=...)
```

# Training on a remote custom dataset

In certain cases, it is beneficial to train directly from a reomte
data source, such as S3 or other object storage.
For very large datatets, it can sometimes be difficult to move data
directly onto the cluster as it requires provisioning large amounts
of storage and takes time to transfer the data.
Luckily, PyTorch allows us a way to directly access our data from
object stores like S3, without having to download the full dataset
ahead of time.

Below, we can see some examples of how to write a PyTorch training
script for a dataset like ImageNet that is stored on S3.
Specifically, we show how you can create an ImageFolder that indexes
files stored on S3 and loads them at training time, as well as a
streaminig implementation that uses the `torchdata` library.

## Using remote datasets

### S3FS
The first method uses the `s3fs` library to treat the remote S3 store as a
local file system.
Let's assume we have something like the imagenet dataset stored on S3, which
has the following format:
```
train/
|-- n01440764/
|   |-- n01440764_10043.JPEG
|   |-- n01440764_10470.JPEG
|   └-- ...
|-- n01443537/
|   |-- n01443537_10092.JPEG
|   |-- n01443537_10408.JPEG
|   └-- ...
|-- n01484850/
|   |-- n01484850_1199.JPEG
|   |-- n01484850_12836.JPEG
|   └-- ...
...
```
- The labels are the subdirectories (`n01440764`, `n01443537`, `n014848501`)
- Under each subdirectory is the set of images for that label

Here we can see an example of a dataset uses the `s3fs` library to create an
`S3ImageFolder` which can be treated as a standard PyTorch Dataset once it has
been created.

```python
class S3ImageFolder(Dataset):
    def __init__(self, bucket_name, prefix, transform=None):
        logger.info("loading data from s3 bucket: %s, prefix: %s", bucket_name, prefix)
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.transform = transform
        self.s3 = s3fs.S3FileSystem()

        self.classes = []
        self.class_to_idx = {}
        self.samples = []

        for i, class_dir in enumerate(self.s3.ls("s3://" + self.bucket_name + "/" + self.prefix)):
            class_name = class_dir.split("/")[-1]
            self.classes.append(class_name)
            self.class_to_idx[class_name] = i

            for file in self.s3.ls("s3://" + class_dir):
                self.samples.append((file, i))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        i = 1
        filename, class_index = self.samples[index]
        since = time.time()
        try:
            with self.s3.open("s3://" + filename, 'rb') as f:
                file_time = time.time()
                print("S3 open image from s3 cost: %s", file_time - since)

                img = Image.open(f).convert('RGB')
                pil_open_time = time.time()

                if self.transform is not None:
                    img = self.transform(img)
        except Exception as e:
            print(i)
            i = i + 1

        return img, class_index
```
- You can see from the above code snippet that we start by creating a list of all filenames and their labels
- We also implement the `__len__` and `__getitem__` which are required functions of PyTorch Dataset implementations
    - The `__getitem__` feature will download a single image and apply all transforms
- By creating a list of all image files before hand, we are still able to do things like randomly shuffle the dataset

Once you have included the `S3ImageFolder` in your code, you can use it as a normal dataset as seen below:
```python
dataset = S3ImageFolder('dataset-bucket', 'path/to/dataset', transforms)

dataloader = DataLoader(dataset, batch_size=8, num_workers=4)

for x, y in dataloader:
    ...
```
- It is recommended to use `num_workers` so that the DataLoader can do some prefetching of the remote data


### The torchdata library

The `torchdata` library is a more recent development from PyTorch which allows users to stream data from a
data source without having to retrieve the full dataset first.

There in one important thing to note about how to store the dataset here that differs from S3FS.
While in S3FS we mapped out the whole dataset before starting, so we were able to map label names to their
encoding (for example, `n01440764` equals label `0`), in the case of `torchdata` the dataset will be streamed
directly, wihtout making a pass over the whole dataset first.
For this reason, it is preferable to store the label values directly in the dataset, for example by
replacing the above file structure with the following:

```
train/
|-- 0/
|   |-- n01440764_10043.JPEG
|   |-- n01440764_10470.JPEG
|   └-- ...
|-- 1/
|   |-- n01443537_10092.JPEG
|   |-- n01443537_10408.JPEG
|   └-- ...
|-- 2/
|   |-- n01484850_1199.JPEG
|   |-- n01484850_12836.JPEG
|   └-- ...
...
```

Now we can see how to use the `torchdata` S3FileLoader class to read the dataset directly from S3.

```python
from PIL import Image
from torchdata.datapipes.iter import IterableWrapper, S3FileLoader
import torchvision.transforms as transforms

# Create a wrapper that reads all the filenames on S3
dp_s3_urls = IterableWrapper(['s3://s3-dataset/imagenet/']).list_files_by_s3()
# For distributed training, the dataset has to be sharded
sharded_s3_urls = dp_s3_urls.shuffle().sharding_filter()
dp_s3_files = S3FileLoader(sharded_s3_urls)

train_transforms = transforms.Compose([
    transforms.ToTensor()
])

# Create a mapping from the (url, File) tuple to
# a format that is usable by PyTorch
def process(sample):
    url, fd = sample
    label = int(url.split('_')[-1][0])

    image = Image.open(fd).convert('RGB')

    image = train_transforms(image)

    return image, label

dp_s3_files_mapped = dp_s3_files.map(process)

for img, label in dp_s3_files_mapped:
    print(img.size(), label) # Output: torch.Size([3, 224, 224]) 0
```

Once you have the S3 data pipe configured to read images from S3, you can combine
it with a torch DataLoader just as you would a normal torch dataset:
```python
from torch.utils.data import DataLoader

dl = DataLoader(dp_s3_files_mapped, batch_size=8)

for inputs, labels in dl:
    output = model(inputs)
    ...
```
