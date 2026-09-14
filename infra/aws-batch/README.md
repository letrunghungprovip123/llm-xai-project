# Batch I trên AWS Batch

Revision gốc: `5cd405fec7aaa271ebcc62d9b44d95a82757c759`.

Thư mục này lưu cấu hình container và job definition đã dùng cho nhánh thực thi Qwen/Phi. Đây là provenance vận hành; không phải entrypoint chính của pipeline nghiên cứu.

## Chuẩn bị

```bash
chmod +x infra/aws-batch/*.sh
git rev-parse HEAD
git status --short
```

## Build trên Apple Silicon

```bash
./infra/aws-batch/build-local.sh
```

Image được build cho `linux/amd64`, chạy `npm ci` và kiểm tra TypeScript research.

## Kiểm tra container bằng CPU

```bash
./infra/aws-batch/test-container.sh llm-xai-batch-i:5cd405fec7aa
```

## Đẩy image lên ECR

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
./infra/aws-batch/push-ecr.sh
```

## Biến môi trường bắt buộc

```text
RUN_ID
MODEL_ID
HF_MODEL_ID
INPUT_URI
OUTPUT_URI
```

Ví dụ Phi:

```text
RUN_ID=run_phi4_mini_eval36_r1
MODEL_ID=phi4_mini_instruct
HF_MODEL_ID=microsoft/Phi-4-mini-instruct
SERVED_MODEL_NAME=microsoft/Phi-4-mini-instruct
```

Ví dụ Qwen:

```text
RUN_ID=run_qwen3_8b_eval36_r1
MODEL_ID=qwen3_8b
HF_MODEL_ID=Qwen/Qwen3-8B
SERVED_MODEL_NAME=Qwen/Qwen3-8B
```

Thiết lập chung:

```text
INPUT_URI=s3://YOUR_BUCKET/experiments/batch-i/inputs/evaluation_36/evidence_packages_36.jsonl
OUTPUT_URI=s3://YOUR_BUCKET/experiments/batch-i/runs/RUN_ID
REPEAT_ID=1
EXPERIMENT_STAGE=evaluation
EVIDENCE_LEVELS=S0,S1,S2,S3,S4,S5
CHECKPOINT_EVERY=10
CONCURRENCY=1
MAX_TOKENS=2000
```

Tài nguyên AWS Batch đã dùng làm mốc:

```text
VCPU=8
MEMORY=28672 MiB
GPU=1
```

Run chính thức phải tham chiếu ECR image digest, không chỉ mutable tag. Không đặt AWS credential hoặc file `.env` vào image.
