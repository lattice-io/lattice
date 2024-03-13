resource "helm_release" "lattice_dashboard" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace           = "lattice"
  name                = "lattice-dashboard"
  repository          = "https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm"
  repository_username = var.jfrog_username
  repository_password = var.jfrog_password
  chart               = "lattice-dashboard"
  version             = "0.0.10"

  values = [<<-EOT
    jfrog:
      username: ${var.jfrog_username}
      password: ${var.jfrog_password}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
  EOT
  ]
}

resource "aws_lb_target_group" "lattice_dashboard" {
  depends_on = [
    module.eks,
    helm_release.lattice_dashboard,
    aws_lb_listener.this
  ]

  name = "${local.project_name}-lattice-dashboard"

  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
}

resource "kubectl_manifest" "lattice_dashboard_tgb" {
  depends_on = [
    module.eks,
    helm_release.aws_load_balancer_controller,
    helm_release.lattice_dashboard
  ]

  yaml_body = <<-EOF
    apiVersion: elbv2.k8s.aws/v1beta1
    kind: TargetGroupBinding
    metadata:
      name: lattice-dashboard
      namespace: lattice
    spec:
      networking:
        ingress:
          - from:
              - securityGroup:
                  groupID: "${module.lb_sg.security_group_id}"
            ports:
              - port: 80
                protocol: TCP
      serviceRef:
        name: lattice-dashboard
        port: http
      targetGroupARN: "${aws_lb_target_group.lattice_dashboard.arn}"
  EOF
}

resource "aws_lb_listener_rule" "lattice_dashboard" {
  depends_on = [
    module.eks,
    helm_release.lattice_dashboard
  ]

  listener_arn = aws_lb_listener.this.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.lattice_dashboard.arn
  }

  condition {
    path_pattern {
      values = ["/", "/*"]
    }
  }
}
