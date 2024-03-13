# Running Lattice on AWS

This project contains a [Terraform](https://www.terraform.io/) configuration for running Lattice on AWS EKS.

To get started, you'll need to install Terraform and the AWS CLI. Then set a few terraform variables by creating a `terraform.tfvars` file in current directory with the following variables:

```
project_name = ""
aws_region = ""
aws_access_key = ""
aws_secret_key = ""
jfrog_username = ""
jfrog_password = ""
```

Then initialize Terraform. By default, this project uses S3 bucket for storing Terraform state. If you want to use a different backend, you can change the `terraform.backend` block in the `terraform.tf` file.

```bash
terraform init -upgrade \
  -backend-config="bucket=<bucket-for-state>" \
  -backend-config="key=<key-for-state>" \
  -backend-config="region=<region-for-state>"
```

Now you can start to provision the infrastructure.

```bash
terraform apply
```

This will provision an EKS cluster and install all the helm charts required to run Lattice.

After the cluster is provisioned, you can get the kubeconfig for the cluster by running:

```bash
aws eks update-kubeconfig --region $(terraform output -raw region) --name $(terraform output -raw cluster_name)
```
