# EKS Addon: AWS Load Balancer Controller

locals {
  lbc_ns = "kube-system"
  lbc_sa = "aws-load-balancer-controller"
}

module "lbc_irsa_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name                              = "${local.project_name}-lbc"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["${local.lbc_ns}:${local.lbc_sa}"]
    }
  }
}

resource "helm_release" "aws_load_balancer_controller" {
  depends_on = [module.eks]

  namespace  = local.lbc_ns
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = "1.4.4"

  values = [<<-EOT
    clusterName: "${module.eks.cluster_name}"
    region: "${data.aws_region.current.name}"
    serviceAccount:
      create: true
      name: "${local.lbc_sa}"
      annotations:
        eks.amazonaws.com/role-arn: ${module.lbc_irsa_role.iam_role_arn}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
  EOT
  ]
}
