data "aws_region" "current" {}

data "aws_vpc" "main" {
  tags = {
    Name = "opta-${var.env_name}"
  }
}

data "aws_subnet_ids" "private" {
  vpc_id = data.aws_vpc.main.id
  tags = {
     type = "private"
  }
}

variable "env_name" {
  description = "Env name"
  type = string
}

variable "layer_name" {
  description = "Layer name"
  type        = string
}

variable "module_name" {
  description = "Module name"
  type = string
}

variable "max_nodes" {
  type    = number
  default = 5
}

variable "min_nodes" {
  type    = number
  default = 3
}

variable "node_disk_size" {
  type    = number
  default = 20
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "k8s_version" {
  type    = string
  default = "1.18"
}

variable "control_plane_security_groups" {
  description = "List of security groups to give control plane access to"
  type        = list(string)
  default     = []
}