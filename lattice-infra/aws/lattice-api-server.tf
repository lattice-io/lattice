locals {
  lattice_api_server_ns = "lattice"
  lattice_api_server_sa = "lattice-api-server"
  lattice_job_ns        = "lattice"
  lattice_job_sa        = "lattice-job"
}

resource "aws_iam_policy" "lattice_api_server_access_policy" {
  policy = jsonencode({
    Version : "2012-10-17",
    Statement : [
      {
        Effect : "Allow",
        Action : [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ],
        Resource : [
          "${module.s3.s3_bucket_arn}/*"
        ]
      },
      {
        Effect : "Allow",
        Action : [
          "sts:AssumeRoleWithWebIdentity"
        ],
        Resource : [
          "*"
        ]
      },
      {
        Effect : "Allow",
        Action : [
          "eks:UpdateNodegroupConfig",
          "eks:DescribeNodegroup"
        ],
        Resource : [
          "arn:*:eks:${data.aws_region.current.name}:*:nodegroup/${local.project_name}/${local.gpu_ng}/*"
        ]
      }
    ]
  })
}

module "lattice_api_server_irsa_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name = "${local.project_name}-lattice-api-server"
  role_policy_arns = {
    access_policy = aws_iam_policy.lattice_api_server_access_policy.arn
  }

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["${local.lattice_api_server_ns}:${local.lattice_api_server_sa}"]
    }
  }
}

resource "aws_iam_policy" "lattice_job_access_policy" {
  policy = jsonencode({
    Version : "2012-10-17",
    Statement : [
      {
        Effect : "Allow",
        Action : [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ],
        Resource : [
          "${module.s3.s3_bucket_arn}/*"
        ]
      },
      {
        Effect : "Allow",
        Action : [
          "s3:GetAccessPoint",
          "s3:GetAccountPublicAccessBlock",
          "s3:PutStorageLensConfiguration",
          "s3:CreateJob"
        ],
        Resource : [
          "arn:aws:s3:::*"
        ]
      }
    ]
  })
}

module "lattice_job_irsa_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name = "${local.project_name}-lattice-job"
  role_policy_arns = {
    s3_access_policy = aws_iam_policy.lattice_job_access_policy.arn
  }

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["${local.lattice_job_ns}:${local.lattice_job_sa}"]
    }
  }
}

resource "kubectl_manifest" "lattice_job_sa" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  yaml_body = <<-EOT
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: ${local.lattice_job_sa}
      namespace: ${local.lattice_job_ns}
      annotations:
        eks.amazonaws.com/role-arn: ${module.lattice_job_irsa_role.iam_role_arn}
  EOT
}

resource "helm_release" "lattice_api_server" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace           = "lattice"
  name                = "lattice-api-server"
  repository          = "https://breezeml.jfrog.io/artifactory/api/helm/breezeml-helm"
  repository_username = var.jfrog_username
  repository_password = var.jfrog_password
  chart               = "lattice-api-server"
  version             = "0.0.10"

  values = [<<-EOT
    jfrog:
      username: ${var.jfrog_username}
      password: ${var.jfrog_password}
    nodeSelector:
      "${local.ng_key}": "${local.sys_ng}"
    aws:
      region: ${data.aws_region.current.name}
      cluster: ${local.project_name}
      s3:
        serviceAccount: ${local.lattice_job_sa}
        bucket: ${module.s3.s3_bucket_id}
      workerNodegroup: ${local.gpu_ng}
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.lattice_api_server_irsa_role.iam_role_arn}
    maxClusterSize: "${local.max_cluster_size}"
    prometheus:
      queryResolution: 10s
    loki:
      endpoint: loki-gateway.${local.lattice_loki_ns}
      limit: 5000
  EOT
  ]
}

resource "aws_lb_target_group" "lattice_api_server" {
  depends_on = [
    module.eks,
    helm_release.lattice_api_server,
    aws_lb_listener.this
  ]

  name = "${local.project_name}-lattice-api-server"

  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id
}

resource "kubectl_manifest" "lattice_api_server_tgb" {
  depends_on = [
    module.eks,
    helm_release.aws_load_balancer_controller,
    helm_release.lattice_api_server
  ]

  yaml_body = <<-EOF
    apiVersion: elbv2.k8s.aws/v1beta1
    kind: TargetGroupBinding
    metadata:
      name: lattice-api-server
      namespace: lattice
    spec:
      networking:
        ingress:
          - from:
              - securityGroup:
                  groupID: "${module.lb_sg.security_group_id}"
            ports:
              - port: 8080
                protocol: TCP
      serviceRef:
        name: lattice-api-server
        port: http
      targetGroupARN: "${aws_lb_target_group.lattice_api_server.arn}"
  EOF
}

resource "aws_lb_listener_rule" "lattice_api_server" {
  depends_on = [
    module.eks,
    helm_release.lattice_api_server
  ]

  listener_arn = aws_lb_listener.this.arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.lattice_api_server.arn
  }

  condition {
    path_pattern {
      values = ["/api", "/api/*"]
    }
  }
}
