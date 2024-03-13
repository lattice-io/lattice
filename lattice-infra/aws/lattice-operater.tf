resource "helm_release" "lattice_operator" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace           = "lattice"
  name                = "lattice-operator"
  repository          = "https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm"
  repository_username = var.jfrog_username
  repository_password = var.jfrog_password
  chart               = "lattice-operator"
  version             = "0.1.11"

  values = [<<-EOT
    jfrog:
      username: ${var.jfrog_username}
      password: ${var.jfrog_password}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
    jobNodeSelector:
      "${local.ng_key}": "${local.gpu_ng}"
    image:
      repository: breezeml.jfrog.io/breezeml-docker/lattice-operator-internal
    monitorNamespace: lattice
  EOT
  ]
}
