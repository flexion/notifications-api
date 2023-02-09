locals {
  cf_org_name      = "gsa-tts-benefits-studio-prototyping"
  cf_space_name    = "notify-demo"
  env              = "demo"
  app_name         = "notify-api"
  recursive_delete = false
}

module "database" {
  source = "github.com/18f/terraform-cloudgov//database?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  name             = "${local.app_name}-rds-${local.env}"
  recursive_delete = local.recursive_delete
  rds_plan_name    = "micro-psql"
}

module "redis" {
  source = "github.com/18f/terraform-cloudgov//redis?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  name             = "${local.app_name}-redis-${local.env}"
  recursive_delete = local.recursive_delete
  redis_plan_name  = "redis-dev"
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  name             = "${local.app_name}-csv-upload-bucket-${local.env}"
}

module "contact_list_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.2.0"

  cf_org_name      = local.cf_org_name
  cf_space_name    = local.cf_space_name
  recursive_delete = local.recursive_delete
  name             = "${local.app_name}-contact-list-bucket-${local.env}"
}

module "egress-space" {
  source = "../shared/egress_space"

  cf_org_name              = local.cf_org_name
  cf_restricted_space_name = local.cf_space_name
  deployers = [
    var.cf_user,
    "ryan.ahearn@gsa.gov",
    "steven.reilly@gsa.gov"
  ]
}

module "ses_email" {
  source = "../shared/ses"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  recursive_delete    = local.recursive_delete
  aws_region          = "us-gov-west-1"
  email_domain        = "notify.sandbox.10x.gsa.gov"
  email_receipt_error = "notify-support@gsa.gov"
}

#########################################################################
# Wait for SNS is out of sandbox and spending limit is increased
# before activating this module
#########################################################################
# module "sns_sms" {
#   source = "../shared/sns"

#   cf_org_name         = local.cf_org_name
#   cf_space_name       = local.cf_space_name
#   name                = "${local.app_name}-sns-${local.env}"
#   recursive_delete    = local.recursive_delete
#   aws_region          = "us-gov-east-1"
#   monthly_spend_limit = 25
# }
