# Lattice Clusters with Terraform

[![aws-ci](https://github.com/breezeml/lattice-infra/actions/workflows/aws-ci.yaml/badge.svg?branch=main)](https://github.com/breezeml/lattice-infra/actions/workflows/aws-ci.yaml)
[![aws-qa](https://github.com/breezeml/lattice-infra/actions/workflows/aws-qa.yaml/badge.svg)](https://github.com/breezeml/lattice-infra/actions/workflows/aws-qa.yaml)

This repo contains Terraform configuration to deploy Lattice clusters on different cloud providers.

## Prerequisites

- [Terraform CLI](https://www.terraform.io/downloads.html)
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/install-kubectl/)
- [`awscli`](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) (>= 2.11.4)

## Deploy the Infrastructure on AWS

Before you get started:

- You need to configure the aws cli
- If you have an existing directory `aws/.terraform` for an older version of this project, which uses Terraform Cloud as the backend, make sure you delete this directory.

We use Terraform with the S3 backend to save states. Go the directory `aws` and run:

```bash
terraform init
```

Follow the instructions to set up backend configurations.

- For the bucket name, please use `breezeml-terraform`
- For the key name, please follow the format `states/<name>`, where the `<name>` should be replaced by an unique name for you own purpose. Note, you don't need to create the file on S3, instead, Terraform will create for you. The only caveat is that the bucket is shared by multiple people and projects, so make sure you are not use a confliting `<name>`.
- For the region, please use `us-east-1`, which is the region of the bucket `breezeml-terraform`

The next step is to set terraform variables. You can do this in the following two ways:

1. Create a `aws/terraform.tfvars` file to set values of variables. Refer to `aws/variables` for all required variables. See the [official docs](https://developer.hashicorp.com/terraform/language/values/variables#variable-definitions-tfvars-files) for more information.
2. Specify env variables in the format `TF_VAR_<variable_name>`, for example, `TF_VAR_project_name`. See the [official docs](https://developer.hashicorp.com/terraform/language/values/variables#environment-variables) for more information.

A few notes about these variables:

- Please use `us-west-1` or `us-west-2` for development. Do not be confused by the region for project (`us-west-1` / `us-west-2`) and region for the state bucket (`us-east-1`)

After you deploy the infrastructure, update the kubeconfig to connect to the K8s cluster. First, make sure your AWS CLI with the access key and secret access key which are used in corresponding Terraform Cloud workspace. Then, run `cd aws && make kubeconfig`

## References

- [Terraform CLI Documentation](https://developer.hashicorp.com/terraform/cli)
