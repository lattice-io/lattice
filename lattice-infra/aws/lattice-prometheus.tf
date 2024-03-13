resource "helm_release" "prometheus" {
  depends_on = [module.eks, kubectl_manifest.lattice_ns]

  namespace  = "lattice"
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus"
  version    = "19.7.1"

  values = [<<-EOT
    alertmanager:
      enabled: false

    pushgateway:
      enabled: false

    server:
      ingress:
        enabled: false
      nodeSelector:
        "${local.ng_key}": "${local.sys_ng}"

    kube-state-metrics:
      nodeSelector:
        "${local.ng_key}": "${local.sys_ng}"

    serverFiles:
      prometheus.yml:
        scrape_configs:  
          - job_name: operator
            static_configs:
              - targets:
                - lattice-operator:8080
            scrape_interval: 10s
            scrape_timeout: 5s
  EOT
  ]
}
