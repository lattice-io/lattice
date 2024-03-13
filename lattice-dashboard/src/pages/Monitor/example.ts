export interface ExampleJobType {
  key: string
  name: string
  model: string
  dataset: string
  storage: string
  tags: string[]
  config: KubeJobConfigType
  submiturl: string
}

export interface KubeJobConfigType {
  apiVersion: string
  kind: string
  metadata: {
    name: string
    namespace: string
  }
  epochs?: number
  spec?: any
}

export const ExampleData: ExampleJobType[] = [
  {
    key: '1',
    name: 'Train BERT on Yelp Review',
    model: 'BERT Base (cased)',
    storage: 'AWS S3',
    dataset: 'Yelp Movie Review',
    tags: ['PyTorch', 'Classification', 'Text'],
    submiturl: "bert",
    config: {
      apiVersion: 'breezeml.ai/v1',
      kind: 'TrainingJob',
      metadata: {
        name: 'lattice-' + 'bert' + '-',
        namespace: 'lattice',
      },
    },
  },
  {
    key: '2',
    name: 'Train ResNet on CIFAR-10',
    model: 'ResNet-50',
    storage: 'AWS S3',
    dataset: 'CIFAR-10',
    tags: ['PyTorch', 'Image', 'Classification'],
    submiturl: "resnet",
    config: {
      apiVersion: 'breezeml.ai/v1',
      kind: 'TrainingJob',
      metadata: {
        name: 'lattice-' + 'resnet' + '-',
        namespace: 'lattice',
      },
    },
  },
]
