#!/bin/bash
# Deploy the GaleFling log upload backend.
#
# Prerequisites:
#   1. AWS CLI configured with credentials
#   2. ACM certificate for galefling.jasmer.tools (note the ARN)
#   3. SES verified sender identity for morgan@windsofstorm.net
#
# Usage:
#   ./deploy.sh <certificate-arn> <bucket-name-suffix> [aws-profile]
#
# Arguments:
#   certificate-arn     ARN of the ACM certificate for galefling.jasmer.tools
#   bucket-name-suffix  Short suffix for the media staging bucket name
#                       (e.g. "jas" produces galefling-media-staging-jas)
#   aws-profile         Optional AWS CLI profile name

set -euo pipefail

STACK_NAME="galefling-log-upload"
TEMPLATE="galefling-log-upload.yaml"
MEDIA_STACK_NAME="galefling-media-staging"
MEDIA_TEMPLATE="galefling-media-staging.yaml"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <certificate-arn> <bucket-name-suffix> [aws-profile]"
    echo ""
    echo "Example:"
    echo "  $0 arn:aws:acm:us-east-1:123456789:certificate/abc-123 jas default"
    exit 1
fi

CERTIFICATE_ARN="$1"
BUCKET_SUFFIX="$2"
AWS_PROFILE="${3:-}"

AWS_REGION="$(cut -d: -f4 <<<"$CERTIFICATE_ARN")"
if [ -z "$AWS_REGION" ]; then
    echo "Could not parse region from certificate ARN."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AWS_CLI=(aws)
AWS_CLI+=(--region "$AWS_REGION")
if [ -n "$AWS_PROFILE" ]; then
    AWS_CLI+=(--profile "$AWS_PROFILE")
fi

echo "Deploying stack: ${STACK_NAME}"
echo "  Certificate: ${CERTIFICATE_ARN}"
echo "  Region: ${AWS_REGION}"
if [ -n "$AWS_PROFILE" ]; then
    echo "  Profile: ${AWS_PROFILE}"
fi
echo ""

# ── 1. Deploy log-upload stack ─────────────────────────────────────────────

"${AWS_CLI[@]}" cloudformation deploy \
    --template-file "${TEMPLATE}" \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        CertificateArn="${CERTIFICATE_ARN}" \
    --tags \
        Project=GaleFling \
        Environment=Production

echo ""
echo "Waiting for ${STACK_NAME} to finish..."
set +e
"${AWS_CLI[@]}" cloudformation wait stack-create-complete --stack-name "${STACK_NAME}" 2>/dev/null
WAIT_STATUS=$?
if [ "$WAIT_STATUS" -ne 0 ]; then
    "${AWS_CLI[@]}" cloudformation wait stack-update-complete --stack-name "${STACK_NAME}" 2>/dev/null
    WAIT_STATUS=$?
fi
set -e

if [ "$WAIT_STATUS" -ne 0 ]; then
    echo "Stack ${STACK_NAME} failed to deploy. Recent events:"
    "${AWS_CLI[@]}" cloudformation describe-stack-events \
        --stack-name "${STACK_NAME}" \
        --max-items 15 \
        --output table
    exit 1
fi

echo "${STACK_NAME} outputs:"
"${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

echo ""
echo "DNS CNAME to create:"
"${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey==\`CustomDomainTarget\`].OutputValue" \
    --output text

# ── 2. Deploy Lambda function code ─────────────────────────────────────────

echo ""
echo "Deploying Lambda function code..."

LAMBDA_FUNCTION_ARN="$("${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey==\`LambdaFunctionArn\`].OutputValue" \
    --output text)"

(cd "${SCRIPT_DIR}" && zip -j lambda.zip lambda_function.py)

"${AWS_CLI[@]}" lambda update-function-code \
    --function-name "${LAMBDA_FUNCTION_ARN}" \
    --zip-file "fileb://${SCRIPT_DIR}/lambda.zip"

echo "Lambda function code updated."

# ── 3. Deploy media-staging stack ──────────────────────────────────────────

echo ""
echo "Deploying stack: ${MEDIA_STACK_NAME}"
echo "  Bucket suffix: ${BUCKET_SUFFIX}"
echo ""

"${AWS_CLI[@]}" cloudformation deploy \
    --template-file "${MEDIA_TEMPLATE}" \
    --stack-name "${MEDIA_STACK_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        BucketNameSuffix="${BUCKET_SUFFIX}" \
    --tags \
        Project=GaleFling \
        Environment=Production

echo ""
echo "Waiting for ${MEDIA_STACK_NAME} to finish..."
set +e
"${AWS_CLI[@]}" cloudformation wait stack-create-complete --stack-name "${MEDIA_STACK_NAME}" 2>/dev/null
WAIT_STATUS=$?
if [ "$WAIT_STATUS" -ne 0 ]; then
    "${AWS_CLI[@]}" cloudformation wait stack-update-complete --stack-name "${MEDIA_STACK_NAME}" 2>/dev/null
    WAIT_STATUS=$?
fi
set -e

if [ "$WAIT_STATUS" -ne 0 ]; then
    echo "Stack ${MEDIA_STACK_NAME} failed to deploy. Recent events:"
    "${AWS_CLI[@]}" cloudformation describe-stack-events \
        --stack-name "${MEDIA_STACK_NAME}" \
        --max-items 15 \
        --output table
    exit 1
fi

echo "${MEDIA_STACK_NAME} outputs:"
"${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${MEDIA_STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

# ── 4. Next steps ──────────────────────────────────────────────────────────

echo ""
echo "Next steps:"
echo "  1. Create the DNS CNAME shown above for galefling.jasmer.tools"
echo "  2. Verify SES sender identity for morgan@windsofstorm.net"
echo "  3. Store the SecretAccessKey from the media-staging outputs —"
echo "     it is only available now and cannot be retrieved later."
echo "  4. Test the endpoint: curl -X POST https://galefling.jasmer.tools/logs/upload"
