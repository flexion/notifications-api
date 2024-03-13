locals {
  cf_org_name              = "gsa-tts-benefits-studio"
  cf_space_name            = "notify-demo"
  env                      = "demo"
  app_name                 = "notify-api"
  delete_recursive_allowed = false
}

data "cloudfoundry_space" "demo" {
  org_name = local.cf_org_name
  name     = local.cf_space_name
}

resource "cloudfoundry_space" "notify-demo" {
  delete_recursive_allowed = local.delete_recursive_allowed
  name                     = local.cf_space_name
  org                      = data.cloudfoundry_org.org.id
}

module "database" {
  source = "github.com/18f/terraform-cloudgov//database?ref=v0.7.1"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-rds-${local.env}"
  rds_plan_name = "micro-psql"
}

module "redis" {
  source = "github.com/18f/terraform-cloudgov//redis?ref=v0.7.1"

  cf_org_name     = local.cf_org_name
  cf_space_name   = local.cf_space_name
  name            = "${local.app_name}-redis-${local.env}"
  redis_plan_name = "redis-dev"
}

module "csv_upload_bucket" {
  source = "github.com/18f/terraform-cloudgov//s3?ref=v0.7.1"

  cf_org_name   = local.cf_org_name
  cf_space_name = local.cf_space_name
  name          = "${local.app_name}-csv-upload-bucket-${local.env}"
}

module "egress-space" {
  source = "../shared/egress_space"

  cf_org_name              = local.cf_org_name
  cf_restricted_space_name = local.cf_space_name
  delete_recursive_allowed = local.delete_recursive_allowed
  deployers = [
    var.cf_user,
    "steven.reilly@gsa.gov"
  ]
}

module "ses_email" {
  source = "../shared/ses"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-ses-${local.env}"
  aws_region          = "us-west-2"
  email_domain        = "notify.sandbox.10x.gsa.gov"
  email_receipt_error = "notify-support@gsa.gov"
}

module "sns_sms" {
  source = "../shared/sns"

  cf_org_name         = local.cf_org_name
  cf_space_name       = local.cf_space_name
  name                = "${local.app_name}-sns-${local.env}"
  aws_region          = "us-east-1"
  monthly_spend_limit = 25
}
