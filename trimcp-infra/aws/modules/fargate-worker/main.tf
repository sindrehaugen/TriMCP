locals {
  cluster = "trimcp-${var.deployment_name}-${var.cluster_name_suffix}"
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/trimcp-${var.deployment_name}/worker"
  retention_in_days = var.environment == "prod" ? 90 : 14
}

resource "aws_ecs_cluster" "this" {
  name = local.cluster

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exec" {
  name               = "trimcp-${substr(var.deployment_name, 0, 20)}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "exec" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "trimcp-${substr(var.deployment_name, 0, 20)}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid    = "ReadParams"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = var.secrets_arns
  }

  statement {
    sid       = "S3BlobPrefix"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "trimcp-task-inline"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_ecs_task_definition" "worker" {
  family                   = var.service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.container_image
      essential = true
      # Placeholder — replace with RQ worker entrypoint after image build
      command = ["tail", "-f", "/dev/null"]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name            = var.service_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.id
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.worker.name
}
