locals {
  project_name     = var.project_name
  cluster_version  = "1.22"
  max_cluster_size = 12
}

data "aws_region" "current" {}
