resource "helm_release" "lattice_ckpt" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace           = "lattice"
  name                = "lattice-ckpt"
  repository          = "https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm"
  repository_username = var.jfrog_username
  repository_password = var.jfrog_password
  chart               = "lattice-ckpt"
  version             = "0.1.3"

  values = [<<-EOT
    jfrog:
      username: ${var.jfrog_username}
      password: ${var.jfrog_password}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
  EOT
  ]
}
