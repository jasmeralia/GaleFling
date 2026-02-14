#!/bin/bash
# Deploy the GalePost log upload backend.
#
# Prerequisites:
#   1. AWS CLI configured with credentials
#   2. ACM certificate for galepost.jasmer.tools (note the ARN)
#   4. SES verified sender identity for noreply@jasmer.tools
#
# Usage:
#   ./deploy.sh <certificate-arn> [aws-profile]
#
# After stack creation, deploy the actual Lambda code:
#   cd infrastructure
#   zip lambda.zip lambda_function.py
#   aws lambda update-function-code \
#     --function-name <function-name-from-output> \
#     --zip-file fileb://lambda.zip

set -euo pipefail

STACK_NAME="galepost-log-upload"
TEMPLATE="template.yaml"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <certificate-arn> [aws-profile]"
    echo ""
    echo "Example:"
    echo "  $0 arn:aws:acm:us-east-1:123456789:certificate/abc-123 default"
    exit 1
fi

CERTIFICATE_ARN="$1"
AWS_PROFILE="${2:-}"

AWS_REGION="$(echo "$CERTIFICATE_ARN" | cut -d: -f4)"
if [ -z "$AWS_REGION" ]; then
    echo "Could not parse region from certificate ARN."
    exit 1
fi

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

"${AWS_CLI[@]}" cloudformation deploy \
    --template-file "${TEMPLATE}" \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        CertificateArn="${CERTIFICATE_ARN}" \
    --tags \
        Project=GalePost \
        Environment=Production

echo ""
echo "Waiting for stack to finish..."
set +e
"${AWS_CLI[@]}" cloudformation wait stack-create-complete --stack-name "${STACK_NAME}" 2>/dev/null
WAIT_STATUS=$?
if [ $WAIT_STATUS -ne 0 ]; then
    "${AWS_CLI[@]}" cloudformation wait stack-update-complete --stack-name "${STACK_NAME}" 2>/dev/null
    WAIT_STATUS=$?
fi
set -e

if [ $WAIT_STATUS -ne 0 ]; then
    echo "Stack failed to deploy. Recent events:"
    "${AWS_CLI[@]}" cloudformation describe-stack-events \
        --stack-name "${STACK_NAME}" \
        --max-items 15 \
        --output table
    exit 1
fi

echo "Stack outputs:"
"${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

echo ""
echo "DNS CNAME to create:"
"${AWS_CLI[@]}" cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs[?OutputKey==`CustomDomainTarget`].OutputValue' \
    --output text

echo ""
echo "Next steps:"
echo "  1. Package and deploy the Lambda code:"
echo "     cd infrastructure"
echo "     zip lambda.zip lambda_function.py"
echo "     aws lambda update-function-code \\"
echo "       --function-name \$(${AWS_CLI[@]} cloudformation describe-stacks \\"
echo "         --stack-name ${STACK_NAME} \\"
echo "         --query 'Stacks[0].Outputs[?OutputKey==\`LambdaFunctionArn\`].OutputValue' \\"
echo "         --output text) \\"
echo "       --zip-file fileb://lambda.zip"
echo ""
echo "  2. Verify SES sender identity for noreply@jasmer.tools"
echo "  3. Test the endpoint: curl -X POST https://galepost.jasmer.tools/logs/upload"
