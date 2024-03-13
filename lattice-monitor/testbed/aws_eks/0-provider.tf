terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = "ap-southeast-1"
}

variable "cluster_name" {
  default = "lattice_dashboard_ingress_4_node"
}

variable "cluster_version" {
  default = "1.24"
}
