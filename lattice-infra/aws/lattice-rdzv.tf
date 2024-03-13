resource "helm_release" "lattice_rdzv" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  name                = "lattice-rdzv"
  namespace           = "lattice"
  repository          = "https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm"
  repository_username = var.jfrog_username
  repository_password = var.jfrog_password
  chart               = "lattice-rdzv"
  version             = "0.1.0"

  values = [<<-EOT
    jfrog:
      username: ${var.jfrog_username}
      password: ${var.jfrog_password}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
  EOT
  ]
}
