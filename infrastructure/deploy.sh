#!/bin/bash
# Deploy the GalePost log upload backend.
#
# Prerequisites:
#   1. AWS CLI configured with credentials
#   2. ACM certificate for galepost.jasmer.tools (note the ARN)
#   3. Route53 hosted zone for jasmer.tools (note the zone ID)
#   4. SES verified sender identity for noreply@jasmer.tools
#
# Usage:
#   ./deploy.sh <hosted-zone-id> <certificate-arn>
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

if [ $# -lt 2 ]; then
    echo "Usage: $0 <hosted-zone-id> <certificate-arn>"
    echo ""
    echo "Example:"
    echo "  $0 Z1234567890ABC arn:aws:acm:us-east-1:123456789:certificate/abc-123"
    exit 1
fi

HOSTED_ZONE_ID="$1"
CERTIFICATE_ARN="$2"

echo "Deploying stack: ${STACK_NAME}"
echo "  Hosted Zone: ${HOSTED_ZONE_ID}"
echo "  Certificate: ${CERTIFICATE_ARN}"
echo ""

aws cloudformation deploy \
    --template-file "${TEMPLATE}" \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        HostedZoneId="${HOSTED_ZONE_ID}" \
        CertificateArn="${CERTIFICATE_ARN}" \
    --tags \
        Project=GalePost \
        Environment=Production

echo ""
echo "Stack outputs:"
aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs' \
    --output table

echo ""
echo "Next steps:"
echo "  1. Package and deploy the Lambda code:"
echo "     cd infrastructure"
echo "     zip lambda.zip lambda_function.py"
echo "     aws lambda update-function-code \\"
echo "       --function-name \$(aws cloudformation describe-stacks \\"
echo "         --stack-name ${STACK_NAME} \\"
echo "         --query 'Stacks[0].Outputs[?OutputKey==\`LambdaFunctionArn\`].OutputValue' \\"
echo "         --output text) \\"
echo "       --zip-file fileb://lambda.zip"
echo ""
echo "  2. Verify SES sender identity for noreply@jasmer.tools"
echo "  3. Test the endpoint: curl -X POST https://galepost.jasmer.tools/logs/upload"
