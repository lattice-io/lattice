resource "kubectl_manifest" "lattice_ns" {
  depends_on = [module.eks]

  yaml_body = <<-EOT
    apiVersion: v1
    kind: Namespace
    metadata:
      name: lattice
  EOT
}
