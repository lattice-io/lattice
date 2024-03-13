# EKS Addon: GPU Device Plugin
# Reference: https://docs.aws.amazon.com/eks/latest/userguide/gpu-ami.html

locals {
  gdp_ns = "kube-system"
}

resource "helm_release" "gpu_device_plugin" {
  depends_on = [module.eks]

  namespace  = local.gdp_ns
  name       = "gpu-device-plugin"
  repository = "https://nvidia.github.io/k8s-device-plugin"
  chart      = "nvidia-device-plugin"
  version    = "0.6.0"
}
