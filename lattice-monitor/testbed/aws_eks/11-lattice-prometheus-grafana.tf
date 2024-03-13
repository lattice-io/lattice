resource "helm_release" "lattice-prometheus-grafana" {
  name       = "lattice-prometheus-grafana"
  chart      = "../../sys_monitor_deploy/kube-prometheus-stack"
  namespace  = "lattice-monitor"
  create_namespace = true

  depends_on = [
    aws_eks_node_group.private-nodes,
  ]
}