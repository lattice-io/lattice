output "region" {
  value = data.aws_region.current.name
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "service_endpoint" {
  value = "http://${aws_lb.this.dns_name}"
}
