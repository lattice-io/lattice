data "aws_availability_zones" "available" {}

locals {
  vpc_cidr      = "10.0.0.0/16"
  number_of_azs = 2
  azs           = slice(data.aws_availability_zones.available.names, 0, local.number_of_azs)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "4.0.2"

  name = local.project_name
  cidr = local.vpc_cidr

  azs             = local.azs
  private_subnets = [for i in range(local.number_of_azs) : cidrsubnet(local.vpc_cidr, 4, i)]
  public_subnets  = [for i in range(local.number_of_azs) : cidrsubnet(local.vpc_cidr, 4, i + local.number_of_azs)]
  intra_subnets   = [for i in range(local.number_of_azs) : cidrsubnet(local.vpc_cidr, 4, i + local.number_of_azs * 2)]

  enable_nat_gateway   = true
  enable_dns_hostnames = true

  enable_flow_log                      = true
  create_flow_log_cloudwatch_iam_role  = true
  create_flow_log_cloudwatch_log_group = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}
