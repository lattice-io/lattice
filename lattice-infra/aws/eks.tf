locals {
  # Label key of eks node group
  ng_key = "eks.amazonaws.com/nodegroup"
  # System node group name
  sys_ng = "system"
  # GPU node group name
  gpu_ng = "gpu"
}

module "eks" {
  source = "terraform-aws-modules/eks/aws"

  cluster_name    = local.project_name
  cluster_version = local.cluster_version

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  control_plane_subnet_ids       = module.vpc.intra_subnets
  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    system = {
      name            = local.sys_ng
      use_name_prefix = false

      desired_size = 1
      min_size     = 1
      max_size     = 3

      disk_size                  = 32
      subnet_ids                 = [module.vpc.private_subnets[0]]
      instance_types             = ["m5.2xlarge"]
      use_custom_launch_template = false
    }

    gpu = {
      name            = local.gpu_ng
      use_name_prefix = false

      desired_size = 0
      min_size     = 0
      max_size     = local.max_cluster_size

      disk_size                  = 64
      subnet_ids                 = [module.vpc.private_subnets[0]]
      instance_types             = ["g4dn.xlarge"]
      ami_type                   = "AL2_x86_64_GPU"
      use_custom_launch_template = false
    }
  }
}
