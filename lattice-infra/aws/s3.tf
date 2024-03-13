module "s3" {
  source = "terraform-aws-modules/s3-bucket/aws"

  acl           = "null"
  force_destroy = true
}
