variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name"
  default     = "secdevproject-sample-bucket"
}

variable "env" {
  type        = string
  description = "Environment tag"
  default     = "dev"
}
