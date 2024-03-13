locals {
  lattice_loki_ns = "lattice"
  lattice_loki_sa = "lattice-loki-sa"
  oidc_id         = replace(data.aws_eks_cluster.current.identity[0].oidc[0].issuer, "https://", "")
}

data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "current" {
  depends_on = [module.eks]
  name       = module.eks.cluster_name
}

data "aws_iam_policy_document" "loki_oidc" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_id}:sub"
      values   = ["system:serviceaccount:${local.lattice_loki_ns}:${local.lattice_loki_sa}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_id}:aud"
      values   = ["sts.amazonaws.com"]
    }

    principals {
      identifiers = [
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_id}"
      ]
      type = "Federated"
    }
  }
}

resource "aws_s3_bucket" "loki_data" {
  force_destroy = true
}

resource "aws_s3_bucket_policy" "loki_grant_access" {
  bucket = aws_s3_bucket.loki_data.id
  policy = jsonencode({
    Version : "2012-10-17",
    Statement : [
      {
        Sid : "Statement1",
        Effect : "Allow",
        Principal : {
          AWS : aws_iam_role.loki_iam_role.arn
        },
        Action : [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ],
        Resource : [
          aws_s3_bucket.loki_data.arn,
          "${aws_s3_bucket.loki_data.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role" "loki_iam_role" {
  name               = "LokiStorage-${module.eks.cluster_name}"
  assume_role_policy = data.aws_iam_policy_document.loki_oidc.json

  inline_policy {}
}

resource "aws_iam_policy" "loki_iam_policy" {
  name        = "LokiStorageAccessPolicy-${aws_s3_bucket.loki_data.id}"
  path        = "/"
  description = "Allows Loki to access bucket"

  policy = jsonencode({
    Version : "2012-10-17",
    Statement : [
      {
        Effect : "Allow",
        Action : [
          "s3:ListBucket",
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ],
        Resource : [
          aws_s3_bucket.loki_data.arn,
          "${aws_s3_bucket.loki_data.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "loki_attach" {
  role       = aws_iam_role.loki_iam_role.name
  policy_arn = aws_iam_policy.loki_iam_policy.arn
}

resource "helm_release" "loki" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace  = local.lattice_loki_ns
  name       = "loki"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki"
  version    = "5.2.0"

  values = [<<-EOT
    serviceAccount:
      name: ${local.lattice_loki_sa}
      annotations:
        eks.amazonaws.com/role-arn: ${aws_iam_role.loki_iam_role.arn}
    
    loki:
      commonConfig:
        replication_factor: 1
      storage:
        type: "s3"
        s3:
          region: ${data.aws_region.current.name}
        bucketNames:
          chunks: ${aws_s3_bucket.loki_data.id}
          ruler: ${aws_s3_bucket.loki_data.id}
          admin: ${aws_s3_bucket.loki_data.id}
      auth_enabled: false
    
    singleBinary:
      replicas: 1
      nodeSelector:
        "${local.ng_key}": "${local.sys_ng}"
  EOT
  ]
}

resource "helm_release" "promtail" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace  = local.lattice_loki_ns
  name       = "promtail"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "promtail"
  version    = "6.11.0"

  values = [<<-EOT
    config:
      clients:
        - url: http://loki-gateway.${local.lattice_loki_ns}/loki/api/v1/push
  EOT
  ]
}